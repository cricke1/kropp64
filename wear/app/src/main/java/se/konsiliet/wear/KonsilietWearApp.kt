package se.konsiliet.wear

import android.app.Application
import androidx.work.ExistingWorkPolicy
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.WorkManager
import se.konsiliet.wear.data.WatchState
import se.konsiliet.wear.health.RegisterWorker
import se.konsiliet.wear.link.Flush

class KonsilietWearApp : Application() {
    override fun onCreate() {
        super.onCreate()
        WatchState.init(this)
        Flush.schedulePeriodic(this)
    }

    fun reregister() {
        WorkManager.getInstance(this).enqueueUniqueWork(
            "register", ExistingWorkPolicy.REPLACE, OneTimeWorkRequestBuilder<RegisterWorker>().build()
        )
    }
}
