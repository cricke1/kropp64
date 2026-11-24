package se.konsiliet.app.link

import android.app.Notification
import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.net.ConnectivityManager
import android.net.Network
import android.util.Log
import androidx.core.app.NotificationCompat
import androidx.core.app.ServiceCompat
import androidx.lifecycle.LifecycleService
import androidx.lifecycle.lifecycleScope
import kotlin.math.min
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.distinctUntilChanged
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.withTimeoutOrNull
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import org.json.JSONObject
import se.konsiliet.app.R
import se.konsiliet.app.alerts.Alerts
import se.konsiliet.app.alerts.Channels
import se.konsiliet.app.data.EventRow
import se.konsiliet.app.data.KonsilietDb
import se.konsiliet.app.data.Prefs
import se.konsiliet.app.hc.HcScheduler
import se.konsiliet.app.net.Api
import se.konsiliet.app.ui.MainActivity

private const val TAG = "KonsilietLive"

/** Senaste live-värdet per mätvärde från servern (sample.live). */
data class LiveSample(val metric: String, val ts: Double, val value: Double)

object Live {
    val samples = MutableStateFlow<Map<String, LiveSample>>(emptyMap())
}

/**
 * Förgrundstjänsten som håller "kontinuerlig connect":
 *  - WebSocket mot /ws med återanslutning (1 s, 2 s, 4 s ... högst 60 s) och ping var 25:e sekund
 *  - nätverksbyte (wifi till mobilnät, flygplansläge av) ger omedelbar återanslutning och uppladdning
 *  - var 60:e sekund: finns det något i kön startas en uppladdning
 *  - typ connectedDevice: ingen sextimmarsgräns som dataSync har på Android 15
 * Startas av appen och efter omstart (BootReceiver). START_STICKY om systemet ändå dödar den.
 */
class LiveService : LifecycleService() {

    companion object {
        private const val NOTIF_ID = 1
        fun start(ctx: Context) {
            runCatching { ctx.startForegroundService(Intent(ctx, LiveService::class.java)) }
                .onFailure { Log.w(TAG, "kunde inte starta förgrundstjänst", it) }
        }
    }

    private var socket: WebSocket? = null
    private var loop: Job? = null
    private val wake = Channel<Unit>(Channel.CONFLATED)
    private var netCallback: ConnectivityManager.NetworkCallback? = null

    override fun onCreate() {
        super.onCreate()
        ServiceCompat.startForeground(this, NOTIF_ID, notification("Ansluter"), ServiceInfo.FOREGROUND_SERVICE_TYPE_CONNECTED_DEVICE)
        loop = lifecycleScope.launch { socketLoop() }
        lifecycleScope.launch { uploadTicker() }
        lifecycleScope.launch { statusUpdater() }
        val cm = getSystemService(ConnectivityManager::class.java)
        netCallback = object : ConnectivityManager.NetworkCallback() {
            override fun onAvailable(network: Network) {
                wake.trySend(Unit)
                UploadScheduler.now(applicationContext)
            }
        }.also { cm.registerDefaultNetworkCallback(it) }
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        super.onStartCommand(intent, flags, startId)
        wake.trySend(Unit)
        return START_STICKY
    }

    override fun onDestroy() {
        netCallback?.let { getSystemService(ConnectivityManager::class.java).unregisterNetworkCallback(it) }
        socket?.cancel()
        super.onDestroy()
    }

    private suspend fun socketLoop() {
        var backoff = 1_000L
        while (lifecycleScope.isActive) {
            val closed = Channel<String>(Channel.CONFLATED)
            val url = Api.wsUrl()
            val req = runCatching { Api.request("/ws").url(url).build() }.getOrNull()
            if (req == null) {
                Prefs.link { it.copy(wsConnected = false) }
                withTimeoutOrNull(30_000) { wake.receive() }
                continue
            }
            var opened = false
            socket = Api.http.newWebSocket(req, object : WebSocketListener() {
                override fun onOpen(webSocket: WebSocket, response: Response) {
                    opened = true
                    Prefs.link { it.copy(wsConnected = true) }
                    UploadScheduler.now(applicationContext)
                }
                override fun onMessage(webSocket: WebSocket, text: String) {
                    lifecycleScope.launch(Dispatchers.IO) { handle(text) }
                }
                override fun onClosed(webSocket: WebSocket, code: Int, reason: String) { closed.trySend("stängd $code") }
                override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                    closed.trySend(t.javaClass.simpleName)
                }
            })
            val why = closed.receive()
            Prefs.link { it.copy(wsConnected = false) }
            Log.d(TAG, "ws nere: $why")
            if (opened) backoff = 1_000L
            // Vänta backoff, men vakna direkt om nätet kommer tillbaka.
            withTimeoutOrNull(backoff) { wake.receive() }
            backoff = min(backoff * 2, 60_000L)
        }
    }

    private suspend fun handle(text: String) {
        val o = runCatching { JSONObject(text) }.getOrNull() ?: return
        val kind = o.optString("kind")
        val payload = o.optJSONObject("payload") ?: JSONObject()
        if (kind == "sample.live") {
            val s = LiveSample(payload.optString("metric"), payload.optDouble("ts"), payload.optDouble("value"))
            Live.samples.value = Live.samples.value + (s.metric to s)
            return
        }
        if (o.isNull("id")) return
        val row = EventRow(o.getLong("id"), o.optDouble("ts"), kind, payload.toString())
        KonsilietDb.get(applicationContext).events().insert(listOf(row))
        // Alerts avgör på id och replay-märkning om händelsen ska ge notis, vibration eller sms
        // (se EventGate). Allt hamnar ändå i listorna via raden ovan.
        Alerts.onEvent(applicationContext, row, replay = o.optBoolean("replay", false))
        // Widgeten och klockan hämtar om sammanfattningen (fördröjt, så att en historikskur blir en hämtning).
        se.konsiliet.app.widget.Summary.onEvent(applicationContext, kind)
    }

    private suspend fun uploadTicker() {
        val db = KonsilietDb.get(applicationContext)
        while (lifecycleScope.isActive) {
            delay(60_000)
            if (db.samples().pending() > 0) UploadScheduler.now(applicationContext)
            HcScheduler.maybeRunSoon(applicationContext)
        }
    }

    private suspend fun statusUpdater() {
        val db = KonsilietDb.get(applicationContext)
        combine(Prefs.link, db.samples().pendingFlow()) { l, q ->
            buildString {
                append(if (l.wsConnected) "Ansluten till servern" else "Ingen kontakt med servern")
                append(" · kö ").append(q)
            }
        }.distinctUntilChanged().collect { text ->
            getSystemService(android.app.NotificationManager::class.java).notify(NOTIF_ID, notification(text))
        }
    }

    private fun notification(text: String): Notification {
        val open = PendingIntent.getActivity(this, 0, Intent(this, MainActivity::class.java), PendingIntent.FLAG_IMMUTABLE)
        return NotificationCompat.Builder(this, Channels.LINK)
            .setSmallIcon(R.drawable.ic_stat)
            .setContentTitle("Konsiliet")
            .setContentText(text)
            .setOngoing(true)
            .setOnlyAlertOnce(true)
            .setShowWhen(false)
            .setContentIntent(open)
            .setPriority(NotificationCompat.PRIORITY_MIN)
            .build()
    }
}

class BootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        LiveService.start(context)
        UploadScheduler.periodic(context)
        UploadScheduler.now(context)
        HcScheduler.periodic(context)
        se.konsiliet.app.widget.Summary.periodic(context)
        Alerts.restorePendingSms(context)
    }
}
