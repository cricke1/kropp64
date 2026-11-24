package se.konsiliet.wear.debug

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.util.Log
import java.io.File
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.runBlocking
import se.konsiliet.wear.data.QueueDb
import se.konsiliet.wear.link.Protocol
import se.konsiliet.wear.link.Sender

/**
 * Endast debug. Ersätter Bluetooth-transporten med adb när klock- och mobilemulatorn inte kan
 * parkopplas (parkoppling kräver Wear OS-appen från Play Butik och ett Google-konto).
 *
 * EXPORT skriver nästa batch, kodad exakt som Sender skickar den, till files/batch.json.
 * ACK raderar raderna first..last, precis som när mobilen kvitterat via MessageClient.
 * STATUS läser files/status.json (exporterad av mobilens debugbrygga) och lämnar den till samma
 * kod som tar emot `/konsiliet/status` från DataClient.
 * MESSAGE läser files/message.json ({"path": ..., "data": {...}}) och lämnar det till samma kod som
 * MessageClient-meddelanden (påminnelse, akut larm).
 * HAPTIC spelar ett mönster direkt (extra "p": AKUT, RORELSE, KLART), för att jämföra dem.
 */
class DebugBridge : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        val dao = QueueDb.get(context).pending()
        runBlocking(Dispatchers.IO) {
            when (intent.action) {
                "se.konsiliet.debug.EXPORT" -> {
                    val rows = dao.oldest(Protocol.BATCH_SIZE)
                    File(context.filesDir, "batch.json").writeBytes(Sender.encode(rows))
                    File(context.filesDir, "batch.range").writeText(
                        if (rows.isEmpty()) "" else "${rows.first().id} ${rows.last().id}")
                    Log.i("KonsilietDebug", "exporterade ${rows.size} rader")
                }
                "se.konsiliet.debug.STATUS" -> {
                    se.konsiliet.wear.link.Incoming.status(context, File(context.filesDir, "status.json").readText())
                    Log.i("KonsilietDebug", "status: ${se.konsiliet.wear.data.PhoneStatus.snapshot.value}")
                }
                "se.konsiliet.debug.MESSAGE" -> {
                    val o = org.json.JSONObject(File(context.filesDir, "message.json").readText())
                    se.konsiliet.wear.link.Incoming.message(context, o.getString("path"),
                        o.getJSONObject("data").toString().toByteArray())
                    Log.i("KonsilietDebug", "meddelande ${o.getString("path")}, mönster ${se.konsiliet.wear.alerts.Haptics.last}")
                }
                "se.konsiliet.debug.HAPTIC" -> {
                    val p = se.konsiliet.wear.alerts.Pattern.valueOf(intent.getStringExtra("p") ?: "KLART")
                    se.konsiliet.wear.alerts.Haptics.play(context, p)
                }
                "se.konsiliet.debug.ACK" -> {
                    val r = File(context.filesDir, "batch.range").readText().trim().split(" ")
                    if (r.size == 2) {
                        val n = dao.deleteRange(r[0].toLong(), r[1].toLong())
                        Log.i("KonsilietDebug", "kvitterade $n rader")
                    }
                }
            }
        }
    }
}
