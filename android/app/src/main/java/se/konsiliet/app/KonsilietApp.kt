package se.konsiliet.app

import android.app.Application
import se.konsiliet.app.alerts.Channels
import se.konsiliet.app.data.Prefs
import se.konsiliet.app.hc.HcScheduler
import se.konsiliet.app.link.UploadScheduler

class KonsilietApp : Application() {
    override fun onCreate() {
        super.onCreate()
        Prefs.init(this)
        Channels.create(this)
        UploadScheduler.periodic(this)
        HcScheduler.periodic(this)
        // Det som låg i kön när processen dog laddas upp direkt vid nästa start.
        UploadScheduler.now(this)
    }
}
