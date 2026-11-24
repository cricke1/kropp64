package se.konsiliet.app.ui.screens

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

@Composable
fun ConsultsScreen(onOpen: (String) -> Unit) {
    val t = LocalTokens.current
    var office by rememberSaveable { mutableStateOf(true) }
    Column(Modifier.fillMaxSize()) {
        Row(Modifier.fillMaxWidth().padding(start = 20.dp, end = 12.dp, top = 12.dp, bottom = 6.dp), verticalAlignment = Alignment.CenterVertically) {
            Text("Konsiliet", style = Type.title, color = t.ink, modifier = Modifier.weight(1f))
            listOf(true to "Kontoret", false to "Möten").forEach { (v, l) ->
                Text(l, style = Type.label, color = if (office == v) t.ink else t.ink3,
                    modifier = Modifier.clickable { office = v }.padding(horizontal = 10.dp, vertical = 8.dp))
            }
        }
        Box(Modifier.fillMaxWidth().height(1.dp).background(t.rule))
        if (office) OfficeWeb() else ConsultList(onOpen)
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

@Composable
private fun ConsultList(onOpen: (String) -> Unit) {
    val t = LocalTokens.current
    val list by produceState<JSONArray?>(null) { value = runCatching { Api.getArray("/api/consults?limit=50") }.getOrNull() ?: JSONArray() }
    val arr = list
    if (arr == null) { Text("Hämtar ...", style = Type.body, color = t.ink3, modifier = Modifier.padding(20.dp)); return }
    if (arr.length() == 0) { Text("Inga möten ännu, eller ingen kontakt med servern.", style = Type.body, color = t.ink3, modifier = Modifier.padding(20.dp)); return }
    val items = (0 until arr.length()).map { arr.getJSONObject(it) }
    LazyColumn(Modifier.fillMaxSize()) {
        items(items, key = { it.optString("id") }) { c ->
            val trig = c.optJSONObject("trigger")
            val v = c.optJSONObject("verdict")
            Column(Modifier.fillMaxWidth().clickable { onOpen(c.optString("id")) }.padding(horizontal = 20.dp, vertical = 14.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(Fmt.day(c.optDouble("started")) + " " + Fmt.hm(c.optDouble("started")), style = Type.small, color = t.ink3,
                        modifier = Modifier.weight(1f))
                    val b = v?.optString("bradska")
                    if (b != null && b.isNotEmpty()) Pill(BRADSKA[b] ?: b, when (b) {
                        "kontakta_vard_nu" -> t.akut; "ta_upp_med_varden" -> t.avvikelse; else -> t.ink2 })
                    else if (c.isNull("ended")) Pill("Pågår", t.accent)
                }
                Spacer(Modifier.height(4.dp))
                Text(trig?.optString("title")?.ifEmpty { null } ?: trig?.optString("question")?.ifEmpty { null } ?: "Möte",
                    style = Type.heading, color = t.ink)
                v?.optString("sammanfattning")?.takeIf { it.isNotBlank() }?.let {
                    Text(it, style = Type.body.copy(fontSize = Type.small.fontSize, lineHeight = Type.small.lineHeight), color = t.ink2, maxLines = 3)
                }
            }
            Box(Modifier.fillMaxWidth().padding(start = 20.dp).height(1.dp).background(t.grid))
        }
    }
}

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
        Row(Modifier.fillMaxWidth().padding(start = 8.dp, top = 6.dp), verticalAlignment = Alignment.CenterVertically) {
            TextButton(onClick = onBack) { Text("Tillbaka") }
        }
        val trig = c?.optJSONObject("trigger")
        Text(trig?.optString("title")?.ifEmpty { null } ?: trig?.optString("question")?.ifEmpty { null } ?: "Konsilium",
            style = Type.title, color = t.ink, modifier = Modifier.padding(horizontal = 20.dp))
        c?.let { Text("Startat ${Fmt.day(it.optDouble("started"))} ${Fmt.hm(it.optDouble("started"))}" +
            (if (it.isNull("ended")) " · pågår" else ""), style = Type.small, color = t.ink3, modifier = Modifier.padding(horizontal = 20.dp, vertical = 4.dp)) }

        val v = c?.optJSONObject("verdict")
        if (v != null) {
            Section("Bedömning", trailing = BRADSKA[v.optString("bradska")]) {
                Text(v.optString("sammanfattning"), style = Type.body, color = t.ink, modifier = Modifier.padding(horizontal = 20.dp, vertical = 12.dp))
                v.optJSONArray("rad")?.let { a -> if (a.length() > 0) {
                    Text("Råd", style = Type.label, color = t.ink2, modifier = Modifier.padding(horizontal = 20.dp))
                    for (i in 0 until a.length()) Text("· " + a.optString(i), style = Type.body, color = t.ink, modifier = Modifier.padding(horizontal = 20.dp, vertical = 2.dp))
                } }
                v.optJSONArray("fragor_till_varden")?.let { a -> if (a.length() > 0) {
                    Spacer(Modifier.height(10.dp))
                    Text("Frågor till vården", style = Type.label, color = t.ink2, modifier = Modifier.padding(horizontal = 20.dp))
                    for (i in 0 until a.length()) Text("· " + a.optString(i), style = Type.body, color = t.ink, modifier = Modifier.padding(horizontal = 20.dp, vertical = 2.dp))
                } }
                v.optJSONArray("belagda_pastaenden")?.let { a -> if (a.length() > 0) {
                    Spacer(Modifier.height(10.dp))
                    Text("Belagda påståenden", style = Type.label, color = t.ink2, modifier = Modifier.padding(horizontal = 20.dp))
                    for (i in 0 until a.length()) {
                        val p = a.optJSONObject(i) ?: continue
                        Column(Modifier.padding(horizontal = 20.dp, vertical = 4.dp)) {
                            Text(p.optString("text"), style = Type.body, color = t.ink)
                            val k = p.optJSONArray("kallor")
                            if (k != null) Text("Källor: " + (0 until k.length()).joinToString { k.optString(it) }, style = Type.small, color = t.ink3)
                        }
                    }
                } }
            }
        }

        // Samtalet: från servern om mötet är klart, annars live från /ws
        val transcript = c?.optJSONArray("transcript")
        Section("Samtalet") {
            val says = if (transcript != null && transcript.length() > 0)
                (0 until transcript.length()).map { transcript.getJSONObject(it) }.filter { it.optString("kind") in setOf("agent.say", "review.strike") }
            else live.filter { it.kind == "agent.say" || it.kind == "review.strike" }
                .map { JSONObject(it.payload).put("kind", it.kind) }
            if (says.isEmpty()) Text("Inget sagt ännu.", style = Type.body, color = t.ink3, modifier = Modifier.padding(20.dp))
            says.forEach { s ->
                Column(Modifier.fillMaxWidth().padding(horizontal = 20.dp, vertical = 8.dp)) {
                    if (s.optString("kind") == "review.strike") {
                        Text("Faktagranskaren strök", style = Type.label, color = t.avvikelse)
                        Text(s.optString("claim") + " (" + s.optString("reason") + ")", style = Type.body, color = t.ink2)
                    } else {
                        Text((AGENT_NAMES[s.optString("agent")] ?: s.optString("agent")) + " till " +
                            (AGENT_NAMES[s.optString("to")] ?: s.optString("to")), style = Type.label, color = t.ink2)
                        Text(s.optString("text"), style = Type.body, color = t.ink)
                        val cites = s.optJSONArray("cites")
                        if (cites != null && cites.length() > 0) Text("Källor: " + (0 until cites.length()).joinToString { cites.optString(it) },
                            style = Type.small, color = t.ink3)
                    }
                }
            }
        }
        Spacer(Modifier.width(1.dp))
    }
}
