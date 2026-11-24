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
                Haptics.notify(ctx, Pattern.RORELSE, 20, o.optString("title"), o.optString("body"))
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
    private var lastHrRequest = 0L

    fun update(ctx: Context) {
        runCatching { TileService.getUpdater(ctx).requestUpdate(KonsilietTile::class.java) }
        for (c in listOf(RecoveryComplication::class.java, ConsultComplication::class.java)) {
            runCatching { ComplicationDataSourceUpdateRequester.create(ctx, ComponentName(ctx, c)).requestUpdateAll() }
        }
    }

    /** Pulsen ändras ofta. Tilen uppdateras för den högst var femte minut, för batteriets skull. */
    fun onHeartRate(ctx: Context) {
        val now = System.currentTimeMillis()
        if (now - lastHrRequest < 5 * 60_000) return
        lastHrRequest = now
        runCatching { TileService.getUpdater(ctx).requestUpdate(KonsilietTile::class.java) }
    }
}
