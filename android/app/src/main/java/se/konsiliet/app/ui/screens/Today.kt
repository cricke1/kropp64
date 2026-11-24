package se.konsiliet.app.ui.screens

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
            Text("Sensorer", style = Type.title, color = t.ink, modifier = Modifier.weight(1f))
            StatusDot(if (link.wsConnected) t.ok else t.avvikelse)
            Text("  " + if (link.wsConnected) "Ansluten" else "Frånkopplad", style = Type.small, color = t.ink2)
        }

        // Puls
        Column(Modifier.padding(start = 20.dp, end = 20.dp, top = 18.dp)) {
            Text("Klockfrekvens", style = Type.label, color = t.ink2)
            Row(verticalAlignment = Alignment.Bottom) {
                Text(hrVal?.let { Fmt.int(it) } ?: "ej mätt", style = if (hrVal == null) Type.value else Type.display,
                    color = if (hrVal == null) t.ink3 else t.ink)
                if (hrVal != null) Text("  BPM", style = Type.small, color = t.ink2, modifier = Modifier.padding(bottom = 10.dp))
            }
            val stale = hrTs != null && now / 1000.0 - hrTs > 15 * 60
            Text(
                if (hrTs == null) "Ingen klockfrekvens mottagen ännu"
                else "${Fmt.ago((hrTs * 1000).toLong(), now)} · $hrSrc" + if (stale) " · inte aktuell" else "",
                style = Type.small, color = if (isTestSource(hrLatest?.source)) t.avvikelse else t.ink3,
            )
        }
        Spacer(Modifier.height(12.dp))
        Column(Modifier.padding(horizontal = 20.dp)) {
            // Finns bara en kort stund data (t.ex. första timmen) zoomas axeln in på den, annars hela dygnet.
            val chartFrom = hrSeries.firstOrNull()?.let { maxOf(from24, it.ts - 15 * 60) } ?: from24
            TraceChart(hrSeries, chartFrom, now / 1000.0, unit = "BPM")
            if (hrSeries.isNotEmpty()) {
                Text((if (chartFrom > from24 + 60) "Sedan ${Fmt.hm(chartFrom)}" else "Senaste dygnet") + ": min ${Fmt.int(hrSeries.minOf { it.value })} · max ${Fmt.int(hrSeries.maxOf { it.value })} · ${Fmt.int(hrSeries.size.toDouble())} punkter",
                    style = Type.small, color = t.ink3, modifier = Modifier.padding(top = 6.dp))
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

        // Övriga mätvärden
        Section("Övriga sensorer", trailing = "senaste värde") {
            ReadoutRow("Timingmarginal (HRV, RMSSD)", hrv?.let { Fmt.dec(it.value) }, "ms", note = hrv?.let { "${Fmt.ago((it.ts * 1000).toLong(), now)} · ${sourceLabel(it.source)}" })
            ReadoutRow("Idle-klock", rest?.let { Fmt.int(it.value) }, "BPM", note = rest?.let { "${Fmt.ago((it.ts * 1000).toLong(), now)} · ${sourceLabel(it.source)}" })
            ReadoutRow("Syremättnad", spo2?.let { Fmt.dec(it.value) }, "%", note = spo2?.let { "${Fmt.ago((it.ts * 1000).toLong(), now)} · ${sourceLabel(it.source)}" })
            ReadoutRow("Andningsfrekvens", resp?.let { Fmt.dec(it.value) }, "/min", note = resp?.let { "${Fmt.ago((it.ts * 1000).toLong(), now)} · ${sourceLabel(it.source)}" })
            ReadoutRow("Hudtemperatur, avvikelse", skin?.let { (if (it.value >= 0) "+" else "") + Fmt.dec(it.value, 2) }, "°C", note = skin?.let { "${Fmt.ago((it.ts * 1000).toLong(), now)} · ${sourceLabel(it.source)}" })
        }

        // Steg
        val steps = maxOf(stepsWatch, stepsHc, stepsEmu)
        val stepsSrc = when (steps) { 0.0 -> null; stepsWatch -> "klockan"; stepsHc -> "Health Connect"; else -> "testdata från emulator" }
        Section("Steg idag", trailing = stepsSrc) {
            Column(Modifier.padding(horizontal = 20.dp, vertical = 12.dp)) {
                Row(verticalAlignment = Alignment.Bottom) {
                    Text(Fmt.int(steps), style = Type.value, color = t.ink)
                    Text("  av mål ${Fmt.int(config.stepsGoal.toDouble())}", style = Type.small, color = t.ink2, modifier = Modifier.padding(bottom = 3.dp))
                }
                Spacer(Modifier.height(8.dp))
                GoalBar(steps, config.stepsGoal.toDouble())
            }
        }

        // Datorn
        val kat = datorn?.optJSONObject("kategorier")
        if (kat != null) {
            Section("Uptime vid datorn", trailing = "senaste dygnet") {
                val names = mapOf("kod" to "Kod", "spel" to "Spel", "chatt" to "Chatt", "webb" to "Webb", "annat" to "Annat")
                names.forEach { (k, label) ->
                    val o = kat.optJSONObject(k) ?: return@forEach
                    val min = o.optInt("minuter")
                    val med = if (o.isNull("puls_median")) null else o.optDouble("puls_median")
                    ReadoutRow(label, if (min > 0) Fmt.int(min.toDouble()) else null, "min",
                        note = med?.let { "medianklockfrekvens ${Fmt.int(it)} BPM" })
                }
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
