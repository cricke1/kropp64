package se.konsiliet.app.widget

import android.content.Context
import android.util.Log
import androidx.glance.appwidget.updateAll
import androidx.work.CoroutineWorker
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.ExistingWorkPolicy
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import java.util.Calendar
import java.util.concurrent.TimeUnit
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import org.json.JSONArray
import org.json.JSONObject
import se.konsiliet.app.data.KonsilietDb
import se.konsiliet.app.data.Prefs
import se.konsiliet.app.data.isTestSource
import se.konsiliet.app.link.WatchSync
import se.konsiliet.app.net.Api

private const val TAG = "KonsilietSummary"

/**
 * Sammanfattningen som hemskärmswidgeten och klockan (tile, komplikationer) visar:
 * återhämtningspoäng med delar, dagens steg mot målet och konsiliets läge.
 *
 * Kodas som JSON (samma format sparas lokalt och skickas till klockan):
 *   v, synkad (ms), server_ok, server_at (ms, senaste lyckade hämtning),
 *   poang (0-100 eller null), poang_kommentar, delar {hrv, vilopuls, somn},
 *   konsilium {pagar, id, start, slut, bradska, sammanfattning},
 *   steg, steg_mal, steg_testdata
 *
 * Uppdateras när händelser kommer över live-länken (consult.start, consult.verdict, brief.morgon),
 * när appen öppnas och var 30:e minut med WorkManager. Hämtar servern inte behålls senaste värden
 * och server_ok blir false, så att widgeten kan visa att siffrorna är gamla.
 */
object Summary {
    private const val KEY = "summary"
    /** Ett konsilium som inte avslutats på två timmar har kraschat och räknas inte som pågående. */
    private const val MAX_RUNNING_S = 2 * 3600

    private val _state = MutableStateFlow<JSONObject?>(null)
    val state: StateFlow<JSONObject?> = _state.asStateFlow()
    private val mutex = Mutex()

    /** Händelser som ändrar det widgeten och klockan visar. */
    val KINDS = setOf("consult.start", "consult.verdict", "brief.morgon", "pass.klart", "alert.raise")

    fun load(): JSONObject? {
        _state.value?.let { return it }
        val raw = Prefs.getString(KEY) ?: return null
        return runCatching { JSONObject(raw) }.getOrNull()?.also { _state.value = it }
    }

    private fun midnight(): Double = Calendar.getInstance().apply {
        set(Calendar.HOUR_OF_DAY, 0); set(Calendar.MINUTE, 0); set(Calendar.SECOND, 0); set(Calendar.MILLISECOND, 0)
    }.timeInMillis / 1000.0

    /** Pågående och senast avslutade konsilium ur /api/consults (nyast först). */
    fun consultState(arr: JSONArray, nowS: Double): JSONObject {
        val k = JSONObject().put("pagar", false)
        for (i in 0 until arr.length()) {
            val c = arr.getJSONObject(i)
            val ended = !c.isNull("ended")
            if (i == 0 && !ended && nowS - c.optDouble("started") < MAX_RUNNING_S) {
                k.put("pagar", true).put("pagar_id", c.optString("id")).put("pagar_start", c.optDouble("started"))
                continue
            }
            if (!ended) continue
            val v = c.optJSONObject("verdict") ?: continue
            k.put("id", c.optString("id")).put("start", c.optDouble("started")).put("slut", c.optDouble("ended"))
                .put("bradska", v.optString("bradska"))
                .put("sammanfattning", v.optString("sammanfattning").take(200))
            break
        }
        return k
    }

    suspend fun refresh(ctx: Context): JSONObject = mutex.withLock {
        val now = System.currentTimeMillis()
        val out = JSONObject((load() ?: JSONObject()).toString()).put("v", 1)
        var ok = true
        runCatching { Api.getObject("/api/aterhamtning") }
            .onSuccess { a ->
                out.put("poang", if (a.isNull("poang") || !a.has("poang")) JSONObject.NULL else a.getInt("poang"))
                out.put("poang_kommentar", a.optString("kommentar"))
                out.put("delar", a.optJSONObject("delar") ?: JSONObject())
            }
            .onFailure { ok = false; Log.d(TAG, "återhämtning: ${it.message}") }
        // Dagens svar (träna, lugnt, vila) och planens pulszon, så att klockan kan visa och följa den.
        runCatching { Api.getObject("/api/idag") }
            .onSuccess { i ->
                val plan = i.optJSONObject("plan") ?: JSONObject()
                out.put("idag", JSONObject().put("beslut", i.optString("beslut")).put("rubrik", i.optString("rubrik"))
                    .put("plan", plan.optString("text")).put("typ", plan.optString("typ")).put("minuter", plan.optInt("minuter"))
                    .put("zon", plan.opt("zon") ?: JSONObject.NULL).put("puls_lo", plan.opt("puls_lo") ?: JSONObject.NULL)
                    .put("puls_hi", plan.opt("puls_hi") ?: JSONObject.NULL).put("varfor", i.optString("varfor").take(140))
                    .put("maxpuls", i.optJSONObject("zoner")?.optInt("maxpuls") ?: 0)
                    .put("pass", i.optJSONObject("veckan")?.optInt("pass") ?: 0).put("mal", i.optJSONObject("veckan")?.optInt("mal") ?: 3))
                se.konsiliet.app.ui.screens.IdagCache.save(i)
            }
            .onFailure { Log.d(TAG, "idag: ${it.message}") }
        runCatching { Api.getArray("/api/consults?limit=5") }
            .onSuccess { out.put("konsilium", consultState(it, now / 1000.0)) }
            .onFailure { ok = false; Log.d(TAG, "konsilier: ${it.message}") }

        // Steg räknas lokalt, samma regel som Idag-vyn: den källa som har flest steg idag.
        val dao = KonsilietDb.get(ctx).samples()
        val today = midnight()
        val bySource = listOf("watch", "health_connect", "watch-emulator")
            .associateWith { dao.sumSince("steps", it, today).first() }
        val best = bySource.maxByOrNull { it.value }
        out.put("steg", (best?.value ?: 0.0).toInt())
        out.put("steg_testdata", best != null && best.value > 0 && isTestSource(best.key))
        out.put("steg_mal", Prefs.config.value.stepsGoal)

        out.put("server_ok", ok)
        if (ok) out.put("server_at", now)
        out.put("synkad", now)
        Prefs.putString(KEY, out.toString())
        _state.value = out
        runCatching { KonsilietWidget().updateAll(ctx) }.onFailure { Log.w(TAG, "widget", it) }
        WatchSync.push(ctx, out.toString())
        out
    }

    /** Hämtar om efter några sekunder. Flera händelser i rad (t.ex. historik vid anslutning) blir en hämtning. */
    fun refreshSoon(ctx: Context, delaySeconds: Long = 3) {
        WorkManager.getInstance(ctx).enqueueUniqueWork(
            "summary-now", ExistingWorkPolicy.REPLACE,
            OneTimeWorkRequestBuilder<SummaryWorker>().setInitialDelay(delaySeconds, TimeUnit.SECONDS).build()
        )
    }

    /** Skyddsnät och stegräkning. 30 minuter räcker för en widget och kostar nästan inget batteri. */
    fun periodic(ctx: Context) {
        WorkManager.getInstance(ctx).enqueueUniquePeriodicWork(
            "summary-periodic", ExistingPeriodicWorkPolicy.KEEP,
            PeriodicWorkRequestBuilder<SummaryWorker>(30, TimeUnit.MINUTES).build()
        )
    }

    fun onEvent(ctx: Context, kind: String) {
        if (kind in KINDS) refreshSoon(ctx)
    }
}

class SummaryWorker(ctx: Context, params: WorkerParameters) : CoroutineWorker(ctx, params) {
    override suspend fun doWork(): Result {
        Summary.refresh(applicationContext)
        return Result.success()
    }
}
