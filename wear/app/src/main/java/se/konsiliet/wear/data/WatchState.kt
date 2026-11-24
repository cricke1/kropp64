package se.konsiliet.wear.data

import android.content.Context
import android.content.SharedPreferences
import android.os.Build
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

/** Det klockans skärm visar. Sparas i SharedPreferences så att det överlever processdöd. */
data class Status(
    val lastHr: Double? = null,
    val lastHrAt: Long = 0,
    val lastSentAt: Long = 0,
    val lastSentCount: Int = 0,
    val lastError: String? = null,
    val registered: String? = null,
    val exerciseActive: Boolean = false,
    val exerciseStartedAt: Long = 0,
)

object WatchState {
    private lateinit var prefs: SharedPreferences
    private val _status = MutableStateFlow(Status())
    val status: StateFlow<Status> = _status.asStateFlow()

    /**
     * Källa som följer med varje batch. På en emulator är all data syntetisk (Health Services
     * testläge) och märks därför tydligt, så att den aldrig kan misstas för riktiga mätningar.
     */
    val source: String by lazy { if (isEmulator()) "watch-emulator" else "watch" }

    fun init(ctx: Context) {
        prefs = ctx.getSharedPreferences("watch_state", Context.MODE_PRIVATE)
        _status.value = Status(
            lastHr = prefs.getFloat("lastHr", -1f).takeIf { it >= 0 }?.toDouble(),
            lastHrAt = prefs.getLong("lastHrAt", 0),
            lastSentAt = prefs.getLong("lastSentAt", 0),
            lastSentCount = prefs.getInt("lastSentCount", 0),
            lastError = prefs.getString("lastError", null),
            registered = prefs.getString("registered", null),
            exerciseActive = prefs.getBoolean("exerciseActive", false),
            exerciseStartedAt = prefs.getLong("exerciseStartedAt", 0),
        )
    }

    private fun update(f: (Status) -> Status, save: SharedPreferences.Editor.(Status) -> Unit) {
        synchronized(this) {
            val s = f(_status.value)
            _status.value = s
            prefs.edit().apply { save(s) }.apply()
        }
    }

    fun noteHr(bpm: Double, atMillis: Long) {
        if (atMillis < _status.value.lastHrAt) return
        update({ it.copy(lastHr = bpm, lastHrAt = atMillis) }) {
            putFloat("lastHr", bpm.toFloat()); putLong("lastHrAt", atMillis)
        }
    }

    fun noteSent(count: Int) = update({ it.copy(lastSentAt = System.currentTimeMillis(), lastSentCount = count, lastError = null) }) {
        putLong("lastSentAt", it.lastSentAt); putInt("lastSentCount", count); remove("lastError")
    }

    fun noteError(msg: String?) = update({ it.copy(lastError = msg) }) {
        if (msg == null) remove("lastError") else putString("lastError", msg)
    }

    fun noteRegistered(desc: String) = update({ it.copy(registered = desc) }) { putString("registered", desc) }

    fun noteExercise(active: Boolean) = update({
        it.copy(exerciseActive = active, exerciseStartedAt = if (active) System.currentTimeMillis() else 0)
    }) {
        putBoolean("exerciseActive", it.exerciseActive); putLong("exerciseStartedAt", it.exerciseStartedAt)
    }

    fun isEmulator(): Boolean =
        Build.FINGERPRINT.contains("generic") || Build.FINGERPRINT.contains("emulator") ||
            Build.HARDWARE.contains("ranchu") || Build.HARDWARE.contains("goldfish") ||
            Build.PRODUCT.contains("sdk")
}
