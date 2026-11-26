package se.konsiliet.app.hc

import android.app.AppOpsManager
import android.app.usage.UsageEvents
import android.app.usage.UsageStatsManager
import android.content.Context
import android.content.Intent
import android.content.pm.ApplicationInfo
import android.content.pm.PackageManager
import android.os.Process
import android.provider.Settings
import se.konsiliet.app.data.KonsilietDb
import se.konsiliet.app.data.Prefs
import se.konsiliet.app.data.SampleRow

/**
 * Skärmtid på mobilen, samma modell som datorn på Mac minin: en mätpunkt per minut och kategori
 * (mobil_spel, mobil_sociala, mobil_video, mobil_chatt, mobil_webb, mobil_annat, värde 1 = appen låg i
 * förgrunden den minuten). Då kan läkarteamet se puls och sömn bredvid sena kvällar med mobilen, precis
 * som med datorn.
 *
 * Bara kategorin sparas, aldrig vilken app. Kräver "Åtkomst till användning", som användaren slår på
 * själv i Inställningar (knapp i appen).
 */
object Skarmtid {
    const val SOURCE = "mobil"
    val KATEGORIER = listOf("spel", "sociala", "video", "chatt", "webb", "annat")

    private val CHATT = listOf("whatsapp", "com.facebook.orca", "telegram", "discord", "thoughtcrime.securesms", "org.signal",
        "apps.messaging", "android.messaging", "com.samsung.android.messaging", "com.microsoft.teams", "slack")
    private val SOCIALA = listOf("instagram", "snapchat", "tiktok", "musically", "com.facebook.katana", "twitter", "reddit",
        "com.zhiliaoapp", "threads", "bereal", "pinterest", "tumblr")
    private val VIDEO = listOf("youtube", "netflix", "twitch", "hbo", "disney", "svtplay", "tv4", "primevideo", "viaplay", "spotify")
    private val WEBB = listOf("chrome", "firefox", "sbrowser", "opera", "brave", "duckduckgo", "edge", "vivaldi")

    fun harBehorighet(ctx: Context): Boolean {
        val ops = ctx.getSystemService(AppOpsManager::class.java)
        return ops.unsafeCheckOpNoThrow(AppOpsManager.OPSTR_GET_USAGE_STATS, Process.myUid(), ctx.packageName) ==
            AppOpsManager.MODE_ALLOWED
    }

    fun oppnaInstallning(ctx: Context) {
        ctx.startActivity(Intent(Settings.ACTION_USAGE_ACCESS_SETTINGS).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
    }

    private fun kategori(pm: PackageManager, pkg: String): String? {
        val p = pkg.lowercase()
        if (CHATT.any { p.contains(it) }) return "chatt"
        if (SOCIALA.any { p.contains(it) }) return "sociala"
        if (VIDEO.any { p.contains(it) }) return "video"
        if (WEBB.any { p.contains(it) }) return "webb"
        val info = runCatching { pm.getApplicationInfo(pkg, 0) }.getOrNull() ?: return "annat"
        return when (info.category) {
            ApplicationInfo.CATEGORY_GAME -> "spel"
            ApplicationInfo.CATEGORY_SOCIAL -> "sociala"
            ApplicationInfo.CATEGORY_VIDEO, ApplicationInfo.CATEGORY_AUDIO -> "video"
            else -> "annat"
        }
    }

    /** Läser förgrundshändelser sedan förra körningen (högst 3 dygn bakåt) och sparar minuterna. */
    suspend fun run(ctx: Context): Int {
        if (!harBehorighet(ctx)) return 0
        val nu = System.currentTimeMillis()
        val fran = maxOf(Prefs.getLong("skarmtid_ts") - 10 * 60_000L, nu - 3 * 86_400_000L)
        val usm = ctx.getSystemService(UsageStatsManager::class.java)
        val pm = ctx.packageManager
        // Hemskärmen, systemgränssnittet och Kropp64 själv räknas inte som skärmtid i någon kategori.
        val hem = pm.resolveActivity(Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_HOME), 0)?.activityInfo?.packageName
        val ignorera = setOf(ctx.packageName, "com.android.systemui", hem)
        val ev = usm.queryEvents(fran, nu)
        val e = UsageEvents.Event()
        val oppen = HashMap<String, Long>()
        val minuter = HashMap<Pair<Long, String>, Boolean>()
        val katCache = HashMap<String, String?>()
        fun stang(pkg: String, slut: Long) {
            val start = oppen.remove(pkg) ?: return
            if (pkg in ignorera || slut <= start) return
            val kat = katCache.getOrPut(pkg) { kategori(pm, pkg) } ?: return
            var m = start / 60_000L
            while (m * 60_000L < slut) { minuter[m to kat] = true; m++ }
        }
        while (ev.hasNextEvent()) {
            ev.getNextEvent(e)
            when (e.eventType) {
                UsageEvents.Event.ACTIVITY_RESUMED -> oppen.putIfAbsent(e.packageName, e.timeStamp)
                UsageEvents.Event.ACTIVITY_PAUSED, UsageEvents.Event.ACTIVITY_STOPPED -> stang(e.packageName, e.timeStamp)
                UsageEvents.Event.SCREEN_NON_INTERACTIVE -> oppen.keys.toList().forEach { stang(it, e.timeStamp) }
            }
        }
        // Appen som ligger öppen just nu räknas fram till nu.
        oppen.keys.toList().forEach { stang(it, nu) }
        val rows = minuter.keys.map { (m, kat) -> SampleRow(metric = "mobil_$kat", ts = m * 60.0, value = 1.0, source = SOURCE) }
        val db = KonsilietDb.get(ctx)
        val n = rows.chunked(500).sumOf { c -> db.samples().insert(c).count { it != -1L } }
        Prefs.putLong("skarmtid_ts", nu)
        return n
    }
}
