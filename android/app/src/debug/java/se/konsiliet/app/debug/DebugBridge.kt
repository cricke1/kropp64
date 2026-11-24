package se.konsiliet.app.debug

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.util.Log
import java.io.File
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.runBlocking
import org.json.JSONObject
import se.konsiliet.app.link.WatchListenerService

/**
 * Endast debug. Tar emot en batch som klockemulatorn exporterat (via adb i stället för Bluetooth)
 * och lämnar den till exakt samma kod som WatchListenerService.onRequest använder.
 * Källan tvingas till något som innehåller "emulator" så att testdata aldrig kan se riktig ut.
 * Kvittensen skrivs till files/ack.json, som testskriptet läser innan klockan får ACK.
 */
class DebugBridge : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action == "se.konsiliet.debug.EXPORT_STATUS") { exportStatus(context); return }
        if (intent.action == "se.konsiliet.debug.SVAR") {
            // Klockans svar på en knuff, flyttat med adb i stället för MessageClient (files/svar.json).
            val o = JSONObject(File(context.filesDir, "svar.json").readText())
            WatchListenerService.svar(context, o)
            Log.i("KonsilietDebug", "svar från klockan: $o")
            return
        }
        val file = File(context.filesDir, "inject.json")
        val reply = try {
            val o = JSONObject(file.readText())
            if (!o.optString("source").contains("emulator")) o.put("source", "watch-emulator")
            val n = runBlocking(Dispatchers.IO) { WatchListenerService.store(context, o.toString().toByteArray()) }
            JSONObject().put("ok", true).put("stored", n)
        } catch (e: Exception) {
            Log.e("KonsilietDebug", "inject misslyckades", e)
            JSONObject().put("ok", false).put("error", e.toString())
        }
        File(context.filesDir, "ack.json").writeText(reply.toString())
        Log.i("KonsilietDebug", "inject: $reply")
    }

    /**
     * Mobil till klocka utan parkoppling: hämtar sammanfattningen på nytt (samma kod som widgeten och
     * WorkManager använder, inklusive putDataItem) och skriver exakt den JSON som lades i Data Layer
     * till files/status.json, plus senaste meddelande till klockan (påminnelse, akut larm) till
     * files/message.json. Testskriptet flyttar dem till klockemulatorn med adb.
     */
    private fun exportStatus(context: Context) {
        val json = runBlocking(Dispatchers.IO) {
            se.konsiliet.app.widget.Summary.refresh(context)
            se.konsiliet.app.data.Prefs.getString("watchStatus")
        }
        File(context.filesDir, "status.json").writeText(json ?: "")
        File(context.filesDir, "message.json").writeText(se.konsiliet.app.data.Prefs.getString("lastWatchMessage") ?: "")
        Log.i("KonsilietDebug", "status exporterad: $json")
    }
}
