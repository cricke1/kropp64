package se.konsiliet.app.link

import android.content.Context
import android.util.Log
import androidx.work.BackoffPolicy
import androidx.work.Constraints
import androidx.work.CoroutineWorker
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.ExistingWorkPolicy
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import java.io.IOException
import java.util.concurrent.TimeUnit
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import org.json.JSONArray
import org.json.JSONObject
import se.konsiliet.app.data.KonsilietDb
import se.konsiliet.app.data.Prefs
import se.konsiliet.app.data.SampleRow
import se.konsiliet.app.net.Api
import se.konsiliet.app.net.HttpError

private const val TAG = "KonsilietUpload"

/**
 * Laddar upp kön till servern. Regler:
 *  - en rad markeras uppladdad först när servern svarat 2xx på exakt den batchen
 *  - nätfel, 5xx, 401, 408 och 429 betyder "försök igen senare", aldrig "släng"
 *  - 400/422 betyder att något i batchen inte går att tolka: batchen delas tills den felande
 *    raden hittas, som då markeras avvisad (sparas lokalt för felsökning) så att den inte blockerar resten
 *  - servern gör INSERT OR REPLACE på (metric, ts, source), så en batch som skickas två gånger
 *    (svaret tappades på vägen) ger inga dubbletter
 */
object Uploader {
    private val mutex = Mutex()
    private const val BATCH = 500

    suspend fun drain(ctx: Context): Int = mutex.withLock {
        val db = KonsilietDb.get(ctx)
        var total = 0
        while (true) {
            val rows = db.samples().nextBatch(BATCH)
            if (rows.isEmpty()) break
            total += sendWithBisect(ctx, rows)
        }
        for (s in db.sleep().pending(50)) {
            val body = JSONObject()
                .put("id", s.id).put("start", s.start).put("end", s.end)
                .put("stages", JSONArray(s.stages)).put("source", s.source)
            try {
                Api.postJson("/api/ingest/sleep", body)
                db.sleep().mark(s.id, 1)
            } catch (e: HttpError) {
                if (e.code == 400 || e.code == 422) db.sleep().mark(s.id, 2) else throw e
            }
        }
        for (e in db.exercise().pending(50)) {
            val body = JSONObject().put("id", e.id).put("start", e.start)
                .put("end", e.end ?: JSONObject.NULL).put("typ", e.typ).put("source", e.source)
            try {
                Api.postJson("/api/ingest/exercise", body)
                db.exercise().mark(e.id, e.end, 1)
            } catch (err: HttpError) {
                if (err.code == 400 || err.code == 422) db.exercise().mark(e.id, e.end, 2) else throw err
            }
        }
        // Behåll en vecka lokalt för appens egna vyer, rensa äldre uppladdade rader.
        db.samples().prune(System.currentTimeMillis() / 1000.0 - 7 * 86400)
        Prefs.link { it.copy(lastUploadAt = System.currentTimeMillis(), lastUploadError = null) }
        total
    }

    private suspend fun sendWithBisect(ctx: Context, rows: List<SampleRow>): Int {
        val dao = KonsilietDb.get(ctx).samples()
        val source = rows.first().source
        try {
            post(source, rows)
            dao.mark(source, rows.first().id, rows.last().id, 1)
            return rows.size
        } catch (e: HttpError) {
            if (e.code != 400 && e.code != 422) throw e
            if (rows.size == 1) {
                Log.w(TAG, "servern avvisade rad ${rows[0]}: ${e.message}")
                dao.reject(rows[0].id)
                return 0
            }
            val half = rows.size / 2
            return sendWithBisect(ctx, rows.subList(0, half)) + sendWithBisect(ctx, rows.subList(half, rows.size))
        }
    }

    private suspend fun post(source: String, rows: List<SampleRow>) {
        val samples = JSONArray()
        for (r in rows) samples.put(JSONObject().put("ts", r.ts).put("metric", r.metric).put("value", r.value))
        Api.postJson("/api/ingest", JSONObject().put("source", source).put("samples", samples))
    }
}

object UploadScheduler {
    private val net = Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build()

    /** Kör så snart det finns nät. KEEP: pågår redan en körning tömmer den kön ändå. */
    fun now(ctx: Context) {
        WorkManager.getInstance(ctx).enqueueUniqueWork(
            "upload", ExistingWorkPolicy.KEEP,
            OneTimeWorkRequestBuilder<UploadWorker>()
                .setConstraints(net)
                .setBackoffCriteria(BackoffPolicy.EXPONENTIAL, 20, TimeUnit.SECONDS)
                .build()
        )
    }

    /** Skyddsnät var 15:e minut. Överlever omstart (WorkManager sparar sina jobb). */
    fun periodic(ctx: Context) {
        WorkManager.getInstance(ctx).enqueueUniquePeriodicWork(
            "upload-periodic", ExistingPeriodicWorkPolicy.KEEP,
            PeriodicWorkRequestBuilder<UploadWorker>(15, TimeUnit.MINUTES).setConstraints(net).build()
        )
    }
}

class UploadWorker(ctx: Context, params: WorkerParameters) : CoroutineWorker(ctx, params) {
    override suspend fun doWork(): Result = try {
        val n = Uploader.drain(applicationContext)
        Log.d(TAG, "laddade upp $n")
        Result.success()
    } catch (e: IOException) {
        val msg = when (e) {
            is HttpError -> if (e.code == 401) "Servern nekade (401). Kontrollera enhetstoken." else e.message
            else -> "Ingen kontakt med servern (${e.javaClass.simpleName})"
        }
        Prefs.link { it.copy(lastUploadError = msg) }
        Result.retry()
    } catch (e: Exception) {
        Log.e(TAG, "oväntat fel", e)
        Prefs.link { it.copy(lastUploadError = e.message) }
        Result.retry()
    }
}
