package se.konsiliet.app.widget

import android.content.Context
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.DpSize
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.glance.GlanceId
import androidx.glance.GlanceModifier
import androidx.glance.LocalSize
import androidx.glance.action.clickable
import androidx.glance.appwidget.GlanceAppWidget
import androidx.glance.appwidget.GlanceAppWidgetReceiver
import androidx.glance.appwidget.LinearProgressIndicator
import androidx.glance.appwidget.SizeMode
import androidx.glance.action.actionStartActivity
import androidx.glance.appwidget.cornerRadius
import androidx.glance.appwidget.provideContent
import androidx.glance.background
import androidx.glance.color.ColorProvider as DayNight
import androidx.glance.layout.Alignment
import androidx.glance.layout.Column
import androidx.glance.layout.Row
import androidx.glance.layout.Spacer
import androidx.glance.layout.fillMaxSize
import androidx.glance.layout.fillMaxWidth
import androidx.glance.layout.height
import androidx.glance.layout.padding
import androidx.glance.layout.width
import androidx.glance.text.FontWeight
import androidx.glance.text.Text
import androidx.glance.text.TextStyle
import androidx.glance.unit.ColorProvider
import org.json.JSONObject
import se.konsiliet.app.ui.MainActivity
import se.konsiliet.app.ui.components.Fmt

/** Samma tokens som appen (Theme.kt): papper och bläck i ljust läge, grafit i mörkt. */
private object W {
    val bg = DayNight(day = Color(0xFFFFFFFF), night = Color(0xFF16191C))
    val ink = DayNight(day = Color(0xFF16191C), night = Color(0xFFE6E7E4))
    val ink2 = DayNight(day = Color(0xFF50575D), night = Color(0xFFA2A8AD))
    val ink3 = DayNight(day = Color(0xFF8A9096), night = Color(0xFF6C7379))
    val track = DayNight(day = Color(0xFFE9EAE6), night = Color(0xFF1F2427))
    val accent = DayNight(day = Color(0xFF1F5A69), night = Color(0xFF7FB6C3))
    val akut = DayNight(day = Color(0xFFB42318), night = Color(0xFFF0645A))
    val avvikelse = DayNight(day = Color(0xFFA15C07), night = Color(0xFFE0A458))
}

private val URGENCY = mapOf(
    "ingen" to "Ingen åtgärd", "bevaka" to "Bevaka", "ta_upp_med_varden" to "Ta upp med vården",
    "kontakta_vard_nu" to "Kontakta vården nu",
)

private fun style(size: Int, color: ColorProvider, weight: FontWeight = FontWeight.Normal) =
    TextStyle(color = color, fontSize = size.sp, fontWeight = weight)

/**
 * Hemskärmswidget: headroom (återhämtningen) med delarna timingmarginal (HRV), idle-klock (vilopuls)
 * och viloläge (sömn), dagens steg mot målet och senaste lösningen i supporttråden (konsiliet).
 * Brådskande nivåer ("Kontakta vården nu") skrivs sakligt, utan forumtermer. Tryck öppnar appen. Ritar bara det som Summary har sparat, så
 * den gör inga nätverksanrop själv. updatePeriodMillis är 0: Summary uppdaterar den vid händelser
 * och var 30:e minut.
 */
class KonsilietWidget : GlanceAppWidget() {

    override val sizeMode = SizeMode.Responsive(setOf(SMALL, WIDE, TALL))

    override suspend fun provideGlance(context: Context, id: GlanceId) {
        Summary.load()
        provideContent {
            val s by Summary.state.collectAsState()
            Content(s, System.currentTimeMillis())
        }
    }

    companion object {
        val SMALL = DpSize(160.dp, 100.dp)
        val WIDE = DpSize(250.dp, 100.dp)
        val TALL = DpSize(250.dp, 160.dp)
    }
}

class KonsilietWidgetReceiver : GlanceAppWidgetReceiver() {
    override val glanceAppWidget: GlanceAppWidget = KonsilietWidget()
}

@Composable
private fun Content(s: JSONObject?, now: Long) {
    val size = LocalSize.current
    val wide = size.width >= KonsilietWidget.WIDE.width
    val tall = size.height >= KonsilietWidget.TALL.height
    Column(
        GlanceModifier.fillMaxSize().background(W.bg).cornerRadius(16.dp).padding(horizontal = 14.dp, vertical = 10.dp)
            .clickable(actionStartActivity<MainActivity>()),
    ) {
        // Rubrik och när siffrorna senast hämtades från servern.
        Row(GlanceModifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            Text("Headroom", style = style(13, W.ink2, FontWeight.Medium), modifier = GlanceModifier.defaultWeight())
            val at = s?.optLong("server_at", 0) ?: 0
            val stale = s != null && (!s.optBoolean("server_ok", false) || now - at > 2 * 3600_000L)
            Text(
                when { s == null -> "Ej hämtad"; at == 0L -> "Servern svarar inte"; else -> Fmt.ago(at, now) },
                style = style(11, if (stale) W.avvikelse else W.ink3),
            )
        }
        Spacer(GlanceModifier.height(2.dp))
        Row(GlanceModifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            val score = s?.takeIf { it.has("poang") && !it.isNull("poang") }?.optInt("poang")
            Row(verticalAlignment = Alignment.Bottom) {
                Text(score?.toString() ?: "--", style = style(34, if (score == null) W.ink3 else W.ink, FontWeight.Medium))
                Text(if (score == null) "  " + (s?.optString("poang_kommentar")?.ifBlank { null } ?: "ingen poäng") else "  av 100",
                    style = style(11, W.ink3), modifier = GlanceModifier.padding(bottom = 6.dp))
            }
            if (wide) {
                Spacer(GlanceModifier.defaultWeight())
                Parts(s?.optJSONObject("delar"))
            }
        }
        Spacer(GlanceModifier.height(6.dp))
        Steps(s)
        if (tall) {
            Spacer(GlanceModifier.height(8.dp))
            Verdict(s?.optJSONObject("konsilium"), lines = if (tall) 2 else 1)
        }
    }
}

/** Tre delar av poängen i en högerställd kolumn: värdet i natt mot baslinjen. */
@Composable
private fun Parts(d: JSONObject?) {
    Column(horizontalAlignment = Alignment.End) {
        PartRow("Timing (HRV)", d?.optJSONObject("hrv")?.let { Fmt.dec(it.optDouble("natt_ms")) + " ms" })
        PartRow("Idle-klock", d?.optJSONObject("vilopuls")?.let { Fmt.dec(it.optDouble("natt")) + " BPM" })
        PartRow("Viloläge", d?.optJSONObject("somn")?.let { Fmt.duration(it.optDouble("timmar") * 3600) })
    }
}

@Composable
private fun PartRow(label: String, value: String?) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        Text(label, style = style(11, W.ink3))
        Spacer(GlanceModifier.width(6.dp))
        Text(value ?: "saknas", style = style(12, if (value == null) W.ink3 else W.ink, FontWeight.Medium))
    }
}

@Composable
private fun Steps(s: JSONObject?) {
    val steps = s?.optInt("steg", 0) ?: 0
    val goal = (s?.optInt("steg_mal", 8000) ?: 8000).coerceAtLeast(1)
    Row(GlanceModifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        Text("Steg ", style = style(12, W.ink2))
        Text(Fmt.int(steps.toDouble()), style = style(12, W.ink, FontWeight.Medium))
        Text(" av " + Fmt.int(goal.toDouble()), style = style(12, W.ink3), modifier = GlanceModifier.defaultWeight())
        if (s?.optBoolean("steg_testdata") == true) Text("testdata", style = style(11, W.avvikelse))
    }
    Spacer(GlanceModifier.height(4.dp))
    LinearProgressIndicator(
        progress = (steps.toFloat() / goal).coerceIn(0f, 1f),
        modifier = GlanceModifier.fillMaxWidth().height(4.dp),
        color = W.accent, backgroundColor = W.track,
    )
}

@Composable
private fun Verdict(k: JSONObject?, lines: Int) {
    val running = k?.optBoolean("pagar") == true
    val u = k?.optString("bradska")?.ifBlank { null }
    val (label, color) = when {
        running -> "Tråd pågår" to W.accent
        u == "kontakta_vard_nu" -> URGENCY.getValue(u) to W.akut
        u == "ta_upp_med_varden" -> URGENCY.getValue(u) to W.avvikelse
        u != null -> "Markerad som lösning: " + (URGENCY[u] ?: u) to W.ink
        else -> "Ingen tråd ännu" to W.ink3
    }
    Row(GlanceModifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                Text(label, style = style(12, color, FontWeight.Medium), modifier = GlanceModifier.defaultWeight())
        k?.takeIf { !running && it.has("slut") }?.let { Text(Fmt.ago((it.optDouble("slut") * 1000).toLong()), style = style(11, W.ink3)) }
    }
    val text = k?.optString("sammanfattning")?.ifBlank { null }
    if (!running && text != null) Text(text, style = style(12, W.ink2), maxLines = lines)
}
