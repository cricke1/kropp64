package se.konsiliet.app.ui.screens

import androidx.compose.foundation.shape.CircleShape

import androidx.compose.foundation.layout.fillMaxHeight

import androidx.compose.foundation.layout.size

import androidx.compose.material.icons.filled.Timeline

import androidx.compose.material.icons.filled.Check

import androidx.compose.material.icons.filled.Circle

import androidx.compose.material.icons.filled.Search

import androidx.compose.material.icons.filled.Person

import androidx.compose.material.icons.filled.Gavel

import androidx.compose.material.icons.filled.Description

import androidx.compose.material.icons.filled.WbSunny

import androidx.compose.material.icons.filled.DirectionsWalk

import androidx.compose.material.icons.filled.CheckCircle

import androidx.compose.material.icons.filled.Forum

import androidx.compose.material.icons.filled.Sensors

import androidx.compose.material.icons.filled.Warning

import androidx.compose.material.icons.Icons

import android.content.Context
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import org.json.JSONObject
import se.konsiliet.app.data.EventRow
import se.konsiliet.app.data.KonsilietDb
import se.konsiliet.app.net.Api
import se.konsiliet.app.ui.components.Fmt
import se.konsiliet.app.ui.theme.LocalTokens
import se.konsiliet.app.ui.theme.Tokens
import se.konsiliet.app.ui.theme.Type

val AGENT_NAMES = mapOf(
    "ordforande" to "Trådstartaren", "kardiolog" to "Kardiologen", "somn" to "Sömnläkaren",
    "idrott" to "Idrottsläkare", "stress" to "Stressmedicin", "labb" to "Klinisk kemist",
    "advokat" to "Trollet", "granskare" to "Moderatorn", "alla" to "alla",
)

private val MAIN_KINDS = setOf("alert.raise", "vakt.anomaly", "consult.start", "consult.verdict", "nudge.move",
    "brief.morgon", "sync.1177", "review.strike")

/** Hämtar serverns senaste händelser till den lokala cachen (för när appen varit stängd). */
suspend fun syncEvents(ctx: Context) {
    runCatching {
        val arr = Api.getArray("/api/events?limit=300")
        val rows = (0 until arr.length()).map { arr.getJSONObject(it) }.filter { !it.isNull("id") }.map {
            EventRow(it.getLong("id"), it.optDouble("ts"), it.optString("kind"), (it.optJSONObject("payload") ?: JSONObject()).toString())
        }
        KonsilietDb.get(ctx).events().insert(rows)
    }
}

data class Described(val title: String, val body: String?, val color: Color?, val consultId: String?)

fun describe(e: EventRow, t: Tokens): Described {
    val p = runCatching { JSONObject(e.payload) }.getOrDefault(JSONObject())
    val cid = p.optString("consult_id").takeIf { it.isNotEmpty() }
    return when (e.kind) {
        "alert.raise" -> Described((if (p.optString("level") == "akut") "Akut larm: " else "Larm: ") + p.optString("title"),
            p.optString("body"), if (p.optString("level") == "akut") t.akut else t.avvikelse, cid)
        "vakt.anomaly" -> Described("Vakten: " + p.optString("title"), p.optString("detail"),
            if (p.optString("level") == "akut") t.akut else t.avvikelse, null)
        "consult.start" -> {
            val tr = p.optJSONObject("trigger")
            Described("Ny tråd startad", tr?.optString("title")?.ifEmpty { null } ?: tr?.optString("question"), t.accent, cid)
        }
        "consult.verdict" -> Described("Markerad som lösning", p.optJSONObject("verdict")?.optString("sammanfattning"), t.accent, cid)
        "nudge.move" -> Described(p.optString("title"), p.optString("body"), null, null)
        "brief.morgon" -> Described("POST-skärmen " + p.optString("datum"), p.optString("text"), null, null)
        "sync.1177" -> when (p.optString("status")) {
            "klar" -> Described("Journalen hämtad från 1177", "${p.optInt("nya_anteckningar")} nya anteckningar, ${p.optInt("nya_provsvar")} nya provsvar", t.ok, null)
            "misslyckades" -> Described("1177-hämtningen misslyckades", p.optString("detail").ifEmpty { null }, t.avvikelse, null)
            else -> Described("1177: " + p.optString("status"), p.optString("detail").ifEmpty { null }, null, null)
        }
        "review.strike" -> Described("Moderatorn strök ett påstående", p.optString("claim") + " (" + p.optString("reason") + ")", t.ink3, cid)
        "agent.say" -> Described((AGENT_NAMES[p.optString("agent")] ?: p.optString("agent")) + " till " +
            (AGENT_NAMES[p.optString("to")] ?: p.optString("to")), p.optString("text"), null, cid)
        "agent.tool" -> Described((AGENT_NAMES[p.optString("agent")] ?: p.optString("agent")) + " slår upp " + p.optString("tool"), null, t.ink3, cid)
        else -> Described(e.kind, null, t.ink3, cid)
    }
}

/** Ikon per händelsetyp, som i en aktivitetslogg. */
private fun ikon(kind: String): androidx.compose.ui.graphics.vector.ImageVector = when (kind) {
    "alert.raise" -> Icons.Filled.Warning
    "vakt.anomaly" -> Icons.Filled.Sensors
    "consult.start" -> Icons.Filled.Forum
    "consult.verdict" -> Icons.Filled.CheckCircle
    "nudge.move" -> Icons.Filled.DirectionsWalk
    "brief.morgon" -> Icons.Filled.WbSunny
    "sync.1177" -> Icons.Filled.Description
    "review.strike" -> Icons.Filled.Gavel
    "agent.say" -> Icons.Filled.Person
    "agent.tool" -> Icons.Filled.Search
    else -> Icons.Filled.Circle
}

@Composable
fun TimelineScreen(onOpenConsult: (String) -> Unit) {
    val t = LocalTokens.current
    val ctx = LocalContext.current
    val cs = androidx.compose.material3.MaterialTheme.colorScheme
    val typo = androidx.compose.material3.MaterialTheme.typography
    val events by remember { KonsilietDb.get(ctx).events().recent(1000) }.collectAsState(emptyList())
    var all by remember { mutableStateOf(false) }
    LaunchedEffect(Unit) { syncEvents(ctx) }
    // Beskrivningarna räknas en gång per lista, inte vid varje omritning av en rad.
    val rows = remember(events, all, t) {
        // 1177 skickar en händelse per steg; i huvudlistan visas bara resultatet.
        fun viktig(e: EventRow) = e.kind in MAIN_KINDS && (e.kind != "sync.1177" ||
            e.payload.contains("\"klar\"") || e.payload.contains("\"misslyckades\""))
        val shown = events.filter { all || viktig(it) }
        shown.mapIndexed { i, e -> Triple(e, describe(e, t), i == 0 || Fmt.day(shown[i - 1].ts) != Fmt.day(e.ts)) }
    }

    Column(Modifier.fillMaxSize()) {
        Row(Modifier.fillMaxWidth().padding(start = 24.dp, end = 16.dp, top = 20.dp, bottom = 8.dp), verticalAlignment = Alignment.CenterVertically) {
            Text("Tidslinje", style = typo.headlineLarge, color = cs.onSurface, modifier = Modifier.weight(1f))
            androidx.compose.material3.FilterChip(selected = all, onClick = { all = !all }, label = { Text("Visa allt") },
                leadingIcon = if (all) { { androidx.compose.material3.Icon(Icons.Filled.Check, null, Modifier.size(18.dp)) } } else null)
        }
        if (rows.isEmpty()) {
            Column(Modifier.fillMaxWidth().padding(40.dp), horizontalAlignment = Alignment.CenterHorizontally) {
                androidx.compose.material3.Icon(Icons.Filled.Timeline, null, tint = cs.onSurfaceVariant, modifier = Modifier.size(48.dp))
                Text("Inga händelser ännu", style = typo.titleMedium, color = cs.onSurface, modifier = Modifier.padding(top = 12.dp))
                Text("Larm, vakten, trådar och 1177 hamnar här.", style = typo.bodyMedium, color = cs.onSurfaceVariant)
            }
        }
        LazyColumn(Modifier.fillMaxSize(), contentPadding = androidx.compose.foundation.layout.PaddingValues(bottom = 24.dp)) {
            items(rows, key = { it.first.id }) { (e, d, header) ->
                if (header) {
                    Text(Fmt.day(e.ts), style = typo.titleSmall, color = cs.primary, modifier = Modifier.padding(start = 24.dp, top = 18.dp, bottom = 6.dp))
                }
                val farg = d.color ?: cs.onSurfaceVariant
                Row(
                    Modifier.fillMaxWidth().clickable(enabled = d.consultId != null) { d.consultId?.let(onOpenConsult) }
                        .padding(horizontal = 16.dp).height(androidx.compose.foundation.layout.IntrinsicSize.Min)
                ) {
                    // Ikonen på en lodrät linje
                    Box(Modifier.width(48.dp).fillMaxHeight(), contentAlignment = Alignment.TopCenter) {
                        Box(Modifier.width(2.dp).fillMaxHeight().background(cs.outlineVariant))
                        Box(Modifier.padding(top = 10.dp).size(36.dp).background(cs.surface, CircleShape).padding(2.dp)
                            .background(farg.copy(alpha = 0.16f), CircleShape), contentAlignment = Alignment.Center) {
                            androidx.compose.material3.Icon(ikon(e.kind), null, tint = farg, modifier = Modifier.size(18.dp))
                        }
                    }
                    Column(Modifier.weight(1f).padding(start = 8.dp, top = 10.dp, bottom = 12.dp)) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Text(d.title, style = typo.titleSmall, color = cs.onSurface, modifier = Modifier.weight(1f))
                            Text(Fmt.hm(e.ts), style = typo.labelMedium, color = cs.onSurfaceVariant)
                        }
                        d.body?.takeIf { it.isNotBlank() }?.let {
                            Text(it, style = typo.bodyMedium, color = cs.onSurfaceVariant, maxLines = 4,
                                overflow = androidx.compose.ui.text.style.TextOverflow.Ellipsis, modifier = Modifier.padding(top = 2.dp))
                        }
                        if (d.consultId != null) Text("Öppna tråden", style = typo.labelLarge, color = cs.primary, modifier = Modifier.padding(top = 4.dp))
                    }
                }
            }
        }
    }
}
