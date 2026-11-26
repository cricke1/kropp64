package se.konsiliet.wear.link

import android.content.ComponentName
import android.content.Context
import android.util.Log
import androidx.wear.tiles.TileService
import androidx.wear.watchface.complications.datasource.ComplicationDataSourceUpdateRequester
import com.google.android.gms.wearable.DataMapItem
import com.google.android.gms.wearable.Wearable
import kotlinx.coroutines.tasks.await
import org.json.JSONObject
import se.konsiliet.wear.alerts.Haptics
import se.konsiliet.wear.alerts.Pattern
import se.konsiliet.wear.complication.ConsultComplication
import se.konsiliet.wear.complication.HeartRateComplication
import se.konsiliet.wear.complication.RecoveryComplication
import se.konsiliet.wear.data.PhoneStatus
import se.konsiliet.wear.data.Urgency
import se.konsiliet.wear.tile.KonsilietTile

private const val TAG = "KonsilietIncoming"

/**
 * Allt som kommer från mobilen går genom här, både från Data Layer (PhoneListenerService) och,
 * i debug-bygget, från adb-bryggan. Då testas samma kod som används med en riktig parkoppling.
 */
object Incoming {
    /** Bedömningar äldre än så här när de kommer fram ger ingen vibration (t.ex. efter en lång frånkoppling). */
    private const val KLART_MAX_AGE_S = 30 * 60

    fun message(ctx: Context, path: String, data: ByteArray) {
        when (path) {
            Protocol.PATH_FLUSH -> Flush.request(ctx, urgent = true)
            Protocol.PATH_NUDGE -> {
                val o = runCatching { JSONObject(String(data)) }.getOrNull() ?: return
                val typ = o.optString("typ").ifBlank { "afk" }
                // Svarsknappar på klockan: svaret går till mobilen, som skickar det till servern.
                val svar = when (typ) {
                    "afk" -> listOf(Triple("Om 30 min", "snooze", 30), Triple("Mitt i ett pass", "fokus", 120))
                    "stress" -> listOf(Triple("Inte nu", "inte_nu", 180))
                    "sova" -> listOf(Triple("Om 20 min", "snooze", 20), Triple("Inte i kväll", "inte_nu", 0))
                    "pass" -> listOf(Triple("Om 1 h", "snooze", 60), Triple("Inte i dag", "inte_nu", 0))
                    else -> emptyList()
                }
                val id = 20 + listOf("afk", "stress", "sova", "pass").indexOf(typ).coerceAtLeast(0)
                val acts = svar.mapIndexed { k, (label, s, min) -> label to SvarReceiver.intent(ctx, id, k, typ, s, min) }.let { a ->
                    // Passdagen: "Starta pass" först, så att dagens pass startar direkt från notisen.
                    if (typ != "pass") a else listOf("Starta pass" to android.app.PendingIntent.getActivity(ctx, id * 4 + 3,
                        android.content.Intent(ctx, se.konsiliet.wear.ui.MainActivity::class.java).putExtra("starta_pass", true)
                            .addFlags(android.content.Intent.FLAG_ACTIVITY_NEW_TASK or android.content.Intent.FLAG_ACTIVITY_SINGLE_TOP),
                        android.app.PendingIntent.FLAG_IMMUTABLE or android.app.PendingIntent.FLAG_UPDATE_CURRENT)) + a
                }
                val open = when (typ) {
                    "stress" -> android.content.Intent(ctx, se.konsiliet.wear.ui.AndasActivity::class.java)
                    "pass" -> android.content.Intent(ctx, se.konsiliet.wear.ui.MainActivity::class.java).putExtra("starta_pass", true)
                    else -> null
                }
                Haptics.notify(ctx, Pattern.RORELSE, id, o.optString("title"), o.optString("body"), acts, open)
            }
            Protocol.PATH_ANDAS -> {
                // Från mobilens "Andas 60 s". Startas via notisen, eftersom en app i bakgrunden inte får öppna skärmar själv.
                Haptics.notify(ctx, Pattern.RORELSE, 24, "Andas 60 sekunder", "Tryck för att börja. In 4 s, ut 6 s.",
                    open = android.content.Intent(ctx, se.konsiliet.wear.ui.AndasActivity::class.java))
                runCatching {
                    ctx.startActivity(android.content.Intent(ctx, se.konsiliet.wear.ui.AndasActivity::class.java)
                        .addFlags(android.content.Intent.FLAG_ACTIVITY_NEW_TASK))
                }
            }
            Protocol.PATH_ALERT -> {
                val o = runCatching { JSONObject(String(data)) }.getOrNull() ?: return
                val id = 1000 + (o.optLong("id") % 1000).toInt()
                Haptics.notify(ctx, Pattern.AKUT, id, o.optString("title"), o.optString("body"))
            }
        }
    }

    /** Ny status från mobilen: spara, uppdatera tile och komplikationer, vibrera om ett konsilium blev klart. */
    fun status(ctx: Context, json: String) {
        val (prev, next) = PhoneStatus.apply(json) ?: run { Log.d(TAG, "äldre status ignorerad"); return }
        Surfaces.update(ctx)
        val prefs = ctx.getSharedPreferences("phone_status", Context.MODE_PRIVATE)
        val cid = next.consultId
        val fresh = System.currentTimeMillis() / 1000.0 - next.verdictAt < KLART_MAX_AGE_S
        if (cid != null && !next.consultRunning && next.urgency != null && fresh &&
            prefs.getString("klart_notified", null) != cid
        ) {
            prefs.edit().putString("klart_notified", cid).apply()
            // Brådskande bedömningar skrivs sakligt, utan forumtermer.
            val serious = next.urgency == "kontakta_vard_nu" || next.urgency == "ta_upp_med_varden"
            Haptics.notify(ctx, Pattern.KLART, 30, if (serious) "Bedömningen är klar" else "Tråden är löst",
                (if (serious) Urgency.label(next.urgency) else "Markerad som lösning: " + Urgency.label(next.urgency)) +
                    (next.summary?.let { ". $it" } ?: ""))
        }
        Log.i(TAG, "status: poäng ${prev.score} -> ${next.score}, pågår ${next.consultRunning}, brådska ${next.urgency}")
    }

    /** Läser det senaste statusobjektet direkt från Data Layer, ifall en leverans missades medan processen var död. */
    suspend fun pull(ctx: Context) {
        runCatching {
            val items = Wearable.getDataClient(ctx).dataItems.await()
            try {
                items.filter { it.uri.path == PhoneStatus.PATH }
                    .mapNotNull { DataMapItem.fromDataItem(it).dataMap.getString("status") }
                    .forEach { status(ctx, it) }
            } finally { items.release() }
        }.onFailure { Log.d(TAG, "kunde inte läsa Data Layer: ${it.message}") }
    }
}

/** Tile och komplikationer läser cachen. Här ber vi systemet hämta om dem. */
object Surfaces {
    /**
     * Ber systemet rita om rutan. Binder direkt till systemets uppdateringstjänst
     * (androidx.wear.tiles.action.BIND_UPDATE_REQUESTER i hemskärmens paket) och skickar begäran
     * när anslutningen finns. TileService.getUpdater().requestUpdate() gjorde ingenting på
     * klockemulatorn (Wear OS 6): ingen ny rendering på 20 försök, medan en direkt bindning gav
     * onTileRequest inom 15 ms (se RESAN.md). Biblioteket används som reserv.
     * Väntar högst 3 s på anslutningen om den anropas utanför huvudtråden, så att processen inte
     * hinner frysas innan begäran gått iväg (onDataChanged körs på en bakgrundstråd).
     */
    @android.annotation.SuppressLint("RestrictedApi")
    fun requestTile(ctx: Context) {
        val app = ctx.applicationContext
        val home = app.packageManager.resolveActivity(
            android.content.Intent(android.content.Intent.ACTION_MAIN).addCategory(android.content.Intent.CATEGORY_HOME), 0)
            ?.activityInfo?.packageName
        val done = java.util.concurrent.CountDownLatch(1)
        val conn = object : android.content.ServiceConnection {
            override fun onServiceConnected(name: ComponentName, b: android.os.IBinder) {
                try {
                    androidx.wear.tiles.TileUpdateRequesterService.Stub.asInterface(b)
                        .requestUpdate(ComponentName(app, KonsilietTile::class.java), androidx.wear.tiles.TileUpdateRequestData())
                    android.util.Log.i("KonsilietTile", "requestUpdate skickad till $home")
                } catch (e: Exception) {
                    android.util.Log.w("KonsilietTile", "requestUpdate misslyckades", e)
                } finally {
                    runCatching { app.unbindService(this) }
                    done.countDown()
                }
            }
            override fun onServiceDisconnected(name: ComponentName) {}
        }
        val bound = home != null && runCatching {
            app.bindService(android.content.Intent("androidx.wear.tiles.action.BIND_UPDATE_REQUESTER").setPackage(home),
                conn, Context.BIND_AUTO_CREATE)
        }.getOrDefault(false)
        if (!bound) {
            android.util.Log.i("KonsilietTile", "ingen uppdateringstjänst, använder TileService.getUpdater")
            runCatching { TileService.getUpdater(app).requestUpdate(KonsilietTile::class.java) }
            return
        }
        if (android.os.Looper.myLooper() != android.os.Looper.getMainLooper()) done.await(3, java.util.concurrent.TimeUnit.SECONDS)
    }

    fun update(ctx: Context) {
        requestTile(ctx)
        for (c in listOf(RecoveryComplication::class.java, ConsultComplication::class.java)) {
            runCatching { ComplicationDataSourceUpdateRequester.create(ctx, ComponentName(ctx, c)).requestUpdateAll() }
        }
    }

    /** Ny puls: be urtavlan hämta pulskomplikationen igen. */
    fun updateHr(ctx: Context) {
        runCatching { ComplicationDataSourceUpdateRequester.create(ctx, ComponentName(ctx, HeartRateComplication::class.java)).requestUpdateAll() }
    }
}

/** Svar på en knuff från klockans notis. Skickas till mobilen över MessageClient (`/konsiliet/svar`). */
class SvarReceiver : android.content.BroadcastReceiver() {
    companion object {
        fun intent(ctx: Context, notis: Int, k: Int, typ: String, svar: String, minuter: Int): android.app.PendingIntent =
            android.app.PendingIntent.getBroadcast(ctx, notis * 4 + k,
                android.content.Intent(ctx, SvarReceiver::class.java).putExtra("notis", notis).putExtra("typ", typ)
                    .putExtra("svar", svar).putExtra("minuter", minuter),
                android.app.PendingIntent.FLAG_IMMUTABLE or android.app.PendingIntent.FLAG_UPDATE_CURRENT)
    }

    override fun onReceive(context: Context, intent: android.content.Intent) {
        val o = JSONObject().put("typ", intent.getStringExtra("typ")).put("svar", intent.getStringExtra("svar"))
            .put("minuter", intent.getIntExtra("minuter", 0))
        context.getSystemService(android.app.NotificationManager::class.java).cancel(intent.getIntExtra("notis", 0))
        // Sparas också för debugbryggan (emulatorerna kan inte parkopplas, se RESAN.md).
        java.io.File(context.filesDir, "svar.json").writeText(o.toString())
        val pending = goAsync()
        Thread {
            try {
                kotlinx.coroutines.runBlocking {
                    runCatching {
                        val nodes = Wearable.getNodeClient(context).connectedNodes.await()
                        for (n in nodes) Wearable.getMessageClient(context).sendMessage(n.id, Protocol.PATH_SVAR, o.toString().toByteArray()).await()
                    }.onFailure { Log.d(TAG, "kunde inte skicka svaret: ${it.message}") }
                }
            } finally { pending.finish() }
        }.start()
    }
}
