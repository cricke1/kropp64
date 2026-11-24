package se.konsiliet.app.ui.screens

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
        "sync.1177" -> Described("1177: " + p.optString("status"), p.optString("detail").ifEmpty { null }, null, null)
        "review.strike" -> Described("Moderatorn strök ett påstående", p.optString("claim") + " (" + p.optString("reason") + ")", t.ink3, cid)
        "agent.say" -> Described((AGENT_NAMES[p.optString("agent")] ?: p.optString("agent")) + " till " +
            (AGENT_NAMES[p.optString("to")] ?: p.optString("to")), p.optString("text"), null, cid)
        "agent.tool" -> Described((AGENT_NAMES[p.optString("agent")] ?: p.optString("agent")) + " slår upp " + p.optString("tool"), null, t.ink3, cid)
        else -> Described(e.kind, null, t.ink3, cid)
    }
}

@Composable
fun TimelineScreen(onOpenConsult: (String) -> Unit) {
    val t = LocalTokens.current
    val ctx = LocalContext.current
    val events by remember { KonsilietDb.get(ctx).events().recent(1000) }.collectAsState(emptyList())
    var all by remember { mutableStateOf(false) }
    LaunchedEffect(Unit) { syncEvents(ctx) }
    val shown = events.filter { all || it.kind in MAIN_KINDS }

    Column(Modifier.fillMaxSize()) {
        Row(Modifier.fillMaxWidth().padding(start = 20.dp, end = 12.dp, top = 12.dp, bottom = 6.dp), verticalAlignment = Alignment.CenterVertically) {
            Text("Tidslinje", style = Type.title, color = t.ink, modifier = Modifier.weight(1f))
            Text("Visa allt", style = Type.small, color = t.ink2)
            Spacer(Modifier.width(8.dp))
            Switch(checked = all, onCheckedChange = { all = it })
        }
        Box(Modifier.fillMaxWidth().height(1.dp).background(t.rule))
        if (shown.isEmpty()) {
            Text("Inga händelser ännu. Händelser från vakten, supporttråden och larm hamnar här.",
                style = Type.body, color = t.ink3, modifier = Modifier.padding(20.dp))
        }
        LazyColumn(Modifier.fillMaxSize()) {
            val rows = shown.mapIndexed { i, e -> e to (i == 0 || Fmt.day(shown[i - 1].ts) != Fmt.day(e.ts)) }
            items(rows, key = { it.first.id }) { (e, header) ->
                if (header) {
                    Text(Fmt.day(e.ts), style = Type.label, color = t.ink2, modifier = Modifier.padding(start = 20.dp, top = 16.dp, bottom = 4.dp))
                }
                val d = describe(e, t)
                Row(
                    Modifier.fillMaxWidth().clickable(enabled = d.consultId != null) { d.consultId?.let(onOpenConsult) }
                        .padding(horizontal = 20.dp, vertical = 10.dp)
                ) {
                    Text(Fmt.hm(e.ts), style = Type.small, color = t.ink3, modifier = Modifier.width(48.dp).padding(top = 2.dp))
                    Box(Modifier.width(2.dp).height(18.dp).padding(top = 2.dp).background(d.color ?: t.rule))
                    Spacer(Modifier.width(10.dp))
                    Column(Modifier.weight(1f)) {
                        Text(d.title, style = Type.label, color = t.ink)
                        d.body?.takeIf { it.isNotBlank() }?.let {
                            Text(it, style = Type.body.copy(fontSize = Type.small.fontSize, lineHeight = Type.small.lineHeight),
                                color = t.ink2, maxLines = 4)
                        }
                    }
                }
            }
        }
    }
}
