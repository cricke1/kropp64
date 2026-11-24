package se.konsiliet.wear

import android.app.Application
import androidx.work.ExistingWorkPolicy
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.WorkManager
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch
import se.konsiliet.wear.alerts.Haptics
import se.konsiliet.wear.data.PhoneStatus
import se.konsiliet.wear.data.WatchState
import se.konsiliet.wear.link.Incoming
import se.konsiliet.wear.health.RegisterWorker
import se.konsiliet.wear.link.Flush

class KonsilietWearApp : Application() {
    override fun onCreate() {
        super.onCreate()
        WatchState.init(this)
        PhoneStatus.init(this)
        se.konsiliet.wear.exercise.PassLogg.init(this)
        Haptics.channels(this)
        Flush.schedulePeriodic(this)
        // Om en statusleverans missades medan processen var död finns den kvar i Data Layer.
        CoroutineScope(SupervisorJob() + Dispatchers.IO).launch { Incoming.pull(this@KonsilietWearApp) }
    }

    fun reregister() {
        WorkManager.getInstance(this).enqueueUniqueWork(
            "register", ExistingWorkPolicy.REPLACE, OneTimeWorkRequestBuilder<RegisterWorker>().build()
        )
    }
}
