package se.konsiliet.app.data

import android.content.Context
import android.content.SharedPreferences
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import org.json.JSONArray
import org.json.JSONObject
import se.konsiliet.app.BuildConfig

data class Contact(val name: String, val number: String)

data class Config(
    val serverUrl: String,
    val deviceToken: String,
    val smsEnabled: Boolean,
    val smsDelayMin: Int,
    val contacts: List<Contact>,
    val stepsGoal: Int,
)

/** Länkens tillstånd, för statusraden och Inställningar. */
data class LinkStatus(
    val wsConnected: Boolean = false,
    val lastWatchAt: Long = 0,
    val lastWatchSource: String? = null,
    val lastUploadAt: Long = 0,
    val lastUploadError: String? = null,
    val lastHcSyncAt: Long = 0,
    val hcStatus: String? = null,
)

object Prefs {
    private lateinit var p: SharedPreferences
    private val _config = MutableStateFlow(Config("", "", false, 5, emptyList(), 8000))
    val config: StateFlow<Config> = _config.asStateFlow()
    private val _link = MutableStateFlow(LinkStatus())
    val link: StateFlow<LinkStatus> = _link.asStateFlow()

    fun init(ctx: Context) {
        p = ctx.getSharedPreferences("konsiliet", Context.MODE_PRIVATE)
        _config.value = readConfig()
        _link.value = LinkStatus(
            lastWatchAt = p.getLong("lastWatchAt", 0),
            lastWatchSource = p.getString("lastWatchSource", null),
            lastUploadAt = p.getLong("lastUploadAt", 0),
            lastUploadError = p.getString("lastUploadError", null),
            lastHcSyncAt = p.getLong("lastHcSyncAt", 0),
            hcStatus = p.getString("hcStatus", null),
        )
    }

    private fun readConfig(): Config {
        val contacts = runCatching {
            val a = JSONArray(p.getString("contacts", "[]"))
            (0 until a.length()).map { a.getJSONObject(it).let { o -> Contact(o.getString("name"), o.getString("number")) } }
        }.getOrDefault(emptyList())
        return Config(
            serverUrl = p.getString("serverUrl", null) ?: BuildConfig.DEFAULT_SERVER,
            deviceToken = p.getString("deviceToken", "") ?: "",
            // Sms till anhöriga är avstängt tills användaren själv slår på det och lägger till kontakter.
            smsEnabled = p.getBoolean("smsEnabled", false),
            smsDelayMin = p.getInt("smsDelayMin", 5),
            contacts = contacts,
            stepsGoal = p.getInt("stepsGoal", 8000),
        )
    }

    fun updateConfig(f: (Config) -> Config) = synchronized(this) {
        val c = f(_config.value)
        val arr = JSONArray()
        c.contacts.forEach { arr.put(JSONObject().put("name", it.name).put("number", it.number)) }
        p.edit()
            .putString("serverUrl", c.serverUrl.trim().trimEnd('/'))
            .putString("deviceToken", c.deviceToken.trim())
            .putBoolean("smsEnabled", c.smsEnabled)
            .putInt("smsDelayMin", c.smsDelayMin.coerceIn(1, 60))
            .putString("contacts", arr.toString())
            .putInt("stepsGoal", c.stepsGoal.coerceAtLeast(0))
            .apply()
        _config.value = readConfig()
    }

    fun link(f: (LinkStatus) -> LinkStatus) = synchronized(this) {
        val s = f(_link.value)
        _link.value = s
        p.edit()
            .putLong("lastWatchAt", s.lastWatchAt)
            .putString("lastWatchSource", s.lastWatchSource)
            .putLong("lastUploadAt", s.lastUploadAt)
            .putString("lastUploadError", s.lastUploadError)
            .putLong("lastHcSyncAt", s.lastHcSyncAt)
            .putString("hcStatus", s.hcStatus)
            .apply()
    }

    // Enkla nyckel-värden för synkroniseringens tillstånd.
    fun getLong(k: String, d: Long = 0) = p.getLong(k, d)
    fun putLong(k: String, v: Long) = p.edit().putLong(k, v).apply()
    fun getString(k: String): String? = p.getString(k, null)
    fun putString(k: String, v: String?) = p.edit().apply { if (v == null) remove(k) else putString(k, v) }.apply()
    fun getBool(k: String, d: Boolean = false) = p.getBoolean(k, d)
    fun putBool(k: String, v: Boolean) = p.edit().putBoolean(k, v).apply()
}

/** Källor som kommer från emulatorer eller testlägen. Visas alltid tydligt märkta i appen. */
fun isTestSource(source: String?): Boolean = source != null && (source.contains("emulator") || source.contains("test"))
