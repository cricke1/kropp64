package se.konsiliet.app.ui.screens

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.background

import androidx.compose.foundation.layout.width

import androidx.compose.ui.graphics.Color

import androidx.compose.material.icons.Icons

import androidx.compose.material.icons.filled.Thermostat

import androidx.compose.material.icons.filled.Air

import androidx.compose.material.icons.filled.WaterDrop

import androidx.compose.material.icons.filled.Bedtime

import androidx.compose.material.icons.filled.MonitorHeart

import androidx.compose.material.icons.filled.DirectionsWalk

import androidx.compose.material.icons.filled.Favorite

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.produceState
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import java.util.Calendar
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.launch
import org.json.JSONArray
import org.json.JSONObject
import se.konsiliet.app.data.KonsilietDb
import se.konsiliet.app.data.Prefs
import se.konsiliet.app.data.isTestSource
import se.konsiliet.app.link.Live
import se.konsiliet.app.net.Api
import se.konsiliet.app.ui.components.Fmt
import se.konsiliet.app.ui.components.GoalBar
import se.konsiliet.app.ui.components.Hypnogram
import se.konsiliet.app.ui.components.Legend
import se.konsiliet.app.ui.components.ReadoutRow
import se.konsiliet.app.ui.components.Section
import se.konsiliet.app.ui.components.StatusDot
import se.konsiliet.app.ui.components.TraceChart
import se.konsiliet.app.ui.theme.LocalTokens
import se.konsiliet.app.ui.theme.Type

fun sourceLabel(src: String?): String = when {
    src == null -> ""
    isTestSource(src) -> "testdata från emulator"
    src == "watch" -> "klockan"
    src == "health_connect" -> "Health Connect"
    else -> src
}

private fun midnight(): Double = Calendar.getInstance().apply {
    set(Calendar.HOUR_OF_DAY, 0); set(Calendar.MINUTE, 0); set(Calendar.SECOND, 0); set(Calendar.MILLISECOND, 0)
}.timeInMillis / 1000.0

@Composable
fun TodayScreen() {
    val t = LocalTokens.current
    val ctx = LocalContext.current
    val db = remember { KonsilietDb.get(ctx) }
    var now by remember { mutableLongStateOf(System.currentTimeMillis()) }
    LaunchedEffect(Unit) { while (true) { delay(15_000); now = System.currentTimeMillis() } }
    val from24 = remember(now / 600_000) { now / 1000.0 - 24 * 3600 }
    val today = remember(now / 600_000) { midnight() }

    val hrSeries by remember(from24) { db.samples().series("hr", from24) }.collectAsState(emptyList())
    val hrLatest by remember { db.samples().latest("hr") }.collectAsState(null)
    val live by Live.samples.collectAsState()
    val hrv by remember { db.samples().latest("hrv_rmssd") }.collectAsState(null)
    val rest by remember { db.samples().latest("hr_resting") }.collectAsState(null)
    val spo2 by remember { db.samples().latest("spo2") }.collectAsState(null)
    val resp by remember { db.samples().latest("resp_rate") }.collectAsState(null)
    val skin by remember { db.samples().latest("skin_temp_delta") }.collectAsState(null)
    val stepsWatch by remember(today) { db.samples().sumSince("steps", "watch", today) }.collectAsState(0.0)
    val stepsEmu by remember(today) { db.samples().sumSince("steps", "watch-emulator", today) }.collectAsState(0.0)
    val stepsHc by remember(today) { db.samples().sumSince("steps", "health_connect", today) }.collectAsState(0.0)
    val sleep by remember { db.sleep().lastSince(now / 1000.0 - 36 * 3600) }.collectAsState(null)
    val config by Prefs.config.collectAsState()
    val link by Prefs.link.collectAsState()
    val queue by remember { db.samples().pendingFlow() }.collectAsState(0)
    val brief by remember { db.events().recent(400).map { l -> l.firstOrNull { it.kind == "brief.morgon" } } }.collectAsState(null)

    var refresh by remember { mutableIntStateOf(0) }
    val recovery by produceState<JSONObject?>(null, refresh) {
        while (true) { value = runCatching { Api.getObject("/api/aterhamtning") }.getOrNull() ?: value; delay(300_000) }
    }
    val datorn by produceState<JSONObject?>(null, refresh) {
        value = runCatching { Api.getObject("/api/datorn?hours=24") }.getOrNull()
    }
    val scope = rememberCoroutineScope()
    var briefMsg by remember { mutableStateOf<String?>(null) }

    // Färskaste pulsen: live från servern eller senaste lokala punkten.
    val liveHr = live["hr"]
    val hrTs: Double?; val hrVal: Double?; val hrSrc: String?
    if (liveHr != null && (hrLatest == null || liveHr.ts > hrLatest!!.ts)) { hrTs = liveHr.ts; hrVal = liveHr.value; hrSrc = "servern (live)" }
    else { hrTs = hrLatest?.ts; hrVal = hrLatest?.value; hrSrc = sourceLabel(hrLatest?.source) }

    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(bottom = 24.dp)) {
        // Rubrikrad
        Row(Modifier.fillMaxWidth().padding(start = 20.dp, end = 20.dp, top = 18.dp), verticalAlignment = Alignment.CenterVertically) {
            Text("Sensorer", style = androidx.compose.material3.MaterialTheme.typography.headlineLarge, color = t.ink, modifier = Modifier.weight(1f))
            StatusDot(if (link.wsConnected) t.ok else t.avvikelse)
            Text("  " + if (link.wsConnected) "Ansluten" else "Frånkopplad", style = Type.small, color = t.ink2)
        }

        // Puls: stort kort med siffra och dygnskurva.
        val cs = androidx.compose.material3.MaterialTheme.colorScheme
        val typo = androidx.compose.material3.MaterialTheme.typography
        androidx.compose.material3.Card(Modifier.fillMaxWidth().padding(start = 12.dp, end = 12.dp, top = 16.dp),
            shape = androidx.compose.foundation.shape.RoundedCornerShape(28.dp),
            colors = androidx.compose.material3.CardDefaults.cardColors(containerColor = cs.surfaceContainerLow)) {
            Column(Modifier.padding(20.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    androidx.compose.material3.Icon(Icons.Filled.Favorite, null, tint = t.akut, modifier = Modifier.height(20.dp).width(20.dp))
                    Text("  Klockfrekvens (puls)", style = typo.labelLarge, color = cs.onSurfaceVariant)
                }
                Row(verticalAlignment = Alignment.Bottom) {
                    Text(hrVal?.let { Fmt.int(it) } ?: "--", style = typo.displayLarge.copy(fontFeatureSettings = se.konsiliet.app.ui.theme.TNUM), color = cs.onSurface)
                    Text("  BPM", style = typo.titleMedium, color = cs.onSurfaceVariant, modifier = Modifier.padding(bottom = 12.dp))
                }
                val stale = hrTs != null && now / 1000.0 - hrTs > 15 * 60
                Text(
                    if (hrTs == null) "Ingen puls mottagen ännu"
                    else "${Fmt.ago((hrTs * 1000).toLong(), now)} · $hrSrc" + if (stale) " · inte aktuell" else "",
                    style = typo.bodySmall, color = if (isTestSource(hrLatest?.source)) t.avvikelse else cs.onSurfaceVariant,
                )
                Spacer(Modifier.height(12.dp))
                val chartFrom = hrSeries.firstOrNull()?.let { maxOf(from24, it.ts - 15 * 60) } ?: from24
                TraceChart(hrSeries, chartFrom, now / 1000.0, unit = "BPM")
                if (hrSeries.isNotEmpty()) {
                    Text((if (chartFrom > from24 + 60) "Sedan ${Fmt.hm(chartFrom)}" else "Senaste dygnet") + ": min ${Fmt.int(hrSeries.minOf { it.value })} · max ${Fmt.int(hrSeries.maxOf { it.value })}",
                        style = typo.bodySmall, color = cs.onSurfaceVariant, modifier = Modifier.padding(top = 6.dp))
                }
            }
        }

        // Rutnät med övriga sensorer
        val steps = maxOf(stepsWatch, stepsHc, stepsEmu)
        fun nar(x: se.konsiliet.app.data.Latest?) = x?.let { Fmt.ago((it.ts * 1000).toLong(), now) }
        val rutor = listOf(
            Triple(Icons.Filled.DirectionsWalk, "Steg", Triple(Fmt.int(steps), "av ${Fmt.int(config.stepsGoal.toDouble())}", t.ok)),
            Triple(Icons.Filled.MonitorHeart, "HRV", Triple(hrv?.let { Fmt.dec(it.value) } ?: "--", "ms", cs.primary)),
            Triple(Icons.Filled.Bedtime, "Vilopuls", Triple(rest?.let { Fmt.int(it.value) } ?: "--", "BPM", t.sleepLight)),
            Triple(Icons.Filled.WaterDrop, "Syremättnad", Triple(spo2?.let { Fmt.dec(it.value) } ?: "--", "%", Color(0xFF4FA3E0))),
            Triple(Icons.Filled.Air, "Andning", Triple(resp?.let { Fmt.dec(it.value) } ?: "--", "/min", Color(0xFF5BB8A8))),
            Triple(Icons.Filled.Thermostat, "Hudtemp", Triple(skin?.let { (if (it.value >= 0) "+" else "") + Fmt.dec(it.value, 1) } ?: "--", "°C", t.avvikelse)),
        )
        val noter = listOf(null, nar(hrv), nar(rest), nar(spo2), nar(resp), nar(skin))
        Column(Modifier.padding(horizontal = 12.dp, vertical = 6.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            rutor.chunked(2).forEachIndexed { r, par ->
                Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    par.forEachIndexed { k, (ic, lbl, v) ->
                        se.konsiliet.app.ui.components.StatTile(ic, lbl, v.first, v.second, v.third, Modifier.weight(1f), note = noter[r * 2 + k])
                    }
                }
            }
        }

        // Återhämtning (beräknas på servern; formeln visas så att siffran går att granska)
        Section("Headroom", trailing = "beräknas på servern") {
            val p = recovery
            val score = p?.optInt("poang", -1)?.takeIf { p.has("poang") && !p.isNull("poang") && it >= 0 }
            ReadoutRow("Headroom", score?.toString(), "av 100",
                note = when {
                    p == null -> "Servern svarar inte"
                    score == null -> p.optString("kommentar", "för lite data")
                    else -> p.optString("formel")
                })
            val delar = p?.optJSONObject("delar")
            delar?.optJSONObject("hrv")?.let {
                ReadoutRow("Timingmarginal (HRV) i natt", Fmt.dec(it.optDouble("natt_ms")), "ms", note = "baslinje ${Fmt.dec(it.optDouble("baslinje_ms"))} ms · z ${Fmt.dec(it.optDouble("z"), 2)}")
            }
            delar?.optJSONObject("vilopuls")?.let {
                ReadoutRow("Idle-klock i natt", Fmt.dec(it.optDouble("natt")), "BPM", note = "baslinje ${Fmt.dec(it.optDouble("baslinje"))} · z ${Fmt.dec(it.optDouble("z"), 2)}")
            }
            delar?.optJSONObject("somn")?.let { ReadoutRow("Viloläge", Fmt.dec(it.optDouble("timmar")), "h") }
        }

        // Sömn
        Section("Viloläge i natt", trailing = sleep?.let { sourceLabel(it.source) }) {
            val s = sleep
            if (s == null) {
                ReadoutRow("Sömnpass", null)
            } else {
                val arr = runCatching { JSONArray(s.stages) }.getOrDefault(JSONArray())
                val stages = (0 until arr.length()).map { arr.getJSONObject(it) }
                    .map { Triple(it.optDouble("start"), it.optDouble("end"), it.optString("stage")) }
                val tot = stages.groupBy { it.third }.mapValues { (_, v) -> v.sumOf { it.second - it.first } }
                val asleep = tot.filterKeys { it != "awake" && it != "unknown" }.values.sum()
                ReadoutRow("Sovit", Fmt.duration(if (asleep > 0) asleep else s.end - s.start), "",
                    note = "${Fmt.hm(s.start)} till ${Fmt.hm(s.end)}")
                if (stages.isNotEmpty()) {
                    Column(Modifier.padding(horizontal = 20.dp, vertical = 12.dp)) { Hypnogram(stages) }
                    Legend(listOf(
                        "Djup ${Fmt.duration(tot["deep"] ?: 0.0)}" to t.sleepDeep,
                        "REM ${Fmt.duration(tot["rem"] ?: 0.0)}" to t.sleepRem,
                    ))
                    Spacer(Modifier.height(4.dp))
                    Legend(listOf(
                        "Lätt ${Fmt.duration(tot["light"] ?: 0.0)}" to t.sleepLight,
                        "Vaken ${Fmt.duration(tot["awake"] ?: 0.0)}" to t.sleepAwake,
                    ))
                }
            }
        }

        // Datorn och mobilen: minuter per kategori senaste dygnet, som staplar.
        @Composable
        fun Staplar(rader: List<Pair<String, Int>>, farg: Color) {
            val max = (rader.maxOfOrNull { it.second } ?: 0).coerceAtLeast(1)
            Column(Modifier.padding(horizontal = 20.dp, vertical = 10.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                rader.forEach { (lbl, min) ->
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text(lbl, style = typo.bodyMedium, color = cs.onSurface, modifier = Modifier.width(88.dp))
                        Box(Modifier.weight(1f).height(12.dp).background(farg.copy(alpha = 0.14f), androidx.compose.foundation.shape.RoundedCornerShape(6.dp))) {
                            Box(Modifier.fillMaxWidth(min.toFloat() / max).height(12.dp).background(farg, androidx.compose.foundation.shape.RoundedCornerShape(6.dp)))
                        }
                        Text(if (min >= 60) "${min / 60} h ${min % 60} min" else "$min min", style = typo.labelMedium,
                            color = cs.onSurfaceVariant, modifier = Modifier.width(78.dp).padding(start = 8.dp))
                    }
                }
            }
        }
        val kat = datorn?.optJSONObject("kategorier")
        if (kat != null) {
            val namn = listOf("kod" to "Kod", "spel" to "Spel", "chatt" to "Chatt", "webb" to "Webb", "annat" to "Annat")
            val rader = namn.map { (k, l) -> l to (kat.optJSONObject(k)?.optInt("minuter") ?: 0) }.filter { it.second > 0 }
            Section("Uptime vid datorn", trailing = "senaste dygnet") {
                if (rader.isEmpty()) Text("Ingen datortid senaste dygnet.", style = typo.bodyMedium, color = cs.onSurfaceVariant,
                    modifier = Modifier.padding(20.dp))
                else Staplar(rader, cs.primary)
            }
        }
        val mob = datorn?.optJSONObject("mobil")
        val harSkarmtid = se.konsiliet.app.hc.Skarmtid.harBehorighet(ctx)
        Section("Skärmtid på mobilen", trailing = "senaste dygnet") {
            if (!harSkarmtid) {
                Column(Modifier.padding(20.dp)) {
                    Text("Ge Kropp64 åtkomst till användning, så läggs mobilens skärmtid per kategori bredvid pulsen och sömnen. " +
                        "Bara kategorin sparas, aldrig vilken app.", style = typo.bodyMedium, color = cs.onSurfaceVariant)
                    androidx.compose.material3.FilledTonalButton(onClick = { se.konsiliet.app.hc.Skarmtid.oppnaInstallning(ctx) },
                        modifier = Modifier.padding(top = 10.dp)) { Text("Slå på skärmtid") }
                }
            } else {
                val namn = listOf("spel" to "Spel", "sociala" to "Sociala", "video" to "Video", "chatt" to "Chatt", "webb" to "Webb", "annat" to "Annat")
                val rader = namn.map { (k, l) -> l to (mob?.optJSONObject(k)?.optInt("minuter") ?: 0) }.filter { it.second > 0 }
                if (rader.isEmpty()) Text("Ingen skärmtid uppladdad än. Den läses var 30:e minut.", style = typo.bodyMedium,
                    color = cs.onSurfaceVariant, modifier = Modifier.padding(20.dp))
                else Staplar(rader, t.avvikelse)
            }
        }

        // Morgonbrief
        Section("POST-skärmen", trailing = brief?.let { Fmt.day(it.ts) }) {
            val text = brief?.let { runCatching { JSONObject(it.payload).optString("text") }.getOrNull() }
            Text(text?.takeIf { it.isNotBlank() } ?: "Ingen POST-skärm ännu.", style = Type.body,
                color = if (text.isNullOrBlank()) t.ink3 else t.ink2, modifier = Modifier.padding(horizontal = 20.dp, vertical = 12.dp))
            Row(Modifier.padding(horizontal = 8.dp), verticalAlignment = Alignment.CenterVertically) {
                TextButton(onClick = {
                    briefMsg = "Skapar ..."
                    scope.launch {
                        briefMsg = runCatching { Api.postJson("/api/brief", JSONObject()); "Klar. Visas när den kommit över live-länken." }
                            .getOrElse { "Gick inte: ${it.message}" }
                        refresh++
                    }
                }) { Text("Kör POST nu") }
                briefMsg?.let { Text(it, style = Type.small, color = t.ink3) }
            }
        }

        // Länken
        Section("Länk", trailing = "klocka, mobil, server") {
            ReadoutRow("Senast från klockan", if (link.lastWatchAt > 0) Fmt.ago(link.lastWatchAt, now) else null,
                note = link.lastWatchSource?.let { sourceLabel(it) }, noteColor = if (isTestSource(link.lastWatchSource)) t.avvikelse else null)
            ReadoutRow("Senast uppladdat", if (link.lastUploadAt > 0) Fmt.ago(link.lastUploadAt, now) else null,
                note = link.lastUploadError, noteColor = t.avvikelse)
            ReadoutRow("I kö på mobilen", Fmt.int(queue.toDouble()), "punkter")
            ReadoutRow("Health Connect", if (link.lastHcSyncAt > 0) Fmt.ago(link.lastHcSyncAt, now) else null, note = link.hcStatus)
        }
        Spacer(Modifier.height(8.dp))
        Row(Modifier.padding(horizontal = 20.dp), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            Text("Server: ${config.serverUrl}", style = Type.small, color = t.ink3)
        }
    }
}
