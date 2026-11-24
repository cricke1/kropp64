package se.konsiliet.app.ui.components

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.text.drawText
import androidx.compose.ui.text.rememberTextMeasurer
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import java.text.NumberFormat
import java.text.SimpleDateFormat
import java.util.Calendar
import java.util.Date
import java.util.Locale
import kotlin.math.ceil
import kotlin.math.floor
import kotlin.math.max
import se.konsiliet.app.data.MetricPoint
import se.konsiliet.app.ui.theme.LocalTokens
import se.konsiliet.app.ui.theme.Type

val SV: Locale = Locale("sv", "SE")
private val hmFmt = SimpleDateFormat("HH:mm", SV)
private val dayFmt = SimpleDateFormat("EEE d MMM", SV)

object Fmt {
    fun int(v: Double): String = NumberFormat.getIntegerInstance(SV).format(Math.round(v))
    fun dec(v: Double, d: Int = 1): String = NumberFormat.getNumberInstance(SV).apply {
        minimumFractionDigits = d; maximumFractionDigits = d
    }.format(v)
    fun hm(tsSeconds: Double): String = hmFmt.format(Date((tsSeconds * 1000).toLong()))
    fun hmMs(ms: Long): String = hmFmt.format(Date(ms))
    fun day(tsSeconds: Double): String = dayFmt.format(Date((tsSeconds * 1000).toLong()))
    fun duration(seconds: Double): String {
        val m = (seconds / 60).toInt()
        return "${m / 60} h ${"%02d".format(m % 60)} min"
    }
    fun ago(ms: Long, now: Long = System.currentTimeMillis()): String {
        if (ms <= 0) return "aldrig"
        val s = (now - ms) / 1000
        return when {
            s < 45 -> "nyss"
            s < 3600 -> "${s / 60} min sedan"
            s < 86400 -> "kl. " + hmMs(ms)
            else -> dayFmt.format(Date(ms))
        }
    }
}

/** Sektion med rubrik i normal versal/gemen och en tunn linje, som i ett instrumentprotokoll. */
@Composable
fun Section(title: String, trailing: String? = null, modifier: Modifier = Modifier, content: @Composable () -> Unit) {
    val t = LocalTokens.current
    Column(modifier.fillMaxWidth().padding(top = 22.dp)) {
        Row(Modifier.fillMaxWidth().padding(horizontal = 20.dp), verticalAlignment = Alignment.Bottom) {
            Text(title, style = Type.heading, color = t.ink, modifier = Modifier.weight(1f))
            if (trailing != null) Text(trailing, style = Type.small, color = t.ink3)
        }
        Spacer(Modifier.height(8.dp))
        Box(Modifier.fillMaxWidth().padding(horizontal = 20.dp).height(1.dp).background(t.rule))
        content()
    }
}

/** En rad i en mätvärdestabell: etikett till vänster, värde och enhet till höger, källa under. */
@Composable
fun ReadoutRow(label: String, value: String?, unit: String = "", note: String? = null, noteColor: Color? = null) {
    val t = LocalTokens.current
    Column(Modifier.fillMaxWidth()) {
        Row(Modifier.fillMaxWidth().padding(horizontal = 20.dp, vertical = 11.dp), verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Text(label, style = Type.body, color = t.ink)
                if (note != null) Text(note, style = Type.small, color = noteColor ?: t.ink3)
            }
            if (value != null) {
                // Tal visas som mätvärden, text (t.ex. "nyss") i brödstil.
                Text(value, style = if (value.any { it.isLetter() }) Type.body else Type.value, color = t.ink)
                if (unit.isNotEmpty()) Text(" $unit", style = Type.small, color = t.ink2, modifier = Modifier.padding(top = 6.dp))
            } else {
                Text("ingen data", style = Type.small, color = t.ink3)
            }
        }
        Box(Modifier.fillMaxWidth().padding(start = 20.dp).height(1.dp).background(t.grid))
    }
}

@Composable
fun StatusDot(color: Color, size: Dp = 7.dp) {
    Box(Modifier.size(size).background(color, CircleShape))
}

private fun niceStep(range: Double, ticks: Int): Double {
    val raw = range / ticks
    val mag = Math.pow(10.0, floor(Math.log10(raw)))
    val n = raw / mag
    return mag * when { n < 1.5 -> 1.0; n < 3 -> 2.0; n < 7 -> 5.0; else -> 10.0 }
}

/**
 * Tidsserie som en instrumentavläsning: tunt spår, svagt rutnät på jämna värden, tidsaxel med
 * hela klockslag, min/max utskrivna. Luckor över [gapSeconds] ritas som avbrott, inte som en linje
 * rakt över (en lucka är frånvaro av data och ska synas som det).
 */
@Composable
fun TraceChart(
    points: List<MetricPoint>,
    fromTs: Double,
    toTs: Double,
    modifier: Modifier = Modifier,
    height: Dp = 140.dp,
    gapSeconds: Double = 15 * 60.0,
    unit: String = "",
    color: Color? = null,
) {
    val t = LocalTokens.current
    val measurer = rememberTextMeasurer()
    val line = color ?: t.trace
    Canvas(modifier.fillMaxWidth().height(height)) {
        val left = 0f
        val right = size.width - 34.dp.toPx()
        val top = 6.dp.toPx()
        val bottom = size.height - 18.dp.toPx()
        if (points.isEmpty()) {
            drawLine(t.grid, Offset(left, (top + bottom) / 2), Offset(right, (top + bottom) / 2), 1.dp.toPx(),
                pathEffect = PathEffect.dashPathEffect(floatArrayOf(6f, 6f)))
            val l = measurer.measure("ingen data", Type.small.copy(color = t.ink3))
            drawText(l, topLeft = Offset((right - l.size.width) / 2, (top + bottom) / 2 - l.size.height - 4))
            return@Canvas
        }
        var lo = points.minOf { it.value }
        var hi = points.maxOf { it.value }
        if (hi - lo < 1e-9) { lo -= 1; hi += 1 }
        val step = niceStep(hi - lo, 3)
        val yLo = floor(lo / step) * step
        val yHi = ceil(hi / step) * step
        fun x(ts: Double) = left + ((ts - fromTs) / (toTs - fromTs)).toFloat() * (right - left)
        fun y(v: Double) = bottom - ((v - yLo) / (yHi - yLo)).toFloat() * (bottom - top)

        // horisontellt rutnät med värden till höger
        var g = yLo
        while (g <= yHi + 1e-9) {
            val yy = y(g)
            drawLine(t.grid, Offset(left, yy), Offset(right, yy), 1f)
            val l = measurer.measure(Fmt.int(g), Type.axis.copy(color = t.ink3))
            drawText(l, topLeft = Offset(right + 6.dp.toPx(), yy - l.size.height / 2))
            g += step
        }
        // tidsaxel: var sjätte timme (24 h) eller varje timme (kortare)
        val span = toTs - fromTs
        val tickH = if (span > 12 * 3600) 6 else if (span > 4 * 3600) 2 else 1
        val cal = Calendar.getInstance().apply {
            timeInMillis = (fromTs * 1000).toLong(); set(Calendar.MINUTE, 0); set(Calendar.SECOND, 0); set(Calendar.MILLISECOND, 0)
            add(Calendar.HOUR_OF_DAY, 1)
        }
        while (cal.timeInMillis / 1000.0 < toTs) {
            if (cal.get(Calendar.HOUR_OF_DAY) % tickH == 0) {
                val xx = x(cal.timeInMillis / 1000.0)
                drawLine(t.rule, Offset(xx, bottom), Offset(xx, bottom + 4.dp.toPx()), 1f)
                val l = measurer.measure(hmFmt.format(cal.time), Type.axis.copy(color = t.ink3))
                drawText(l, topLeft = Offset((xx - l.size.width / 2).coerceIn(0f, right - l.size.width), bottom + 5.dp.toPx()))
            }
            cal.add(Calendar.HOUR_OF_DAY, 1)
        }
        drawLine(t.rule, Offset(left, bottom), Offset(right, bottom), 1f)

        // spåret
        val path = Path()
        var prev: MetricPoint? = null
        for (p in points) {
            if (p.ts < fromTs) continue
            val px = x(p.ts); val py = y(p.value)
            if (prev == null || p.ts - prev.ts > gapSeconds) path.moveTo(px, py) else path.lineTo(px, py)
            prev = p
        }
        drawPath(path, line, style = Stroke(width = 1.6.dp.toPx(), cap = StrokeCap.Round, join = StrokeJoin.Round))
        val last = points.last()
        drawCircle(line, 3.dp.toPx(), Offset(x(last.ts), y(last.value)))
    }
}

/** Hypnogram: fyra nivåer (vaken överst, djupsömn nederst) som trappsteg över natten. */
@Composable
fun Hypnogram(stages: List<Triple<Double, Double, String>>, modifier: Modifier = Modifier) {
    val t = LocalTokens.current
    val measurer = rememberTextMeasurer()
    val levels = listOf("awake" to "Vaken", "rem" to "REM", "light" to "Lätt", "deep" to "Djup")
    val colors = mapOf("awake" to t.sleepAwake, "rem" to t.sleepRem, "light" to t.sleepLight, "deep" to t.sleepDeep,
        "sleeping" to t.sleepLight, "unknown" to t.ink3)
    Canvas(modifier.fillMaxWidth().height(112.dp)) {
        if (stages.isEmpty()) return@Canvas
        val labelW = 44.dp.toPx()
        val bottomAxis = 16.dp.toPx()
        val rowH = (size.height - bottomAxis) / levels.size
        val from = stages.first().first
        val to = stages.maxOf { it.second }
        fun x(ts: Double) = labelW + ((ts - from) / (to - from)).toFloat() * (size.width - labelW)
        levels.forEachIndexed { i, (_, name) ->
            val yy = i * rowH
            drawLine(t.grid, Offset(labelW, yy + rowH / 2), Offset(size.width, yy + rowH / 2), 1f)
            val l = measurer.measure(name, Type.axis.copy(color = t.ink3))
            drawText(l, topLeft = Offset(0f, yy + rowH / 2 - l.size.height / 2))
        }
        for ((s, e, st) in stages) {
            val idx = when (st) { "awake" -> 0; "rem" -> 1; "deep" -> 3; else -> 2 }
            val yy = idx * rowH + rowH * 0.2f
            drawRect(colors[st] ?: t.ink3, Offset(x(s), yy), Size(max(1f, x(e) - x(s)), rowH * 0.6f))
        }
        val lf = measurer.measure(Fmt.hm(from), Type.axis.copy(color = t.ink3))
        drawText(lf, topLeft = Offset(labelW, size.height - lf.size.height))
        val lt = measurer.measure(Fmt.hm(to), Type.axis.copy(color = t.ink3))
        drawText(lt, topLeft = Offset(size.width - lt.size.width, size.height - lt.size.height))
    }
}

/** Steg mot mål: en tunn skala med målet markerat, inte en ring. */
@Composable
fun GoalBar(value: Double, goal: Double, modifier: Modifier = Modifier) {
    val t = LocalTokens.current
    Canvas(modifier.fillMaxWidth().height(10.dp)) {
        val h = 4.dp.toPx()
        val y = (size.height - h) / 2
        val scaleMax = max(goal * 1.25, value)
        drawRect(t.grid, Offset(0f, y), Size(size.width, h))
        val w = (value / scaleMax).toFloat() * size.width
        drawRect(if (value >= goal) t.ok else t.accent, Offset(0f, y), Size(w, h))
        val gx = (goal / scaleMax).toFloat() * size.width
        drawLine(t.ink2, Offset(gx, 0f), Offset(gx, size.height), 1.5f)
    }
}

@Composable
fun Pill(text: String, color: Color) {
    Text(text, style = Type.small, color = color,
        modifier = Modifier.background(color.copy(alpha = 0.10f), CircleShape).padding(horizontal = 8.dp, vertical = 2.dp))
}

@Composable
fun HSpace(w: Dp) = Spacer(Modifier.width(w))

@Composable
fun Legend(items: List<Pair<String, Color>>) {
    val t = LocalTokens.current
    Row(horizontalArrangement = Arrangement.spacedBy(14.dp), modifier = Modifier.padding(horizontal = 20.dp)) {
        items.forEach { (name, c) ->
            Row(verticalAlignment = Alignment.CenterVertically) {
                Box(Modifier.size(8.dp).background(c))
                Spacer(Modifier.width(5.dp))
                Text(name, style = Type.small, color = t.ink2)
            }
        }
    }
}
