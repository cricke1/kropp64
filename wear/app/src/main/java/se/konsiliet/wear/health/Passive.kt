package se.konsiliet.wear.health

import android.Manifest
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.util.Log
import androidx.concurrent.futures.await
import androidx.core.content.ContextCompat
import androidx.health.services.client.HealthServices
import androidx.health.services.client.PassiveListenerService
import androidx.health.services.client.data.DataPointContainer
import androidx.health.services.client.data.DataType
import androidx.health.services.client.data.HealthEvent
import androidx.health.services.client.data.PassiveListenerConfig
import androidx.health.services.client.data.UserActivityInfo
import androidx.work.CoroutineWorker
import androidx.work.ExistingWorkPolicy
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.runBlocking
import se.konsiliet.wear.data.Pending
import se.konsiliet.wear.data.QueueDb
import se.konsiliet.wear.data.WatchState
import se.konsiliet.wear.link.Flush

private const val TAG = "KonsilietPassive"

object Permissions {
    /** Pulsbehörigheten heter olika före och efter Wear OS 6 (API 36). */
    val heartRate: String
        get() = if (Build.VERSION.SDK_INT >= 36) "android.permission.health.READ_HEART_RATE" else Manifest.permission.BODY_SENSORS

    val background: String
        get() = if (Build.VERSION.SDK_INT >= 36) "android.permission.health.READ_HEALTH_DATA_IN_BACKGROUND" else Manifest.permission.BODY_SENSORS_BACKGROUND

    fun foreground(): Array<String> = buildList {
        add(heartRate)
        add(Manifest.permission.ACTIVITY_RECOGNITION)
        if (Build.VERSION.SDK_INT >= 33) add(Manifest.permission.POST_NOTIFICATIONS)
    }.toTypedArray()

    fun has(ctx: Context, p: String) = ContextCompat.checkSelfPermission(ctx, p) == PackageManager.PERMISSION_GRANTED
}

object Passive {
    /**
     * Registrerar alla datatyper som klockan faktiskt kan leverera passivt och som vi har behörighet för.
     * Vilka typer som finns varierar mellan klockmodeller och Wear OS-versioner, så de läses vid körning.
     */
    suspend fun register(ctx: Context): String {
        val client = HealthServices.getClient(ctx).passiveMonitoringClient
        val caps = client.getCapabilitiesAsync().await()
        val hasHr = Permissions.has(ctx, Permissions.heartRate)
        val hasAct = Permissions.has(ctx, Manifest.permission.ACTIVITY_RECOGNITION)

        val types = caps.supportedDataTypesPassiveMonitoring.filter { t ->
            if (t == DataType.HEART_RATE_BPM) hasHr else hasAct
        }.toSet()
        val events = caps.supportedHealthEventTypes.filter { it == HealthEvent.Type.FALL_DETECTED }.toSet()
        val activity = hasAct && caps.supportedUserActivityStates.isNotEmpty()

        val config = PassiveListenerConfig.builder()
            .setDataTypes(types)
            .setShouldUserActivityInfoBeRequested(activity)
            .setHealthEventTypes(if (hasHr) events else emptySet())
            .build()
        client.setPassiveListenerServiceAsync(PassiveDataService::class.java, config).await()

        val desc = (types.map { Convert.metricName(it) } +
            (if (activity) listOf("activity_state") else emptyList()) +
            (if (hasHr && events.isNotEmpty()) listOf("fall_detected") else emptyList())).sorted().joinToString(", ")
        Log.i(TAG, "registrerade passivt: $desc")
        WatchState.noteRegistered(desc)
        return desc
    }

    /** Alla typer klockan erbjuder, oavsett behörighet. Visas på skärmen för felsökning. */
    suspend fun available(ctx: Context): List<String> {
        val caps = HealthServices.getClient(ctx).passiveMonitoringClient.getCapabilitiesAsync().await()
        return caps.supportedDataTypesPassiveMonitoring.map { Convert.metricName(it) }.sorted()
    }
}

class PassiveDataService : PassiveListenerService() {

    private fun store(rows: List<Pending>, urgent: Boolean = false) {
        if (rows.isEmpty()) return
        // Callbacken kommer på en tråd vi inte äger och tjänsten kan avbindas direkt efteråt,
        // så skrivningen görs klart innan vi returnerar. En Room-insert tar millisekunder.
        runBlocking(Dispatchers.IO) { QueueDb.get(applicationContext).pending().insert(rows) }
        rows.filter { it.metric == "hr" }.maxByOrNull { it.ts }?.let {
            WatchState.noteHr(it.value, (it.ts * 1000).toLong())
            se.konsiliet.wear.link.Surfaces.updateHr(applicationContext)
        }
        Flush.request(applicationContext, urgent)
    }

    override fun onNewDataPointsReceived(dataPoints: DataPointContainer) {
        store(Convert.fromContainer(dataPoints))
    }

    override fun onUserActivityInfoReceived(info: UserActivityInfo) {
        store(listOf(Pending(metric = "activity_state", ts = Convert.seconds(info.stateChangeTime),
            value = Convert.activityCode(info.userActivityState))))
    }

    override fun onHealthEventReceived(event: HealthEvent) {
        val metric = if (event.type == HealthEvent.Type.FALL_DETECTED) "fall_detected" else "health_event"
        store(listOf(Pending(metric = metric, ts = Convert.seconds(event.eventTime), value = 1.0)), urgent = true)
    }

    override fun onPermissionLost() {
        WatchState.noteError("Behörighet återkallad. Öppna appen på klockan.")
    }
}

/** Registrerar om passiv övervakning efter omstart och appuppdatering. */
class BootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        WorkManager.getInstance(context).enqueueUniqueWork(
            "register", ExistingWorkPolicy.REPLACE, OneTimeWorkRequestBuilder<RegisterWorker>().build()
        )
        Flush.schedulePeriodic(context)
    }
}

class RegisterWorker(ctx: Context, params: WorkerParameters) : CoroutineWorker(ctx, params) {
    override suspend fun doWork(): Result = try {
        Passive.register(applicationContext)
        Result.success()
    } catch (e: Exception) {
        Log.w(TAG, "registrering misslyckades", e)
        WatchState.noteError("Registrering misslyckades: ${e.message}")
        Result.retry()
    }
}
