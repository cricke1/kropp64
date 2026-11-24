package se.konsiliet.app.link

import android.content.Context
import android.util.Log
import com.google.android.gms.tasks.Task
import com.google.android.gms.tasks.Tasks
import com.google.android.gms.wearable.CapabilityClient
import com.google.android.gms.wearable.CapabilityInfo
import com.google.android.gms.wearable.Wearable
import com.google.android.gms.wearable.WearableListenerService
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.tasks.await
import org.json.JSONObject
import se.konsiliet.app.data.ExerciseRow
import se.konsiliet.app.data.KonsilietDb
import se.konsiliet.app.data.Prefs
import se.konsiliet.app.data.SampleRow

private const val TAG = "KonsilietWatch"

object Protocol {
    const val CAP_WATCH = "konsiliet_watch"
    const val PATH_BATCH = "/konsiliet/batch"
    const val PATH_FLUSH = "/konsiliet/flush"
    const val PATH_NUDGE = "/konsiliet/nudge"
    const val PATH_ALERT = "/konsiliet/alert"
}

/**
 * Tar emot klockans batchar. Svaret (kvittensen) skickas först när raderna ligger i Room,
 * eftersom klockan raderar sin kopia när den får ett ok. Systemet startar tjänsten vid behov,
 * även om appen inte körs.
 */
class WatchListenerService : WearableListenerService() {

    override fun onRequest(nodeId: String, path: String, request: ByteArray): Task<ByteArray>? {
        if (path != Protocol.PATH_BATCH) return null
        val reply = try {
            val n = runBlocking(Dispatchers.IO) { store(applicationContext, request) }
            JSONObject().put("ok", true).put("stored", n)
        } catch (e: Exception) {
            Log.e(TAG, "kunde inte spara batch", e)
            JSONObject().put("ok", false).put("error", e.javaClass.simpleName + ": " + e.message)
        }
        return Tasks.forResult(reply.toString().toByteArray())
    }

    override fun onCapabilityChanged(info: CapabilityInfo) {
        // Klockan kom inom räckhåll igen: be den tömma sin kö direkt i stället för att vänta.
        if (info.nodes.isNotEmpty()) runBlocking { requestFlush(applicationContext) }
    }

    companion object {
        suspend fun store(ctx: Context, request: ByteArray): Int {
            val o = JSONObject(String(request))
            val source = o.optString("source", "watch").ifEmpty { "watch" }
            val arr = o.getJSONArray("samples")
            val rows = ArrayList<SampleRow>(arr.length())
            for (i in 0 until arr.length()) {
                val s = arr.getJSONArray(i)
                val v = s.getDouble(2)
                if (v.isNaN() || v.isInfinite()) continue
                rows += SampleRow(metric = s.getString(1), ts = s.getDouble(0), value = v, source = source)
            }
            KonsilietDb.get(ctx).samples().insert(rows)
            // Passmarkörer blir även pass för /api/ingest/exercise: värde > 0 är start (ExerciseType-id), 0 är slut.
            val types = o.optJSONObject("exercise_types")
            val ex = KonsilietDb.get(ctx).exercise()
            for (r in rows.filter { it.metric == "exercise" }.sortedBy { it.ts }) {
                if (r.value > 0) {
                    val id = r.value.toInt().toString()
                    ex.insertStart(ExerciseRow(id = "$source-${(r.ts * 1000).toLong()}", start = r.ts, end = null,
                        typ = types?.optString(id)?.ifEmpty { null } ?: "typ_$id", source = source))
                } else ex.closeLatest(source, r.ts)
            }
            Prefs.link { it.copy(lastWatchAt = System.currentTimeMillis(), lastWatchSource = source) }
            UploadScheduler.now(ctx)
            return rows.size
        }

        /** Stillasittandevaktens påminnelse ska också vibrera på klockan. */
        fun forwardNudge(ctx: Context, title: String, body: String) {
            val bytes = JSONObject().put("title", title).put("body", body).toString().toByteArray()
            Prefs.putString("lastWatchMessage", JSONObject().put("path", Protocol.PATH_NUDGE)
                .put("data", JSONObject(String(bytes))).toString())
            kotlinx.coroutines.CoroutineScope(Dispatchers.IO).launch {
                runCatching {
                    val nodes = Wearable.getCapabilityClient(ctx)
                        .getCapability(Protocol.CAP_WATCH, CapabilityClient.FILTER_REACHABLE).await().nodes
                    for (n in nodes) Wearable.getMessageClient(ctx).sendMessage(n.id, Protocol.PATH_NUDGE, bytes).await()
                }.onFailure { Log.d(TAG, "kunde inte skicka påminnelse till klockan: ${it.message}") }
            }
        }

        /** Akut larm till klockan: eget vibrationsmönster (lång, stark, går igenom Stör ej). */
        fun forwardAlert(ctx: Context, id: Long, title: String, body: String) {
            val bytes = JSONObject().put("id", id).put("title", title).put("body", body).toString().toByteArray()
            Prefs.putString("lastWatchMessage", JSONObject().put("path", Protocol.PATH_ALERT)
                .put("data", JSONObject(String(bytes))).toString())
            kotlinx.coroutines.CoroutineScope(Dispatchers.IO).launch {
                runCatching {
                    val nodes = Wearable.getCapabilityClient(ctx)
                        .getCapability(Protocol.CAP_WATCH, CapabilityClient.FILTER_REACHABLE).await().nodes
                    for (n in nodes) Wearable.getMessageClient(ctx).sendMessage(n.id, Protocol.PATH_ALERT, bytes).await()
                }.onFailure { Log.d(TAG, "kunde inte skicka larm till klockan: ${it.message}") }
            }
        }

        /** Ber alla anslutna klockor skicka det de har. Används när appen öppnas. */
        suspend fun requestFlush(ctx: Context) {
            runCatching {
                val nodes = Wearable.getCapabilityClient(ctx)
                    .getCapability(Protocol.CAP_WATCH, CapabilityClient.FILTER_REACHABLE).await().nodes
                for (n in nodes) {
                    Wearable.getMessageClient(ctx).sendMessage(n.id, Protocol.PATH_FLUSH, ByteArray(0)).await()
                }
            }.onFailure { Log.d(TAG, "ingen klocka att be om data: ${it.message}") }
        }
    }
}
