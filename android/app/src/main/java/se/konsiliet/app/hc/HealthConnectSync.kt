package se.konsiliet.app.hc

import android.content.Context
import android.util.Log
import androidx.health.connect.client.HealthConnectClient
import androidx.health.connect.client.HealthConnectFeatures
import androidx.health.connect.client.changes.UpsertionChange
import androidx.health.connect.client.permission.HealthPermission
import androidx.health.connect.client.records.ExerciseSessionRecord
import androidx.health.connect.client.records.HeartRateRecord
import androidx.health.connect.client.records.HeartRateVariabilityRmssdRecord
import androidx.health.connect.client.records.OxygenSaturationRecord
import androidx.health.connect.client.records.Record
import androidx.health.connect.client.records.RespiratoryRateRecord
import androidx.health.connect.client.records.RestingHeartRateRecord
import androidx.health.connect.client.records.SkinTemperatureRecord
import androidx.health.connect.client.records.SleepSessionRecord
import androidx.health.connect.client.records.StepsRecord
import androidx.health.connect.client.request.ChangesTokenRequest
import androidx.health.connect.client.request.ReadRecordsRequest
import androidx.health.connect.client.time.TimeRangeFilter
import androidx.work.Constraints
import androidx.work.CoroutineWorker
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.ExistingWorkPolicy
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import java.time.Instant
import java.time.temporal.ChronoUnit
import java.util.concurrent.TimeUnit
import kotlin.reflect.KClass
import org.json.JSONArray
import org.json.JSONObject
import se.konsiliet.app.data.KonsilietDb
import se.konsiliet.app.data.Prefs
import se.konsiliet.app.data.SampleRow
import se.konsiliet.app.data.SleepRow
import se.konsiliet.app.link.UploadScheduler

private const val TAG = "KonsilietHC"
private const val SOURCE = "health_connect"

/**
 * Health Connect som andra källa: det Fitbit-appen och Pixel Watch skriver dit (sömn med faser,
 * HRV, vilopuls, SpO2, hudtemperatur, andningsfrekvens, träningspass) plus puls och steg för historik.
 *
 * Första körningen: hämta ändringstoken FÖRST (så att inget som skrivs under bakåtläsningen missas),
 * läs sedan bakåt en vecka i taget tills åtta veckor i rad är tomma. Utan historikbehörighet ger
 * Health Connect bara de senaste 30 dagarna, med den ger den allt som finns.
 * Därefter: inkrementellt med getChanges. Har token gått ut (efter 30 dagar utan körning) läses
 * de senaste 30 dagarna om och en ny token hämtas. Servern avduplicerar på (metric, ts, source).
 */
object HealthConnectSync {

    val recordTypes: List<KClass<out Record>> = listOf(
        HeartRateRecord::class,
        HeartRateVariabilityRmssdRecord::class,
        RestingHeartRateRecord::class,
        OxygenSaturationRecord::class,
        SkinTemperatureRecord::class,
        RespiratoryRateRecord::class,
        SleepSessionRecord::class,
        ExerciseSessionRecord::class,
        StepsRecord::class,
    )

    val permissions: Set<String> = recordTypes.map { HealthPermission.getReadPermission(it) }.toSet() +
        HealthPermission.PERMISSION_READ_HEALTH_DATA_HISTORY +
        HealthPermission.PERMISSION_READ_HEALTH_DATA_IN_BACKGROUND

    private const val WEEK_S = 7L * 86400
    private const val EMPTY_WEEKS_TO_STOP = 8
    private const val WEEKS_PER_RUN = 12

    fun available(ctx: Context): Boolean =
        HealthConnectClient.getSdkStatus(ctx) == HealthConnectClient.SDK_AVAILABLE

    suspend fun granted(ctx: Context): Set<String> =
        HealthConnectClient.getOrCreate(ctx).permissionController.getGrantedPermissions()

    /** Typer vi både har behörighet för och som finns på enheten. */
    private suspend fun readable(client: HealthConnectClient, granted: Set<String>): List<KClass<out Record>> =
        recordTypes.filter { HealthPermission.getReadPermission(it) in granted }.filter {
            it != SkinTemperatureRecord::class || client.features.getFeatureStatus(
                HealthConnectFeatures.FEATURE_SKIN_TEMPERATURE) == HealthConnectFeatures.FEATURE_STATUS_AVAILABLE
        }

    suspend fun run(ctx: Context): String {
        if (!available(ctx)) return "Health Connect finns inte på enheten"
        val client = HealthConnectClient.getOrCreate(ctx)
        val granted = granted(ctx)
        val types = readable(client, granted)
        if (types.isEmpty()) return "Ingen behörighet till Health Connect ännu"
        val typesKey = types.joinToString(",") { it.simpleName ?: "" }

        // Ny uppsättning typer (t.ex. fler behörigheter) betyder ny token och ny bakåtläsning.
        if (Prefs.getString("hc_types") != typesKey) {
            Prefs.putString("hc_types", typesKey)
            Prefs.putString("hc_token", client.getChangesToken(ChangesTokenRequest(types.toSet())))
            Prefs.putLong("hc_cursor", Instant.now().epochSecond)
            Prefs.putLong("hc_empty_weeks", 0)
            Prefs.putBool("hc_backfill_done", false)
        }

        var stored = 0
        stored += incremental(ctx, client, types)
        if (!Prefs.getBool("hc_backfill_done")) stored += backfill(ctx, client, types)

        val status = if (Prefs.getBool("hc_backfill_done")) "Historik inläst. $stored nya punkter senast."
        else "Läser historik, framme vid ${java.time.LocalDate.ofEpochDay(Prefs.getLong("hc_cursor") / 86400)}"
        Prefs.link { it.copy(lastHcSyncAt = System.currentTimeMillis(), hcStatus = status) }
        if (stored > 0) UploadScheduler.now(ctx)
        return status
    }

    private suspend fun incremental(ctx: Context, client: HealthConnectClient, types: List<KClass<out Record>>): Int {
        var token = Prefs.getString("hc_token") ?: return 0
        var stored = 0
        while (true) {
            val resp = client.getChanges(token)
            if (resp.changesTokenExpired) {
                Log.i(TAG, "ändringstoken utgången, läser om 30 dagar")
                val now = Instant.now()
                for (t in types) stored += readRange(ctx, client, t, now.minus(30, ChronoUnit.DAYS), now)
                token = client.getChangesToken(ChangesTokenRequest(types.toSet()))
                break
            }
            val records = resp.changes.filterIsInstance<UpsertionChange>().map { it.record }
            stored += persist(ctx, records)
            token = resp.nextChangesToken
            if (!resp.hasMore) break
        }
        Prefs.putString("hc_token", token)
        return stored
    }

    private suspend fun backfill(ctx: Context, client: HealthConnectClient, types: List<KClass<out Record>>): Int {
        var cursor = Prefs.getLong("hc_cursor", Instant.now().epochSecond)
        var empty = Prefs.getLong("hc_empty_weeks", 0)
        var stored = 0
        repeat(WEEKS_PER_RUN) {
            val end = Instant.ofEpochSecond(cursor)
            val start = Instant.ofEpochSecond(cursor - WEEK_S)
            var n = 0
            for (t in types) n += readRange(ctx, client, t, start, end)
            stored += n
            empty = if (n == 0) empty + 1 else 0
            cursor -= WEEK_S
            Prefs.putLong("hc_cursor", cursor)
            Prefs.putLong("hc_empty_weeks", empty)
            if (empty >= EMPTY_WEEKS_TO_STOP) {
                Prefs.putBool("hc_backfill_done", true)
                return stored
            }
        }
        return stored
    }

    private suspend fun readRange(ctx: Context, client: HealthConnectClient, type: KClass<out Record>, start: Instant, end: Instant): Int {
        var page: String? = null
        var n = 0
        do {
            val resp = client.readRecords(ReadRecordsRequest(type, TimeRangeFilter.between(start, end),
                pageSize = 5000, pageToken = page))
            n += persist(ctx, resp.records)
            page = resp.pageToken
        } while (page != null)
        return n
    }

    private fun s(i: Instant) = i.epochSecond + i.nano / 1e9

    private suspend fun persist(ctx: Context, records: List<Record>): Int {
        if (records.isEmpty()) return 0
        val rows = ArrayList<SampleRow>()
        val sleeps = ArrayList<SleepRow>()
        fun add(metric: String, t: Instant, v: Double) {
            if (!v.isNaN() && !v.isInfinite()) rows += SampleRow(metric = metric, ts = s(t), value = v, source = SOURCE)
        }
        for (r in records) when (r) {
            is HeartRateRecord -> r.samples.forEach { add("hr", it.time, it.beatsPerMinute.toDouble()) }
            is HeartRateVariabilityRmssdRecord -> add("hrv_rmssd", r.time, r.heartRateVariabilityMillis)
            is RestingHeartRateRecord -> add("hr_resting", r.time, r.beatsPerMinute.toDouble())
            is OxygenSaturationRecord -> add("spo2", r.time, r.percentage.value)
            is RespiratoryRateRecord -> add("resp_rate", r.time, r.rate)
            is SkinTemperatureRecord -> {
                // Pixel Watch/Fitbit skriver oftast bara avvikelse mot baslinjen. Absolut temperatur
                // och avvikelse hålls isär så att de aldrig blandas i samma serie.
                val base = r.baseline?.inCelsius
                r.deltas.forEach { d ->
                    if (base != null) add("skin_temp", d.time, base + d.delta.inCelsius)
                    else add("skin_temp_delta", d.time, d.delta.inCelsius)
                }
            }
            is StepsRecord -> add("steps", r.endTime, r.count.toDouble())
            is ExerciseSessionRecord -> {
                add("exercise_minutes", r.endTime, (r.endTime.epochSecond - r.startTime.epochSecond) / 60.0)
                add("exercise_type_hc", r.startTime, r.exerciseType.toDouble())
            }
            is SleepSessionRecord -> {
                val stages = JSONArray()
                r.stages.sortedBy { it.startTime }.forEach {
                    stages.put(JSONObject().put("start", s(it.startTime)).put("end", s(it.endTime)).put("stage", stageName(it.stage)))
                }
                sleeps += SleepRow(id = "hc-" + r.metadata.id, start = s(r.startTime), end = s(r.endTime),
                    stages = stages.toString(), source = SOURCE)
            }
            else -> {}
        }
        val db = KonsilietDb.get(ctx)
        val inserted = rows.chunked(500).sumOf { chunk -> db.samples().insert(chunk).count { it != -1L } }
        if (sleeps.isNotEmpty()) db.sleep().upsert(sleeps)
        return inserted + sleeps.size
    }

    private fun stageName(s: Int): String = when (s) {
        SleepSessionRecord.STAGE_TYPE_AWAKE, SleepSessionRecord.STAGE_TYPE_AWAKE_IN_BED,
        SleepSessionRecord.STAGE_TYPE_OUT_OF_BED -> "awake"
        SleepSessionRecord.STAGE_TYPE_LIGHT -> "light"
        SleepSessionRecord.STAGE_TYPE_DEEP -> "deep"
        SleepSessionRecord.STAGE_TYPE_REM -> "rem"
        SleepSessionRecord.STAGE_TYPE_SLEEPING -> "sleeping"
        else -> "unknown"
    }
}

object HcScheduler {
    fun periodic(ctx: Context) {
        WorkManager.getInstance(ctx).enqueueUniquePeriodicWork(
            "hc-periodic", ExistingPeriodicWorkPolicy.KEEP,
            PeriodicWorkRequestBuilder<HcWorker>(30, TimeUnit.MINUTES).build()
        )
    }

    fun now(ctx: Context) {
        WorkManager.getInstance(ctx).enqueueUniqueWork(
            "hc-now", ExistingWorkPolicy.KEEP, OneTimeWorkRequestBuilder<HcWorker>().setConstraints(Constraints.NONE).build()
        )
    }

    /** Under bakåtläsningen: fortsätt så snart förra omgången är klar, i stället för att vänta 30 min. */
    fun maybeRunSoon(ctx: Context) {
        if (!Prefs.getBool("hc_backfill_done") && Prefs.getString("hc_types") != null) now(ctx)
    }
}

class HcWorker(ctx: Context, params: WorkerParameters) : CoroutineWorker(ctx, params) {
    override suspend fun doWork(): Result = try {
        HealthConnectSync.run(applicationContext)
        Result.success()
    } catch (e: Exception) {
        Log.w(TAG, "synk misslyckades", e)
        Prefs.link { it.copy(hcStatus = "Fel: ${e.javaClass.simpleName} ${e.message ?: ""}".trim()) }
        Result.retry()
    }
}
