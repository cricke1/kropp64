package se.konsiliet.app.ui.screens

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
fun IdagScreen(onAsk: (String) -> Unit, onOpenConsult: (String) -> Unit, onSettings: () -> Unit) {
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

    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(bottom = 28.dp)) {
        Text("Idag", style = Type.title, color = t.ink,
            modifier = Modifier.padding(start = 20.dp, end = 20.dp, top = 18.dp).semantics { heading() })
        val i = idag
        if (i == null) {
            Text(if (offline) "Ingen kontakt med servern och inget sparat svar än. Kontrollera adressen under Inställningar."
                 else "Hämtar dagens svar ...", style = Type.body, color = t.ink3, modifier = Modifier.padding(20.dp))
            if (offline) TextButton(onClick = onSettings, modifier = Modifier.padding(horizontal = 8.dp)) { Text("Öppna Inställningar") }
            return@Column
        }
        val plan = i.optJSONObject("plan")
        val beslut = i.optString("beslut")
        val farg = beslutFarg(beslut, t)
        val rubrik = i.optString("rubrik")
        val planText = plan?.optString("text").orEmpty()
        val varfor = i.optString("varfor")
        // Beslutskortet: rubrik, plan, varför. En skärmläsare läser det som en mening.
        Row(Modifier.fillMaxWidth().padding(start = 20.dp, end = 20.dp, top = 14.dp).height(IntrinsicSize.Min).background(t.surface)
            .semantics(mergeDescendants = true) { contentDescription = "$rubrik. $planText. $varfor" }
            .heightIn(min = 120.dp)) {
            Box(Modifier.width(6.dp).fillMaxHeight().background(farg))
            Column(Modifier.padding(16.dp)) {
                Text(rubrik, style = Type.title.copy(fontSize = Type.title.fontSize * 1.25f), color = t.ink)
                if (planText.isNotBlank()) Text(planText, style = Type.value, color = t.ink, modifier = Modifier.padding(top = 6.dp))
                plan?.optString("forslag")?.takeIf { it.isNotBlank() }?.let {
                    Text(it.replaceFirstChar { c -> c.uppercase() }, style = Type.body, color = t.ink2, modifier = Modifier.padding(top = 2.dp))
                }
                if (varfor.isNotBlank()) Text("Varför: $varfor.", style = Type.body, color = t.ink2, modifier = Modifier.padding(top = 10.dp))
                i.optString("matt").takeIf { it.isNotBlank() }?.let {
                    Text("Mätt: $it.", style = Type.small, color = t.ink3, modifier = Modifier.padding(top = 6.dp))
                }
                i.optJSONObject("oppet")?.let { o ->
                    o.optString("consult_id").takeIf { it.isNotBlank() }?.let { cid ->
                        TextButton(onClick = { onOpenConsult(cid) }) { Text("Öppna tråden") }
                    }
                }
            }
        }
        if (offline) {
            val at = cached?.second ?: 0L
            Text("Ingen kontakt med servern. Visar svaret från " + Fmt.ago(at, now) + ".", style = Type.small, color = t.avvikelse,
                modifier = Modifier.padding(horizontal = 20.dp, vertical = 6.dp))
        }
        // Första dagarna: tom data är inget fel, men det ska stå vad som behövs.
        if (i.isNull("headroom") && i.optJSONObject("somn")?.optJSONObject("natt") == null) {
            Section("Kom igång") {
                Column(Modifier.padding(horizontal = 20.dp, vertical = 10.dp)) {
                    listOf(
                        "Ge Health Connect behörighet (Inställningar), så läses de senaste 30 dagarna in som baslinje.",
                        "Öppna Kropp64 på klockan och tillåt puls i bakgrunden.",
                        "Stäng av batterioptimering för Kropp64 (Inställningar).",
                        "Sov en natt med klockan. Då kommer Headroom och dagens råd bygger på din sömn.",
                    ).forEachIndexed { k, s2 -> Text("${k + 1}. $s2", style = Type.body, color = t.ink2, modifier = Modifier.padding(vertical = 3.dp)) }
                    TextButton(onClick = onSettings) { Text("Öppna Inställningar") }
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

        // Veckan
        val vk = i.optJSONObject("veckan")
        val niva = i.optJSONObject("niva")
        Section("Veckans pass", trailing = niva?.let { "plan vecka ${it.optInt("vecka_nr")}, nivå ${it.optInt("niva")} av 4" }) {
            Column(Modifier.padding(horizontal = 20.dp, vertical = 12.dp)) {
                val pass = vk?.optInt("pass") ?: 0
                val mal = vk?.optInt("mal") ?: 3
                Row(verticalAlignment = Alignment.CenterVertically,
                    modifier = Modifier.semantics(mergeDescendants = true) { contentDescription = "$pass av $mal pass den här veckan" }) {
                    for (k in 1..mal) {
                        Box(Modifier.padding(end = 6.dp).width(28.dp).height(10.dp).background(if (k <= pass) t.ok else t.grid))
                    }
                    Text("  $pass av $mal", style = Type.value, color = t.ink)
                }
                val dagar = vk?.optJSONArray("passdagar")
                val streak = vk?.optInt("veckor_i_rad") ?: 0
                Text((if (dagar != null) "Passdagar: " + (0 until dagar.length()).joinToString { dagar.optString(it) } + ". " else "") +
                    (if (streak > 0) "$streak veckor i rad med målet nått." else "Målet: $mal pass i veckan, nivån höjs när två blir av."),
                    style = Type.small, color = t.ink3, modifier = Modifier.padding(top = 6.dp))
            }
            senastePass?.let { p ->
                val z = p.optJSONArray("zon_minuter")
                val zt = if (z != null) (0 until z.length()).filter { z.optInt(it) > 0 }.joinToString { "zon ${it + 1}: ${z.optInt(it)} min" } else ""
                Column(Modifier.padding(horizontal = 20.dp, vertical = 4.dp)) {
                    Text("Senaste pass: ${p.optInt("minuter")} min ${p.optString("typ")}, ${Fmt.day(p.optDouble("start"))}", style = Type.label, color = t.ink)
                    if (!p.isNull("puls_medel")) Text("Medelpuls ${p.optInt("puls_medel")} BPM, max ${p.optInt("puls_max")} BPM. $zt", style = Type.small, color = t.ink2)
                    Text(p.optString("rad"), style = Type.small, color = t.ink3)
                }
            }
        }

        // Sömnen
        val sm = i.optJSONObject("somn")
        Section("Viloläge (sömn)", trailing = sm?.optJSONObject("natt")?.let { "i natt " + Fmt.duration(it.optDouble("timmar") * 3600) }) {
            sm?.let { s ->
                Column(Modifier.padding(horizontal = 20.dp, vertical = 12.dp)) {
                    Text(s.optString("laggdags_text") + ".", style = Type.body, color = t.ink)
                    val skuld = s.optDouble("skuld_h")
                    if (!skuld.isNaN()) Text("Sömnskuld ${Fmt.duration(skuld * 3600)} på ${s.optInt("natter_med_data")} nätter (mot behovet ${Fmt.dec(s.optDouble("behov_h"))} h).",
                        style = Type.small, color = if (skuld >= 5) t.avvikelse else t.ink3, modifier = Modifier.padding(top = 4.dp))
                    val sena = s.optInt("sena_natter_vid_datorn")
                    if (sena > 0) Text("Vid datorn efter midnatt $sena av 7 nätter.", style = Type.small, color = t.ink3)
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
        Section("Fråga teamet", trailing = "snabbsvar direkt, tråden på några minuter") {
            Column(Modifier.padding(horizontal = 12.dp, vertical = 6.dp)) {
                FRAGOR.forEach { q -> TextButton(onClick = { onAsk(q) }) { Text(q, style = Type.body) } }
                TextButton(onClick = { onAsk("") }) { Text("Egen fråga ...", style = Type.body, color = t.ink2) }
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
