package se.konsiliet.wear.exercise

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.util.Log
import androidx.concurrent.futures.await
import androidx.core.app.NotificationCompat
import androidx.core.app.ServiceCompat
import androidx.health.services.client.ExerciseUpdateCallback
import androidx.health.services.client.HealthServices
import androidx.health.services.client.data.Availability
import androidx.health.services.client.data.DataType
import androidx.health.services.client.data.ExerciseConfig
import androidx.health.services.client.data.ExerciseLapSummary
import androidx.health.services.client.data.ExerciseTrackedStatus
import androidx.health.services.client.data.ExerciseType
import androidx.health.services.client.data.ExerciseUpdate
import androidx.lifecycle.LifecycleService
import androidx.lifecycle.lifecycleScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import se.konsiliet.wear.R
import se.konsiliet.wear.data.Pending
import se.konsiliet.wear.data.QueueDb
import se.konsiliet.wear.data.WatchState
import se.konsiliet.wear.health.Convert
import se.konsiliet.wear.link.Flush
import se.konsiliet.wear.link.Sender
import se.konsiliet.wear.ui.MainActivity

private const val TAG = "KonsilietExercise"

/** Passtyper som erbjuds på klockan, i den ordningen. Filtreras mot vad klockan stöder. */
val EXERCISE_CHOICES = listOf(
    ExerciseType.WALKING to "Promenad",
    ExerciseType.RUNNING to "Löpning",
    ExerciseType.BIKING to "Cykling",
    ExerciseType.STRENGTH_TRAINING to "Styrka",
)

/** Namn som skickas till servern som passets typ. */
fun exerciseTypeName(id: Int): String =
    EXERCISE_CHOICES.firstOrNull { it.first.id == id }?.second?.lowercase()
        ?: ExerciseType.fromId(id).name.lowercase()

/**
 * Träningspass med ExerciseClient: puls med hög upplösning (ungefär varje sekund) i stället för
 * passiva lägets glesa punkter. Körs som förgrundstjänst av typen health, vilket krävs för att
 * Health Services ska fortsätta leverera när skärmen släcks.
 */
class ExerciseService : LifecycleService() {

    companion object {
        const val ACTION_START = "se.konsiliet.wear.START"
        const val ACTION_STOP = "se.konsiliet.wear.STOP"
        const val EXTRA_TYPE = "type"
        private const val NOTIF_ID = 10
        private const val CHANNEL = "pass"

        val message = MutableStateFlow<String?>(null)

        fun start(ctx: Context, type: ExerciseType) {
            ctx.startForegroundService(Intent(ctx, ExerciseService::class.java)
                .setAction(ACTION_START).putExtra(EXTRA_TYPE, type.id))
        }

        fun stop(ctx: Context) {
            ctx.startService(Intent(ctx, ExerciseService::class.java).setAction(ACTION_STOP))
        }
    }

    private val client by lazy { HealthServices.getClient(this).exerciseClient }
    private var flusher: Job? = null

    private val callback = object : ExerciseUpdateCallback {
        override fun onExerciseUpdateReceived(update: ExerciseUpdate) {
            val boot = Convert.bootInstant()
            val rows = update.latestMetrics.getData(DataType.HEART_RATE_BPM)
                .filter { it.value > 0 }
                .map { Pending(metric = "hr", ts = Convert.seconds(it.getTimeInstant(boot)), value = it.value) }
            if (rows.isNotEmpty()) {
                lifecycleScope.launch(Dispatchers.IO) { QueueDb.get(applicationContext).pending().insert(rows) }
                val last = rows.maxBy { it.ts }
                WatchState.noteHr(last.value, (last.ts * 1000).toLong())
            }
            if (update.exerciseStateInfo.state.isEnded) {
                val total = update.latestMetrics.getData(DataType.CALORIES_TOTAL)?.total
                finish(total)
            }
        }

        override fun onLapSummaryReceived(lapSummary: ExerciseLapSummary) {}
        override fun onRegistered() {}
        override fun onRegistrationFailed(throwable: Throwable) {
            Log.w(TAG, "registrering av callback misslyckades", throwable)
        }
        override fun onAvailabilityChanged(dataType: DataType<*, *>, availability: Availability) {}
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        super.onStartCommand(intent, flags, startId)
        when (intent?.action) {
            ACTION_STOP -> lifecycleScope.launch {
                runCatching { client.endExerciseAsync().await() }.onFailure {
                    Log.w(TAG, "kunde inte avsluta", it); finish(null)
                }
            }
            else -> {
                goForeground()
                val typeId = intent?.getIntExtra(EXTRA_TYPE, ExerciseType.WALKING.id) ?: ExerciseType.WALKING.id
                lifecycleScope.launch { begin(ExerciseType.fromId(typeId)) }
            }
        }
        return START_NOT_STICKY
    }

    private suspend fun begin(type: ExerciseType) {
        try {
            val info = client.getCurrentExerciseInfoAsync().await()
            when (info.exerciseTrackedStatus) {
                ExerciseTrackedStatus.OTHER_APP_IN_PROGRESS -> {
                    message.value = "En annan app har redan ett pass igång."
                    stopSelf(); return
                }
                ExerciseTrackedStatus.OWNED_EXERCISE_IN_PROGRESS -> {
                    // Processen har startats om mitt i ett pass: koppla bara på igen.
                    client.setUpdateCallback(callback)
                    WatchState.noteExercise(true)
                    startFlusher(); return
                }
            }
            val caps = client.getCapabilitiesAsync().await()
            val typeCaps = caps.getExerciseTypeCapabilities(type)
            val wanted = setOf<DataType<*, *>>(DataType.HEART_RATE_BPM, DataType.CALORIES_TOTAL)
                .filter { it in typeCaps.supportedDataTypes }.toSet()
            val config = ExerciseConfig.builder(type)
                .setDataTypes(wanted)
                .setIsAutoPauseAndResumeEnabled(false)
                .setIsGpsEnabled(false)
                .build()
            client.setUpdateCallback(callback)
            client.startExerciseAsync(config).await()
            WatchState.noteExercise(true)
            message.value = null
            val now = System.currentTimeMillis() / 1000.0
            QueueDb.get(applicationContext).pending().insert(
                listOf(Pending(metric = "exercise", ts = now, value = type.id.toDouble()))
            )
            startFlusher()
        } catch (e: Exception) {
            Log.w(TAG, "kunde inte starta pass", e)
            message.value = "Kunde inte starta passet: ${e.message}"
            WatchState.noteExercise(false)
            stopSelf()
        }
    }

    /** Under passet skickas pulsen var 15:e sekund så att mobilen och servern ser den nästan live. */
    private fun startFlusher() {
        flusher?.cancel()
        flusher = lifecycleScope.launch(Dispatchers.IO) {
            while (isActive) {
                runCatching { Sender.flush(applicationContext) }
                delay(15_000)
            }
        }
    }

    private fun finish(caloriesTotal: Double?) {
        flusher?.cancel()
        lifecycleScope.launch(Dispatchers.IO) {
            val now = System.currentTimeMillis() / 1000.0
            val rows = buildList {
                add(Pending(metric = "exercise", ts = now, value = 0.0))
                if (caloriesTotal != null) add(Pending(metric = "exercise_calories", ts = now, value = caloriesTotal))
            }
            QueueDb.get(applicationContext).pending().insert(rows)
            runCatching { client.clearUpdateCallbackAsync(callback).await() }
            WatchState.noteExercise(false)
            Flush.request(applicationContext, urgent = true)
            ServiceCompat.stopForeground(this@ExerciseService, ServiceCompat.STOP_FOREGROUND_REMOVE)
            stopSelf()
        }
    }

    private fun goForeground() {
        val nm = getSystemService(NotificationManager::class.java)
        nm.createNotificationChannel(NotificationChannel(CHANNEL, "Träningspass", NotificationManager.IMPORTANCE_LOW))
        val open = PendingIntent.getActivity(this, 0, Intent(this, MainActivity::class.java), PendingIntent.FLAG_IMMUTABLE)
        val n: Notification = NotificationCompat.Builder(this, CHANNEL)
            .setSmallIcon(R.drawable.ic_stat)
            .setContentTitle("Träningspass pågår")
            .setContentText("Puls registreras och skickas till mobilen")
            .setOngoing(true)
            .setContentIntent(open)
            .setCategory(NotificationCompat.CATEGORY_WORKOUT)
            .build()
        ServiceCompat.startForeground(this, NOTIF_ID, n, ServiceInfo.FOREGROUND_SERVICE_TYPE_HEALTH)
    }
}
