package se.konsiliet.wear.data

import android.content.Context
import android.content.SharedPreferences
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import org.json.JSONObject

/**
 * Det mobilen senast skickade över Data Layer (`/konsiliet/status`): återhämtningspoäng och
 * konsiliets läge. Cachas i SharedPreferences så att tile och komplikationer kan svara direkt,
 * även när mobilen är utom räckhåll eller processen nyss startat.
 */
data class Snapshot(
    /** Återhämtning 0-100, null om servern har för lite data. */
    val score: Int? = null,
    val scoreNote: String? = null,
    val consultRunning: Boolean = false,
    val consultId: String? = null,
    /** Senaste bedömningens brådska: ingen, bevaka, ta_upp_med_varden, kontakta_vard_nu. */
    val urgency: String? = null,
    val summary: String? = null,
    /** När bedömningen var klar (unix-sekunder). */
    val verdictAt: Double = 0.0,
    /** När mobilen byggde underlaget (ms). */
    val phoneAt: Long = 0,
    /** När klockan tog emot det (ms). Detta är "senast synkad". */
    val receivedAt: Long = 0,
    /** Dagens svar från servern (vardag.idag): beslut, rubrik och plan med pulszon. */
    val idag: Idag? = null,
) {
    val hasData: Boolean get() = receivedAt > 0
}

data class Idag(
    val beslut: String, val rubrik: String, val plan: String, val typ: String, val minuter: Int,
    val zon: Int?, val pulsLo: Int?, val pulsHi: Int?, val maxpuls: Int, val pass: Int, val mal: Int,
)

object PhoneStatus {
    const val PATH = "/konsiliet/status"
    private const val KEY = "status_json"
    private const val KEY_AT = "status_received"

    private lateinit var prefs: SharedPreferences
    private val _snap = MutableStateFlow(Snapshot())
    val snapshot: StateFlow<Snapshot> = _snap.asStateFlow()

    fun init(ctx: Context) {
        prefs = ctx.getSharedPreferences("phone_status", Context.MODE_PRIVATE)
        val raw = prefs.getString(KEY, null) ?: return
        _snap.value = runCatching { parse(raw, prefs.getLong(KEY_AT, 0)) }.getOrDefault(Snapshot())
    }

    /** Samma kodning som mobilens WatchSync.encode. */
    fun parse(json: String, receivedAt: Long): Snapshot {
        val o = JSONObject(json)
        val k = o.optJSONObject("konsilium")
        return Snapshot(
            score = if (o.isNull("poang") || !o.has("poang")) null else o.optInt("poang"),
            scoreNote = o.optString("poang_kommentar").ifBlank { null },
            consultRunning = k?.optBoolean("pagar") ?: false,
            consultId = k?.optString("id")?.ifBlank { null },
            urgency = k?.optString("bradska")?.ifBlank { null },
            summary = k?.optString("sammanfattning")?.ifBlank { null },
            verdictAt = k?.optDouble("slut", 0.0)?.takeIf { !it.isNaN() } ?: 0.0,
            phoneAt = o.optLong("synkad", 0),
            receivedAt = receivedAt,
            idag = o.optJSONObject("idag")?.let { i ->
                Idag(i.optString("beslut"), i.optString("rubrik"), i.optString("plan"), i.optString("typ"), i.optInt("minuter"),
                    if (i.isNull("zon")) null else i.optInt("zon"), if (i.isNull("puls_lo")) null else i.optInt("puls_lo"),
                    if (i.isNull("puls_hi")) null else i.optInt("puls_hi"), i.optInt("maxpuls", 0), i.optInt("pass"), i.optInt("mal", 3))
            },
        )
    }

    /**
     * Ny status från mobilen. Äldre underlag än det som redan finns ignoreras (Data Layer kan leverera
     * om ett äldre objekt efter återanslutning). Returnerar föregående och ny ögonblicksbild.
     */
    fun apply(json: String, now: Long = System.currentTimeMillis()): Pair<Snapshot, Snapshot>? = synchronized(this) {
        val next = parse(json, now)
        val prev = _snap.value
        if (prev.hasData && next.phoneAt < prev.phoneAt) return null
        prefs.edit().putString(KEY, json).putLong(KEY_AT, now).apply()
        _snap.value = next
        prev to next
    }
}

/** Korta svenska etiketter för brådskan, samma ord som i mobilappen och webben. */
object Urgency {
    fun label(u: String?): String = when (u) {
        "ingen" -> "Ingen åtgärd"
        "bevaka" -> "Bevaka"
        "ta_upp_med_varden" -> "Ta upp med vården"
        "kontakta_vard_nu" -> "Kontakta vården nu"
        else -> "Ingen bedömning"
    }

    /** Högst 7 tecken, för SHORT_TEXT-komplikationer. */
    fun short(u: String?): String = when (u) {
        "ingen" -> "Ingen"
        "bevaka" -> "Bevaka"
        "ta_upp_med_varden" -> "Ta upp"
        "kontakta_vard_nu" -> "Vård nu"
        else -> "--"
    }
}
