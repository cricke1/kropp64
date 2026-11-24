package se.konsiliet.wear.link

import android.content.Context
import android.os.Build
import android.util.Log
import androidx.work.BackoffPolicy
import androidx.work.CoroutineWorker
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.ExistingWorkPolicy
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import com.google.android.gms.wearable.CapabilityClient
import com.google.android.gms.wearable.CapabilityInfo
import com.google.android.gms.wearable.MessageEvent
import com.google.android.gms.wearable.Node
import com.google.android.gms.wearable.Wearable
import com.google.android.gms.wearable.WearableListenerService
import java.io.IOException
import java.util.concurrent.TimeUnit
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.tasks.await
import kotlinx.coroutines.withTimeout
import org.json.JSONArray
import org.json.JSONObject
import se.konsiliet.wear.data.QueueDb
import se.konsiliet.wear.data.WatchState

private const val TAG = "KonsilietLink"

/** Protokollet mellan klocka och mobil. Samma konstanter finns i mobilappen. */
object Protocol {
    const val CAP_PHONE = "konsiliet_phone"
    const val PATH_BATCH = "/konsiliet/batch"
    const val PATH_FLUSH = "/konsiliet/flush"
    const val PATH_NUDGE = "/konsiliet/nudge"
    const val BATCH_SIZE = 400
}

sealed interface FlushResult {
    data object Empty : FlushResult
    data object NoPhone : FlushResult
    data class Sent(val count: Int) : FlushResult
}

object Sender {
    private val mutex = Mutex()

    /** Batchformatet: kompakta trippler [ts, metric, value] för att hålla meddelandet litet. */
    fun encode(rows: List<se.konsiliet.wear.data.Pending>): ByteArray {
        val samples = JSONArray()
        for (r in rows) samples.put(JSONArray().put(r.ts).put(r.metric).put(r.value))
        return JSONObject()
            .put("v", 1)
            .put("source", WatchState.source)
            .put("device", Build.MODEL)
            .put("samples", samples)
            .toString().toByteArray()
    }

    suspend fun findPhone(ctx: Context): Node? {
        val info = Wearable.getCapabilityClient(ctx)
            .getCapability(Protocol.CAP_PHONE, CapabilityClient.FILTER_REACHABLE).await()
        return info.nodes.firstOrNull { it.isNearby } ?: info.nodes.firstOrNull()
    }

    /**
     * Skickar kön i batchar med MessageClient.sendRequest. Mobilen svarar först när batchen ligger
     * i dess Room-databas, och först då raderas raderna här. Avbryts överföringen mitt i blir
     * raderna kvar och skickas igen. Dubbletter är ofarliga: mobilen och servern avduplicerar
     * på (metric, ts, source).
     */
    suspend fun flush(ctx: Context): FlushResult = mutex.withLock {
        val dao = QueueDb.get(ctx).pending()
        // Mer än 30 dagar gammal data utan kontakt med mobilen rensas, annars kan lagringen ta slut.
        dao.pruneOlderThan(System.currentTimeMillis() / 1000.0 - 30 * 86400)
        if (dao.count() == 0) return FlushResult.Empty
        val node = findPhone(ctx) ?: run {
            WatchState.noteError("Mobilen nås inte. Data sparas på klockan.")
            return FlushResult.NoPhone
        }
        val client = Wearable.getMessageClient(ctx)
        var total = 0
        while (true) {
            val rows = dao.oldest(Protocol.BATCH_SIZE)
            if (rows.isEmpty()) break
            val payload = encode(rows)
            val resp = withTimeout(30_000) { client.sendRequest(node.id, Protocol.PATH_BATCH, payload).await() }
            val ack = JSONObject(String(resp))
            if (!ack.optBoolean("ok")) throw IOException("mobilen avvisade batchen: ${ack.optString("error")}")
            dao.deleteRange(rows.first().id, rows.last().id)
            total += rows.size
            WatchState.noteSent(total)
        }
        FlushResult.Sent(total)
    }
}

object Flush {
    /**
     * Begär att kön töms. Vanliga anrop väntar 20 sekunder så att flera leveranser från
     * Health Services slås ihop till en överföring (sparar batteri). Brådskande (fall) går direkt.
     */
    fun request(ctx: Context, urgent: Boolean = false) {
        val b = OneTimeWorkRequestBuilder<FlushWorker>()
            .setBackoffCriteria(BackoffPolicy.EXPONENTIAL, 30, TimeUnit.SECONDS)
        if (!urgent) b.setInitialDelay(20, TimeUnit.SECONDS)
        WorkManager.getInstance(ctx).enqueueUniqueWork(
            if (urgent) "flush-now" else "flush", ExistingWorkPolicy.KEEP, b.build()
        )
    }

    /** Skyddsnät om alla andra utlösare missas. */
    fun schedulePeriodic(ctx: Context) {
        WorkManager.getInstance(ctx).enqueueUniquePeriodicWork(
            "flush-periodic", ExistingPeriodicWorkPolicy.KEEP,
            PeriodicWorkRequestBuilder<FlushWorker>(15, TimeUnit.MINUTES).build()
        )
    }
}

class FlushWorker(ctx: Context, params: WorkerParameters) : CoroutineWorker(ctx, params) {
    override suspend fun doWork(): Result = try {
        when (val r = Sender.flush(applicationContext)) {
            // Ingen mobil i närheten: vänta på att den dyker upp (CAPABILITY_CHANGED) eller nästa period.
            FlushResult.NoPhone -> Result.success()
            else -> { Log.d(TAG, "flush: $r"); Result.success() }
        }
    } catch (e: Exception) {
        Log.w(TAG, "flush misslyckades", e)
        WatchState.noteError("Överföring avbröts: ${e.javaClass.simpleName}")
        if (runAttemptCount < 8) Result.retry() else Result.success()
    }
}

/** Mobilen ber om data (t.ex. när appen öppnas) eller kommer tillbaka inom räckhåll. */
class PhoneListenerService : WearableListenerService() {
    override fun onMessageReceived(event: MessageEvent) {
        when (event.path) {
            Protocol.PATH_FLUSH -> Flush.request(applicationContext, urgent = true)
            Protocol.PATH_NUDGE -> {
                val o = runCatching { JSONObject(String(event.data)) }.getOrNull() ?: return
                Nudge.show(applicationContext, o.optString("title"), o.optString("body"))
            }
        }
    }

    override fun onCapabilityChanged(info: CapabilityInfo) {
        if (info.name == Protocol.CAP_PHONE && info.nodes.isNotEmpty()) {
            Flush.request(applicationContext, urgent = true)
        }
    }
}

/** Stillasittandevaktens påminnelse: notis med tydlig vibration på klockan. */
object Nudge {
    private const val CHANNEL = "rorelse"

    fun show(ctx: Context, title: String, body: String) {
        val nm = ctx.getSystemService(android.app.NotificationManager::class.java)
        nm.createNotificationChannel(android.app.NotificationChannel(CHANNEL, "Rörelse",
            android.app.NotificationManager.IMPORTANCE_HIGH).apply {
            enableVibration(true)
            vibrationPattern = longArrayOf(0, 250, 150, 250)
        })
        if (Build.VERSION.SDK_INT >= 33 &&
            ctx.checkSelfPermission(android.Manifest.permission.POST_NOTIFICATIONS) != android.content.pm.PackageManager.PERMISSION_GRANTED
        ) return
        val n = androidx.core.app.NotificationCompat.Builder(ctx, CHANNEL)
            .setSmallIcon(se.konsiliet.wear.R.drawable.ic_stat)
            .setContentTitle(title)
            .setContentText(body)
            .setAutoCancel(true)
            .setVibrate(longArrayOf(0, 250, 150, 250))
            .setCategory(androidx.core.app.NotificationCompat.CATEGORY_REMINDER)
            .build()
        nm.notify(20, n)
    }
}
