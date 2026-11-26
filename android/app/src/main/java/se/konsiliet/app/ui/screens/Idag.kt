package se.konsiliet.app.ui.screens

import androidx.compose.material.icons.filled.BatteryChargingFull
import androidx.compose.material.icons.filled.BatterySaver
import androidx.compose.material.icons.filled.Bedtime
import androidx.compose.material.icons.filled.DirectionsRun
import androidx.compose.material.icons.filled.DirectionsWalk
import androidx.compose.material.icons.filled.Edit
import androidx.compose.material.icons.filled.FitnessCenter
import androidx.compose.material.icons.filled.HealthAndSafety
import androidx.compose.material.icons.filled.Hotel
import androidx.compose.material.icons.filled.QuestionAnswer
import androidx.compose.material.icons.filled.Today
import androidx.compose.material.icons.filled.Watch

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.IntrinsicSize
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.produceState
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.stateDescription
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.launch
import org.json.JSONArray
import org.json.JSONObject
import se.konsiliet.app.data.KonsilietDb
import se.konsiliet.app.data.Prefs
import se.konsiliet.app.net.Api
import se.konsiliet.app.ui.components.Fmt
import se.konsiliet.app.ui.components.Section
import se.konsiliet.app.ui.theme.LocalTokens
import se.konsiliet.app.ui.theme.Type

/**
 * Idag: svaret på morgonfrågan på fem sekunder. Träna, ta det lugnt eller vila, varför på en rad och planen.
 * Allt räknas på servern (vardag.py) med regler i koden; ingen språkmodell bestämmer beslutet.
 * Senaste svaret sparas, så att vyn fungerar utan nät (märkt med när det hämtades).
 */
object IdagCache {
    fun load(): Pair<JSONObject, Long>? {
        val raw = Prefs.getString("idag") ?: return null
        val o = runCatching { JSONObject(raw) }.getOrNull() ?: return null
        return o to Prefs.getLong("idagAt")
    }
    fun save(o: JSONObject) {
        Prefs.putString("idag", o.toString()); Prefs.putLong("idagAt", System.currentTimeMillis())
    }
}

/** Plan och beslut i klartext för skärmläsare och notiser. */
fun beslutFarg(beslut: String?, t: se.konsiliet.app.ui.theme.Tokens): Color = when (beslut) {
    "trana", "klart" -> t.ok
    "lugnt" -> t.avvikelse
    "vila" -> t.akut
    else -> t.ink3
}

@Composable
fun IdagScreen(onAsk: (String) -> Unit, onOpenConsult: (String) -> Unit, onSettings: () -> Unit,
               start1177: Boolean = false, onStart1177Done: () -> Unit = {}) {
    val t = LocalTokens.current
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    var refresh by remember { mutableIntStateOf(0) }
    var now by remember { mutableStateOf(System.currentTimeMillis()) }
    LaunchedEffect(Unit) { while (true) { delay(60_000); now = System.currentTimeMillis() } }
    val cached = remember { IdagCache.load() }
    var offline by remember { mutableStateOf(false) }
    val idag by produceState(cached?.first, refresh) {
        while (true) {
            val r = runCatching { Api.getObject("/api/idag") }.getOrNull()
            if (r != null) { IdagCache.save(r); offline = false; value = r } else offline = true
            delay(10 * 60_000)
        }
    }
    val notiser by produceState<JSONObject?>(null, refresh) {
        value = runCatching { Api.getObject("/api/notiser?dagar=1") }.getOrNull()?.also { n ->
            n.optString("tysta").takeIf { it.contains("-") }?.let { Prefs.putString("tystaTimmar", it) }
        }
    }
    val senastePass by produceState<JSONObject?>(null, refresh) {
        value = runCatching { Api.getArray("/api/pass?dagar=7") }.getOrNull()?.let { a -> if (a.length() > 0) a.getJSONObject(a.length() - 1) else null }
    }
    val brief by remember { KonsilietDb.get(ctx).events().recent(400).map { l -> l.firstOrNull { it.kind == "brief.morgon" } } }.collectAsState(null)
    var ordlista by rememberSaveable { mutableStateOf(false) }
    var msg by remember { mutableStateOf<String?>(null) }

    val cs = androidx.compose.material3.MaterialTheme.colorScheme
    val typo = androidx.compose.material3.MaterialTheme.typography
    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(bottom = 28.dp)) {
        Text("Idag", style = typo.headlineLarge, color = cs.onSurface,
            modifier = Modifier.padding(start = 24.dp, end = 24.dp, top = 20.dp).semantics { heading() })
        val i = idag
        if (i == null) {
            Text(if (offline) "Ingen kontakt med servern och inget sparat svar än. Kontrollera adressen under Inställningar."
                 else "Hämtar dagens svar ...", style = typo.bodyLarge, color = cs.onSurfaceVariant, modifier = Modifier.padding(24.dp))
            if (offline) TextButton(onClick = onSettings, modifier = Modifier.padding(horizontal = 12.dp)) { Text("Öppna Inställningar") }
            return@Column
        }
        val plan = i.optJSONObject("plan")
        val beslut = i.optString("beslut")
        val rubrik = i.optString("rubrik")
        val planText = plan?.optString("text").orEmpty()
        val varfor = i.optString("varfor")
        // Hjältekortet: färg och ikon efter beslutet, som en statusskärm i en träningsapp.
        val (heroBg, heroFg, heroIcon) = when (beslut) {
            "trana", "klart" -> Triple(Color(0xFF1B5E3B), Color(0xFFDDF5E6), androidx.compose.material.icons.Icons.Filled.DirectionsRun)
            "lugnt" -> Triple(Color(0xFF7A4A07), Color(0xFFFFEBCC), androidx.compose.material.icons.Icons.Filled.DirectionsWalk)
            "vila" -> Triple(Color(0xFF8C1D18), Color(0xFFFFDAD6), androidx.compose.material.icons.Icons.Filled.Hotel)
            else -> Triple(cs.primaryContainer, cs.onPrimaryContainer, androidx.compose.material.icons.Icons.Filled.Today)
        }
        androidx.compose.material3.Card(
            Modifier.fillMaxWidth().padding(start = 12.dp, end = 12.dp, top = 16.dp)
                .semantics(mergeDescendants = true) { contentDescription = "$rubrik. $planText. $varfor" },
            shape = androidx.compose.foundation.shape.RoundedCornerShape(28.dp),
            colors = androidx.compose.material3.CardDefaults.cardColors(containerColor = heroBg, contentColor = heroFg),
        ) {
            Column(Modifier.padding(24.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Box(Modifier.height(56.dp).width(56.dp).background(heroFg.copy(alpha = 0.16f), androidx.compose.foundation.shape.CircleShape),
                        contentAlignment = Alignment.Center) {
                        androidx.compose.material3.Icon(heroIcon, null, modifier = Modifier.height(32.dp).width(32.dp))
                    }
                    Text(rubrik, style = typo.headlineSmall, modifier = Modifier.padding(start = 16.dp))
                }
                if (planText.isNotBlank()) Text(planText, style = typo.titleLarge, modifier = Modifier.padding(top = 20.dp))
                plan?.optString("forslag")?.takeIf { it.isNotBlank() }?.let {
                    Text(it.replaceFirstChar { c -> c.uppercase() }, style = typo.bodyLarge, color = heroFg.copy(alpha = 0.85f), modifier = Modifier.padding(top = 2.dp))
                }
                if (varfor.isNotBlank()) Text(varfor.replaceFirstChar { c -> c.uppercase() } + ".", style = typo.bodyMedium,
                    color = heroFg.copy(alpha = 0.8f), modifier = Modifier.padding(top = 14.dp))
                i.optJSONObject("oppet")?.let { o ->
                    o.optString("consult_id").takeIf { it.isNotBlank() }?.let { cid ->
                        androidx.compose.material3.FilledTonalButton(onClick = { onOpenConsult(cid) }, modifier = Modifier.padding(top = 12.dp)) { Text("Öppna tråden") }
                    }
                }
            }
        }
        if (offline) {
            val at = cached?.second ?: 0L
            Text("Ingen kontakt med servern. Visar svaret från " + Fmt.ago(at, now) + ".", style = typo.bodySmall, color = t.avvikelse,
                modifier = Modifier.padding(horizontal = 24.dp, vertical = 6.dp))
        }

        // Ringarna: återhämtning, veckans pass och nattens sömn.
        val vk = i.optJSONObject("veckan")
        val sm = i.optJSONObject("somn")
        val natt = sm?.optJSONObject("natt")
        val hr = if (i.isNull("headroom")) null else i.optInt("headroom")
        val pass = vk?.optInt("pass") ?: 0
        val mal = (vk?.optInt("mal") ?: 3).coerceAtLeast(1)
        val behov = sm?.optDouble("behov_h")?.takeIf { !it.isNaN() && it > 0 } ?: 8.0
        val timmar = natt?.optDouble("timmar")?.takeIf { !it.isNaN() }
        androidx.compose.material3.Card(Modifier.fillMaxWidth().padding(start = 12.dp, end = 12.dp, top = 12.dp),
            shape = androidx.compose.foundation.shape.RoundedCornerShape(28.dp),
            colors = androidx.compose.material3.CardDefaults.cardColors(containerColor = cs.surfaceContainerLow)) {
            Row(Modifier.fillMaxWidth().padding(vertical = 20.dp), horizontalArrangement = Arrangement.SpaceEvenly) {
                se.konsiliet.app.ui.components.Ring(hr?.toString() ?: "--", "Headroom", (hr ?: 0) / 100f, cs.primary,
                    icon = androidx.compose.material.icons.Icons.Filled.BatteryChargingFull)
                se.konsiliet.app.ui.components.Ring("$pass/$mal", "Pass i veckan", pass.toFloat() / mal, t.ok,
                    icon = androidx.compose.material.icons.Icons.Filled.FitnessCenter)
                se.konsiliet.app.ui.components.Ring(timmar?.let { Fmt.dec(it) } ?: "--", "Sömn", ((timmar ?: 0.0) / behov).toFloat(), t.sleepLight,
                    unit = "timmar", icon = androidx.compose.material.icons.Icons.Filled.Bedtime)
            }
        }

        // Journalen från 1177: inbyggd, med BankID direkt på telefonen.
        Journal1177Card(autoStart = start1177, onAutoStarted = onStart1177Done)

        // Första dagarna: en checklista i stället för tomma ringar utan förklaring.
        if (i.isNull("headroom") && natt == null) {
            Section("Kom igång") {
                Column(Modifier.padding(vertical = 4.dp)) {
                    listOf(
                        androidx.compose.material.icons.Icons.Filled.HealthAndSafety to "Ge Health Connect behörighet, så läses 30 dagar in som baslinje.",
                        androidx.compose.material.icons.Icons.Filled.Watch to "Öppna Kropp64 på klockan och tillåt puls i bakgrunden.",
                        androidx.compose.material.icons.Icons.Filled.BatterySaver to "Stäng av batterioptimering för Kropp64.",
                        androidx.compose.material.icons.Icons.Filled.Bedtime to "Sov en natt med klockan. Då kommer Headroom.",
                    ).forEach { (ic, txt) ->
                        androidx.compose.material3.ListItem(
                            headlineContent = { Text(txt, style = typo.bodyMedium) },
                            leadingContent = { androidx.compose.material3.Icon(ic, null, tint = cs.primary) },
                            colors = androidx.compose.material3.ListItemDefaults.colors(containerColor = Color.Transparent),
                        )
                    }
                    androidx.compose.material3.FilledTonalButton(onClick = onSettings, modifier = Modifier.padding(start = 16.dp, bottom = 8.dp)) { Text("Öppna Inställningar") }
                }
            }
        }
        // Termerna är skämt, men betydelsen och enheten ska vara ett tryck bort.
        Text(if (ordlista) "Dölj förklaringarna" else "Vad betyder Headroom och zon?", style = Type.label, color = t.accent,
            modifier = Modifier.clickable { ordlista = !ordlista }.padding(horizontal = 20.dp, vertical = 12.dp)
                .semantics { stateDescription = if (ordlista) "utfälld" else "ihopfälld" })
        if (ordlista) i.optJSONObject("ordlista")?.let { o ->
            o.keys().forEach { k ->
                Column(Modifier.padding(horizontal = 20.dp, vertical = 4.dp)) {
                    Text(k, style = Type.label, color = t.ink)
                    Text(o.optString(k), style = Type.body, color = t.ink2)
                }
            }
            i.optString("regler").takeIf { it.isNotBlank() }?.let {
                Text("Reglerna: $it", style = Type.small, color = t.ink3, modifier = Modifier.padding(horizontal = 20.dp, vertical = 6.dp))
            }
        }

        val niva = i.optJSONObject("niva")
        Section("Veckan och sömnen", trailing = niva?.let { "nivå ${it.optInt("niva")} av 4" }) {
            Column(Modifier.padding(horizontal = 20.dp, vertical = 12.dp)) {
                val dagar = vk?.optJSONArray("passdagar")
                val streak = vk?.optInt("veckor_i_rad") ?: 0
                Text((if (dagar != null) "Passdagar: " + (0 until dagar.length()).joinToString { dagar.optString(it) } + ". " else "") +
                    (if (streak > 0) "$streak veckor i rad med målet nått." else "Nivån höjs när två pass i veckan blir av."),
                    style = typo.bodyMedium, color = cs.onSurfaceVariant)
                senastePass?.let { p ->
                    Text("Senaste pass: ${p.optInt("minuter")} min ${p.optString("typ")}, ${Fmt.day(p.optDouble("start"))}" +
                        (if (!p.isNull("puls_medel")) ", medel ${p.optInt("puls_medel")} BPM" else ""), style = typo.bodyMedium, color = cs.onSurface,
                        modifier = Modifier.padding(top = 8.dp))
                }
                sm?.let { s2 ->
                    Text(s2.optString("laggdags_text") + ".", style = typo.bodyMedium, color = cs.onSurface, modifier = Modifier.padding(top = 8.dp))
                    val skuld = s2.optDouble("skuld_h")
                    if (!skuld.isNaN() && skuld > 0) Text("Sömnskuld ${Fmt.duration(skuld * 3600)}.", style = typo.bodySmall,
                        color = if (skuld >= 5) t.avvikelse else cs.onSurfaceVariant)
                }
            }
        }

        // POST-skärmen: idrottsläkarens text under beslutet
        val b = brief?.let { runCatching { JSONObject(it.payload) }.getOrNull() }
        b?.optString("text")?.takeIf { it.isNotBlank() && b.optString("datum") == i.optString("datum") }?.let { text ->
            Section("POST-skärmen", trailing = (if (b.optString("skrivet_av") == "idrottsläkaren") "idrottsläkaren" else "regelverket") +
                ", kl. " + Fmt.hm(brief!!.ts)) {
                Text(text, style = Type.body, color = t.ink2, modifier = Modifier.padding(horizontal = 20.dp, vertical = 12.dp))
            }
        }

        // Fråga teamet: färdiga frågor startar en tråd med ett tryck.
        Section("Fråga läkarteamet", trailing = "svar på några minuter") {
            @OptIn(androidx.compose.foundation.layout.ExperimentalLayoutApi::class)
            androidx.compose.foundation.layout.FlowRow(Modifier.padding(horizontal = 16.dp, vertical = 8.dp),
                horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                FRAGOR.forEach { q ->
                    androidx.compose.material3.SuggestionChip(onClick = { onAsk(q) }, label = { Text(q) },
                        icon = { androidx.compose.material3.Icon(androidx.compose.material.icons.Icons.Filled.QuestionAnswer, null,
                            modifier = Modifier.height(18.dp).width(18.dp)) })
                }
                androidx.compose.material3.AssistChip(onClick = { onAsk("") }, label = { Text("Egen fråga") },
                    leadingIcon = { androidx.compose.material3.Icon(androidx.compose.material.icons.Icons.Filled.Edit, null,
                        modifier = Modifier.height(18.dp).width(18.dp)) })
            }
        }

        // Notiser och fokusläge
        Section("Knuffar", trailing = notiser?.let { "${it.optInt("idag")} av ${it.optInt("budget")} i dag" }) {
            Column(Modifier.padding(horizontal = 20.dp, vertical = 10.dp)) {
                val fokus = notiser?.optDouble("fokus_till")?.takeIf { !it.isNaN() && it > 0 }
                Text(if (fokus != null) "Fokusläge till ${Fmt.hm(fokus)}: inga AFK- eller stressknuffar."
                     else "Tysta timmar ${notiser?.optString("tysta") ?: "23:00-08:00"}. Akuta larm går alltid fram.",
                    style = Type.small, color = t.ink3)
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.padding(top = 6.dp)) {
                    OutlinedButton(onClick = {
                        scope.launch {
                            msg = runCatching {
                                Api.postJson("/api/knuff/svar", JSONObject().put("typ", "fokus").put("svar", if (fokus != null) "av" else "fokus").put("minuter", 120))
                                if (fokus != null) "Fokusläget avslutat." else "Fokusläge i 2 h."
                            }.getOrElse { "Gick inte: ${it.message}" }
                            refresh++
                        }
                    }) { Text(if (fokus != null) "Avsluta fokusläge" else "Jag är mitt i ett pass (2 h)") }
                }
                msg?.let { Text(it, style = Type.small, color = t.ink2, modifier = Modifier.padding(top = 4.dp)) }
                TextButton(onClick = onSettings) { Text("Ändra passdagar, väckning och notiser") }
            }
        }
    }
}

val FRAGOR = listOf(
    "Varför är jag så trött i dag?",
    "Kan jag köra ett hårdare pass i veckan?",
    "Hur påverkar sena spelkvällar min sömn?",
)
