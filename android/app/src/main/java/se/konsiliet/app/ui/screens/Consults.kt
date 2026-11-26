package se.konsiliet.app.ui.screens

import androidx.compose.material3.SegmentedButton

import androidx.compose.foundation.layout.Arrangement

import androidx.compose.foundation.shape.CircleShape

import androidx.compose.foundation.layout.size

import androidx.compose.material.icons.filled.Gavel

import androidx.compose.material.icons.filled.Forum

import androidx.compose.material.icons.filled.CheckCircle

import androidx.compose.material.icons.filled.Visibility

import androidx.compose.material.icons.filled.EventNote

import androidx.compose.material.icons.filled.LocalHospital

import androidx.compose.material.icons.filled.Edit

import androidx.compose.material.icons.automirrored.filled.ArrowBack

import androidx.compose.material.icons.Icons

import android.annotation.SuppressLint
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
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
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.produceState
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import org.json.JSONArray
import org.json.JSONObject
import se.konsiliet.app.data.KonsilietDb
import se.konsiliet.app.data.Prefs
import se.konsiliet.app.net.Api
import se.konsiliet.app.ui.components.Fmt
import se.konsiliet.app.ui.components.Pill
import se.konsiliet.app.ui.components.Section
import se.konsiliet.app.ui.theme.LocalTokens
import se.konsiliet.app.ui.theme.Type

private val BRADSKA = mapOf(
    "ingen" to "Ingen åtgärd", "bevaka" to "Bevaka", "ta_upp_med_varden" to "Ta upp med vården",
    "kontakta_vard_nu" to "Kontakta vården nu",
)

@OptIn(androidx.compose.material3.ExperimentalMaterial3Api::class)
@Composable
fun ConsultsScreen(onOpen: (String) -> Unit, onAsk: () -> Unit = {}) {
    val cs = androidx.compose.material3.MaterialTheme.colorScheme
    val typo = androidx.compose.material3.MaterialTheme.typography
    // Listan först: den svarar på "vad kom teamet fram till?". Kontoret är ett tryck bort.
    var office by rememberSaveable { mutableStateOf(false) }
    Box(Modifier.fillMaxSize()) {
        Column(Modifier.fillMaxSize()) {
            Text("Trådar", style = typo.headlineLarge, color = cs.onSurface, modifier = Modifier.padding(start = 24.dp, top = 20.dp, bottom = 8.dp))
            androidx.compose.material3.SingleChoiceSegmentedButtonRow(Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 4.dp)) {
                listOf(false to "Lista", true to "Kontoret").forEachIndexed { i, (v, l) ->
                    SegmentedButton(selected = office == v, onClick = { office = v },
                        shape = androidx.compose.material3.SegmentedButtonDefaults.itemShape(i, 2)) { Text(l) }
                }
            }
            if (office) OfficeWeb() else ConsultList(onOpen)
        }
        if (!office) androidx.compose.material3.ExtendedFloatingActionButton(onClick = onAsk,
            icon = { androidx.compose.material3.Icon(Icons.Filled.Edit, null) }, text = { Text("Ny tråd") },
            modifier = Modifier.align(Alignment.BottomEnd).padding(16.dp))
    }
}

/** Samma pixelkontor som webben, så att läkarteamet syns jobba även i mobilen. */
@SuppressLint("SetJavaScriptEnabled")
@Composable
private fun OfficeWeb() {
    val t = LocalTokens.current
    val config by Prefs.config.collectAsState()
    var error by remember { mutableStateOf<String?>(null) }
    Box(Modifier.fillMaxSize()) {
        AndroidView(
            modifier = Modifier.fillMaxSize(),
            factory = { ctx ->
                WebView(ctx).apply {
                    settings.javaScriptEnabled = true
                    settings.domStorageEnabled = true
                    setBackgroundColor(android.graphics.Color.TRANSPARENT)
                    webViewClient = object : WebViewClient() {
                        override fun onReceivedError(view: WebView, request: WebResourceRequest, err: WebResourceError) {
                            if (request.isForMainFrame) error = "Kunde inte öppna ${request.url}: ${err.description}"
                        }
                        override fun onPageFinished(view: WebView, url: String) { if (error == null) error = null }
                    }
                }
            },
            update = { wv ->
                val headers = if (config.deviceToken.isNotEmpty()) mapOf("X-Device-Token" to config.deviceToken) else emptyMap()
                // Servern sätter en httpOnly-cookie från ?token=, så att webbappens egna anrop och /ws
                // också är behöriga via Cloudflare Tunnel. Via Tailscale behövs ingen token.
                val q = if (config.deviceToken.isNotEmpty()) "?token=" + java.net.URLEncoder.encode(config.deviceToken, "UTF-8") else ""
                if (wv.url == null || !wv.url!!.startsWith(config.serverUrl)) { error = null; wv.loadUrl(config.serverUrl + "/" + q + "#/kontoret", headers) }
            },
        )
        error?.let {
            Text(it, style = Type.body, color = t.ink2, modifier = Modifier.background(t.bg).fillMaxWidth().padding(20.dp))
        }
    }
}

/** Färg och ikon per brådska, så att listan går att skumma utan att läsa. */
@Composable
private fun bradskaStil(b: String?, pagar: Boolean): Pair<androidx.compose.ui.graphics.Color, androidx.compose.ui.graphics.vector.ImageVector> {
    val t = LocalTokens.current
    val cs = androidx.compose.material3.MaterialTheme.colorScheme
    return when {
        b == "kontakta_vard_nu" -> t.akut to Icons.Filled.LocalHospital
        b == "ta_upp_med_varden" -> t.avvikelse to Icons.Filled.EventNote
        b == "bevaka" -> cs.primary to Icons.Filled.Visibility
        b == "ingen" -> t.ok to Icons.Filled.CheckCircle
        pagar -> cs.tertiary to Icons.Filled.Forum
        else -> cs.onSurfaceVariant to Icons.Filled.Forum
    }
}

@Composable
private fun ConsultList(onOpen: (String) -> Unit) {
    val cs = androidx.compose.material3.MaterialTheme.colorScheme
    val typo = androidx.compose.material3.MaterialTheme.typography
    val list by produceState<JSONArray?>(null) { value = runCatching { Api.getArray("/api/consults?limit=50") }.getOrNull() ?: JSONArray() }
    val arr = list
    if (arr == null) { androidx.compose.material3.LinearProgressIndicator(Modifier.fillMaxWidth().padding(24.dp)); return }
    if (arr.length() == 0) {
        Column(Modifier.fillMaxWidth().padding(40.dp), horizontalAlignment = Alignment.CenterHorizontally) {
            androidx.compose.material3.Icon(Icons.Filled.Forum, null, tint = cs.onSurfaceVariant, modifier = Modifier.size(48.dp))
            Text("Inga trådar ännu", style = typo.titleMedium, color = cs.onSurface, modifier = Modifier.padding(top = 12.dp))
            Text("Vakten startar en när något avviker, eller ställ en fråga själv.", style = typo.bodyMedium, color = cs.onSurfaceVariant)
        }
        return
    }
    val items = remember(arr) { (0 until arr.length()).map { arr.getJSONObject(it) } }
    LazyColumn(Modifier.fillMaxSize(), contentPadding = androidx.compose.foundation.layout.PaddingValues(start = 12.dp, end = 12.dp, top = 8.dp, bottom = 96.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp)) {
        items(items, key = { it.optString("id") }) { c ->
            val trig = c.optJSONObject("trigger")
            val v = c.optJSONObject("verdict")
            val b = v?.optString("bradska")?.takeIf { it.isNotEmpty() }
            val (farg, ic) = bradskaStil(b, c.isNull("ended"))
            androidx.compose.material3.Card(onClick = { onOpen(c.optString("id")) }, modifier = Modifier.fillMaxWidth(),
                shape = androidx.compose.foundation.shape.RoundedCornerShape(24.dp),
                colors = androidx.compose.material3.CardDefaults.cardColors(containerColor = cs.surfaceContainerLow)) {
                Row(Modifier.padding(16.dp)) {
                    Box(Modifier.size(44.dp).background(farg.copy(alpha = 0.16f), CircleShape), contentAlignment = Alignment.Center) {
                        androidx.compose.material3.Icon(ic, null, tint = farg, modifier = Modifier.size(22.dp))
                    }
                    Column(Modifier.padding(start = 14.dp).weight(1f)) {
                        Text(trig?.optString("title")?.ifEmpty { null } ?: trig?.optString("question")?.ifEmpty { null } ?: "Tråd",
                            style = typo.titleMedium, color = cs.onSurface, maxLines = 2)
                        v?.optString("sammanfattning")?.takeIf { it.isNotBlank() }?.let {
                            Text(it, style = typo.bodyMedium, color = cs.onSurfaceVariant, maxLines = 2,
                                overflow = androidx.compose.ui.text.style.TextOverflow.Ellipsis, modifier = Modifier.padding(top = 2.dp))
                        }
                        Row(Modifier.padding(top = 8.dp), verticalAlignment = Alignment.CenterVertically) {
                            Text(Fmt.day(c.optDouble("started")) + " " + Fmt.hm(c.optDouble("started")), style = typo.labelMedium,
                                color = cs.onSurfaceVariant, modifier = Modifier.weight(1f))
                            Text(if (b != null) BRADSKA[b] ?: b else if (c.isNull("ended")) "Pågår" else "", style = typo.labelMedium, color = farg,
                                modifier = Modifier.background(farg.copy(alpha = 0.12f), androidx.compose.foundation.shape.RoundedCornerShape(8.dp))
                                    .padding(horizontal = 8.dp, vertical = 3.dp))
                        }
                    }
                }
            }
        }
    }
}

/** Färg och initial per läkare i chatten. */
private val AGENT_FARG = mapOf(
    "ordforande" to 0xFF5B8DEF, "kardiolog" to 0xFFE5484D, "somn" to 0xFF7C6FE0, "idrott" to 0xFF2FA36B,
    "stress" to 0xFFE0A030, "labb" to 0xFF2BA3B8, "advokat" to 0xFF8A8F98, "granskare" to 0xFFB54A86,
)

@Composable
fun ConsultDetail(id: String, onBack: () -> Unit) {
    val t = LocalTokens.current
    val ctx = LocalContext.current
    val live by remember(id) { KonsilietDb.get(ctx).events().forConsult(id) }.collectAsState(emptyList())
    // Hämta mötet igen när en bedömning kommer in live.
    val verdictSeen = live.any { it.kind == "consult.verdict" }
    val consult by produceState<JSONObject?>(null, id, verdictSeen) {
        value = runCatching { Api.getObject("/api/consults/$id") }.getOrNull()
    }
    LaunchedEffect(id) { syncEvents(ctx) }
    val c = consult
    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(bottom = 24.dp)) {
        val cs = androidx.compose.material3.MaterialTheme.colorScheme
        val typo = androidx.compose.material3.MaterialTheme.typography
        Row(Modifier.fillMaxWidth().padding(start = 4.dp, top = 8.dp), verticalAlignment = Alignment.CenterVertically) {
            androidx.compose.material3.IconButton(onClick = onBack) {
                androidx.compose.material3.Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Tillbaka")
            }
            Text("Tråd", style = typo.titleLarge, color = cs.onSurface)
        }
        val trig = c?.optJSONObject("trigger")
        Text(trig?.optString("title")?.ifEmpty { null } ?: trig?.optString("question")?.ifEmpty { null } ?: "Tråd",
            style = typo.headlineSmall, color = cs.onSurface, modifier = Modifier.padding(horizontal = 24.dp, vertical = 4.dp))
        c?.let { Text("Startat ${Fmt.day(it.optDouble("started"))} ${Fmt.hm(it.optDouble("started"))}" +
            (if (it.isNull("ended")) " · pågår" else ""), style = Type.small, color = t.ink3, modifier = Modifier.padding(horizontal = 20.dp, vertical = 4.dp)) }

        val v = c?.optJSONObject("verdict")
        // Snabbsvaret ur datan kommer inom sekunder (regelverket, ingen språkmodell), medan teamet arbetar.
        val kort = live.lastOrNull { it.kind == "consult.kort" }?.let { runCatching { JSONObject(it.payload) }.getOrNull() }
        if (v == null && kort != null) {
            Section("Snabbsvar ur datan", trailing = "teamet svarar om ca ${maxOf(1, kort.optInt("eta_s") / 60)} min") {
                Text(kort.optString("bradska_text"), style = Type.heading, color = t.ink,
                    modifier = Modifier.padding(start = 20.dp, end = 20.dp, top = 12.dp))
                kort.optJSONArray("skal")?.let { a -> if (a.length() > 0) Text("Regelverket: " + (0 until a.length()).joinToString("; ") { a.optString(it) },
                    style = Type.small, color = t.ink3, modifier = Modifier.padding(horizontal = 20.dp)) }
                kort.optJSONArray("rader")?.let { a ->
                    for (k in 0 until a.length()) Text("· " + a.optString(k), style = Type.body, color = t.ink2,
                        modifier = Modifier.padding(horizontal = 20.dp, vertical = 2.dp))
                }
                Spacer(Modifier.height(8.dp))
            }
        } else if (v == null && c != null && c.isNull("ended")) {
            Text("Teamet arbetar. Snabbsvaret kommer om några sekunder.", style = Type.body, color = t.ink3, modifier = Modifier.padding(20.dp))
        }
        v?.optJSONArray("atgarder")?.let { a -> if (a.length() > 0) {
            Section("Gör så här") {
                for (k in 0 until a.length()) Row(Modifier.padding(horizontal = 20.dp, vertical = 8.dp), verticalAlignment = Alignment.CenterVertically) {
                    Box(Modifier.size(28.dp).background(androidx.compose.material3.MaterialTheme.colorScheme.primary, CircleShape), contentAlignment = Alignment.Center) {
                        Text("${k + 1}", style = androidx.compose.material3.MaterialTheme.typography.labelLarge, color = androidx.compose.material3.MaterialTheme.colorScheme.onPrimary)
                    }
                    Text(a.optString(k), style = androidx.compose.material3.MaterialTheme.typography.bodyLarge, color = t.ink, modifier = Modifier.padding(start = 12.dp))
                }
            }
        } }
        if (v != null) {
            val (farg, ic) = bradskaStil(v.optString("bradska"), false)
            androidx.compose.material3.Card(Modifier.fillMaxWidth().padding(start = 12.dp, end = 12.dp, top = 16.dp),
                shape = androidx.compose.foundation.shape.RoundedCornerShape(28.dp),
                colors = androidx.compose.material3.CardDefaults.cardColors(containerColor = farg.copy(alpha = 0.14f))) {
                Column(Modifier.padding(20.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        androidx.compose.material3.Icon(ic, null, tint = farg, modifier = Modifier.size(28.dp))
                        Column(Modifier.padding(start = 12.dp)) {
                            Text("Markerad som lösning", style = typo.labelLarge, color = cs.onSurfaceVariant)
                            Text(BRADSKA[v.optString("bradska")] ?: v.optString("bradska"), style = typo.titleLarge, color = cs.onSurface)
                        }
                    }
                    Text(v.optString("sammanfattning"), style = typo.bodyLarge, color = cs.onSurface, modifier = Modifier.padding(top = 12.dp))
                    v.optJSONArray("rad")?.let { a -> if (a.length() > 0) {
                        Text("Råd", style = typo.titleSmall, color = cs.onSurface, modifier = Modifier.padding(top = 14.dp))
                        for (i in 0 until a.length()) Text("• " + a.optString(i), style = typo.bodyMedium, color = cs.onSurface, modifier = Modifier.padding(top = 4.dp))
                    } }
                    v.optJSONArray("fragor_till_varden")?.let { a -> if (a.length() > 0) {
                        Text("Frågor till vården", style = typo.titleSmall, color = cs.onSurface, modifier = Modifier.padding(top = 14.dp))
                        for (i in 0 until a.length()) Text("• " + a.optString(i), style = typo.bodyMedium, color = cs.onSurface, modifier = Modifier.padding(top = 4.dp))
                    } }
                }
            }
            v.optJSONArray("belagda_pastaenden")?.let { a -> if (a.length() > 0) {
                Section("Belagda påståenden", trailing = "${a.length()} st") {
                    for (i in 0 until a.length()) {
                        val p = a.optJSONObject(i) ?: continue
                        Column(Modifier.padding(horizontal = 20.dp, vertical = 8.dp)) {
                            Text(p.optString("text"), style = typo.bodyMedium, color = cs.onSurface)
                            val k = p.optJSONArray("kallor")
                            if (k != null) Text("Källor: " + (0 until k.length()).joinToString { k.optString(it) }, style = typo.labelSmall, color = cs.onSurfaceVariant)
                        }
                    }
                }
            } }
        }

        // Samtalet: från servern om mötet är klart, annars live från /ws
        val transcript = c?.optJSONArray("transcript")
        Section("Inläggen") {
            val says = if (transcript != null && transcript.length() > 0)
                (0 until transcript.length()).map { transcript.getJSONObject(it) }.filter { it.optString("kind") in setOf("agent.say", "review.strike") }
            else live.filter { it.kind == "agent.say" || it.kind == "review.strike" }
                .map { JSONObject(it.payload).put("kind", it.kind) }
            if (says.isEmpty()) Text("Inget sagt ännu.", style = Type.body, color = t.ink3, modifier = Modifier.padding(20.dp))
            says.forEach { s ->
                if (s.optString("kind") == "review.strike") {
                    Row(Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 6.dp)) {
                        Box(Modifier.size(36.dp).background(t.avvikelse.copy(alpha = 0.16f), CircleShape), contentAlignment = Alignment.Center) {
                            androidx.compose.material3.Icon(Icons.Filled.Gavel, null, tint = t.avvikelse, modifier = Modifier.size(18.dp))
                        }
                        Column(Modifier.padding(start = 10.dp).background(t.avvikelse.copy(alpha = 0.10f),
                            androidx.compose.foundation.shape.RoundedCornerShape(topStart = 4.dp, topEnd = 18.dp, bottomEnd = 18.dp, bottomStart = 18.dp))
                            .padding(12.dp)) {
                            Text("Strukit av moderatorn", style = androidx.compose.material3.MaterialTheme.typography.labelLarge, color = t.avvikelse)
                            Text(s.optString("claim"), style = androidx.compose.material3.MaterialTheme.typography.bodyMedium.copy(
                                textDecoration = androidx.compose.ui.text.style.TextDecoration.LineThrough), color = t.ink2)
                            Text("Anledning: " + s.optString("reason"), style = androidx.compose.material3.MaterialTheme.typography.bodySmall, color = t.ink2)
                        }
                    }
                } else {
                    val agent = s.optString("agent")
                    val farg = androidx.compose.ui.graphics.Color(AGENT_FARG[agent] ?: 0xFF8A8F98)
                    val namn = AGENT_NAMES[agent] ?: agent
                    Row(Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 6.dp)) {
                        Box(Modifier.size(36.dp).background(farg, CircleShape), contentAlignment = Alignment.Center) {
                            Text(namn.take(1), style = androidx.compose.material3.MaterialTheme.typography.titleSmall, color = androidx.compose.ui.graphics.Color.White)
                        }
                        Column(Modifier.padding(start = 10.dp).background(androidx.compose.material3.MaterialTheme.colorScheme.surfaceContainerHighest,
                            androidx.compose.foundation.shape.RoundedCornerShape(topStart = 4.dp, topEnd = 18.dp, bottomEnd = 18.dp, bottomStart = 18.dp))
                            .padding(12.dp)) {
                            Text(namn + if (s.optString("to") !in listOf("", "alla")) " → " + (AGENT_NAMES[s.optString("to")] ?: s.optString("to")) else "",
                                style = androidx.compose.material3.MaterialTheme.typography.labelLarge, color = farg)
                            Text(s.optString("text"), style = androidx.compose.material3.MaterialTheme.typography.bodyMedium, color = t.ink)
                            val cites = s.optJSONArray("cites")
                            if (cites != null && cites.length() > 0) Text("Källor: " + (0 until cites.length()).joinToString { cites.optString(it) },
                                style = androidx.compose.material3.MaterialTheme.typography.labelSmall, color = t.ink3, modifier = Modifier.padding(top = 4.dp))
                        }
                    }
                }
            }
        }
        Spacer(Modifier.width(1.dp))
    }
}
