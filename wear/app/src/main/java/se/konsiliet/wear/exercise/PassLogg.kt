package se.konsiliet.wear.exercise

import android.content.Context
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import org.json.JSONArray
import org.json.JSONObject
import se.konsiliet.wear.data.PhoneStatus

/**
 * Pulszoner och passets logg på klockan, så att zonerna syns live och sammanfattningen kommer direkt
 * efter passet, även utan kontakt med mobilen. Samma gränser som servern (vardag.zoner): procent av
 * maxpuls 50/60/70/80/90/100, maxpuls från mobilen eller 208 - 0,7 x 18 år = 195.
 */
object Zoner {
    private val PROCENT = doubleArrayOf(0.5, 0.6, 0.7, 0.8, 0.9, 1.0)
    val NAMN = listOf("under zon 1", "mycket lätt", "lätt, du kan prata", "medel", "hårt", "max")

    fun maxpuls(): Int = PhoneStatus.snapshot.value.idag?.maxpuls?.takeIf { it > 100 } ?: 195

    /** Nedre och övre gräns för zon 1-5 i BPM. */
    fun grans(zon: Int, mx: Int = maxpuls()): Pair<Int, Int> =
        Math.round(mx * PROCENT[zon - 1]).toInt() to (Math.round(mx * PROCENT[zon]).toInt() - if (zon < 5) 1 else 0)

    fun zon(bpm: Double, mx: Int = maxpuls()): Int {
        for (z in 1..5) {
            val (lo, hi) = grans(z, mx)
            if (bpm <= hi) return if (bpm >= lo) z else 0
        }
        return 5
    }

    /** Målzon för passet: planens zon om dagens råd var att träna, annars zon 2 (zon 1 för promenad). */
    fun malzon(typ: String): Int {
        val i = PhoneStatus.snapshot.value.idag
        return when {
            i != null && i.beslut == "trana" && i.zon != null -> i.zon
            typ.contains("promenad", ignoreCase = true) -> 1
            else -> 2
        }
    }
}

data class Live(val sekunderIZon: DoubleArray = DoubleArray(6), val malzon: Int = 2, val sistaZon: Int = 0,
                val sum: Double = 0.0, val n: Int = 0, val max: Double = 0.0, val startMs: Long = 0, val typ: String = "")

object PassLogg {
    private val _live = MutableStateFlow(Live())
    val live: StateFlow<Live> = _live.asStateFlow()
    private var senastTs = 0.0
    private val _senaste = MutableStateFlow<JSONObject?>(null)
    /** Sammanfattningen efter senaste passet. Visas på klockans startsida tills man trycker Ok. */
    val senaste: StateFlow<JSONObject?> = _senaste.asStateFlow()

    fun init(ctx: Context) {
        val raw = ctx.getSharedPreferences("pass", Context.MODE_PRIVATE).getString("senaste", null)
        _senaste.value = raw?.let { runCatching { JSONObject(it) }.getOrNull() }
    }

    @Synchronized fun start(typ: String) {
        senastTs = 0.0
        _live.value = Live(malzon = Zoner.malzon(typ), startMs = System.currentTimeMillis(), typ = typ)
    }

    /** Pulspunkter under passet (sekunder sedan epoch, BPM). Tiden mellan punkterna räknas till zonen, högst 10 s. */
    @Synchronized fun puls(ts: Double, bpm: Double) {
        val l = _live.value
        if (l.startMs == 0L) return
        val z = Zoner.zon(bpm)
        val dt = if (senastTs > 0 && ts > senastTs) minOf(10.0, ts - senastTs) else 1.0
        senastTs = maxOf(senastTs, ts)
        val sek = l.sekunderIZon.copyOf().also { it[z] += dt }
        _live.value = l.copy(sekunderIZon = sek, sistaZon = z, sum = l.sum + bpm, n = l.n + 1, max = maxOf(l.max, bpm))
    }

    @Synchronized fun avsluta(ctx: Context): JSONObject? {
        val l = _live.value
        if (l.startMs == 0L) return null
        val min = (System.currentTimeMillis() - l.startMs) / 60000
        val zonMin = l.sekunderIZon.map { Math.round(it / 60).toInt() }
        val hart = (l.sekunderIZon[4] + l.sekunderIZon[5]) / 60
        val totalt = l.sekunderIZon.drop(1).sum()
        val iMal = if (totalt > 0) Math.round(100 * l.sekunderIZon[l.malzon] / totalt).toInt() else null
        val rad = when {
            l.n == 0 -> "Ingen puls registrerades."
            hart >= 15 -> "Hårt pass. Lätt dag i morgon och sov ordentligt."
            hart >= 5 -> "Medelhårt pass. Lätt pass eller vila i morgon."
            else -> "Lätt pass. Du kan träna igen i morgon om Headroom är över 55."
        }
        val o = JSONObject().put("typ", l.typ).put("minuter", min).put("puls_medel", if (l.n > 0) Math.round(l.sum / l.n) else JSONObject.NULL)
            .put("puls_max", if (l.n > 0) Math.round(l.max) else JSONObject.NULL).put("zon_minuter", JSONArray(zonMin.drop(1)))
            .put("malzon", l.malzon).put("i_malzon_procent", iMal ?: JSONObject.NULL).put("rad", rad).put("slut", System.currentTimeMillis())
        ctx.getSharedPreferences("pass", Context.MODE_PRIVATE).edit().putString("senaste", o.toString()).apply()
        _senaste.value = o
        _live.value = Live()
        return o
    }

    fun kvittera(ctx: Context) {
        ctx.getSharedPreferences("pass", Context.MODE_PRIVATE).edit().remove("senaste").apply()
        _senaste.value = null
    }
}
