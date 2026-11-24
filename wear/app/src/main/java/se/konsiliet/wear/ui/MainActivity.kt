package se.konsiliet.wear.ui

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.concurrent.futures.await
import androidx.health.services.client.HealthServices
import androidx.health.services.client.MeasureCallback
import androidx.health.services.client.data.Availability
import androidx.health.services.client.data.DataPointContainer
import androidx.health.services.client.data.DataType
import androidx.health.services.client.data.DeltaDataType
import androidx.lifecycle.lifecycleScope
import androidx.compose.ui.graphics.graphicsLayer
import androidx.wear.compose.foundation.lazy.TransformingLazyColumn
import androidx.wear.compose.foundation.lazy.TransformingLazyColumnItemScope
import androidx.wear.compose.foundation.lazy.rememberTransformingLazyColumnState
import androidx.wear.compose.material3.SurfaceTransformation
import androidx.wear.compose.material3.lazy.TransformationSpec
import androidx.wear.compose.material3.lazy.rememberTransformationSpec
import androidx.wear.compose.material3.lazy.transformedHeight
import androidx.wear.compose.material3.AppScaffold
import androidx.wear.compose.material3.Button
import androidx.wear.compose.material3.ButtonDefaults
import androidx.wear.compose.material3.ColorScheme
import androidx.wear.compose.material3.MaterialTheme
import androidx.wear.compose.material3.ListHeader
import androidx.wear.compose.material3.ScreenScaffold
import androidx.wear.compose.material3.TimeText
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.wear.compose.material3.Text
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import se.konsiliet.wear.KonsilietWearApp
import se.konsiliet.wear.data.Pending
import se.konsiliet.wear.data.QueueDb
import se.konsiliet.wear.data.WatchState
import se.konsiliet.wear.exercise.EXERCISE_CHOICES
import se.konsiliet.wear.exercise.ExerciseService
import se.konsiliet.wear.health.Convert
import se.konsiliet.wear.health.Passive
import se.konsiliet.wear.health.Permissions
import se.konsiliet.wear.link.Flush

private val Ink = Color(0xFFE8ECEA)
private val Dim = Color(0xFF8E9894)
private val Accent = Color(0xFF8FC1CC)
private val Warn = Color(0xFFE0A458)
private val Tab = TextStyle(fontFeatureSettings = "tnum")

class MainActivity : ComponentActivity() {

    private var permsOk by mutableStateOf(false)

    private val askForeground = registerForActivityResult(ActivityResultContracts.RequestMultiplePermissions()) {
        refreshPerms()
        // Bakgrundsbehörigheten måste begäras separat, efter att förgrundsbehörigheten getts.
        if (Permissions.has(this, Permissions.heartRate) && !Permissions.has(this, Permissions.background)) {
            askBackground.launch(Permissions.background)
        } else {
            (application as KonsilietWearApp).reregister()
        }
    }
    private val askBackground = registerForActivityResult(ActivityResultContracts.RequestPermission()) {
        refreshPerms(); (application as KonsilietWearApp).reregister()
    }

    /** Medan skärmen är på mäts pulsen direkt med MeasureClient, så att siffran är färsk. */
    private val measure = object : MeasureCallback {
        override fun onAvailabilityChanged(dataType: DeltaDataType<*, *>, availability: Availability) {}
        override fun onDataReceived(data: DataPointContainer) {
            val boot = Convert.bootInstant()
            val rows = data.getData(DataType.HEART_RATE_BPM).filter { it.value > 0 }
                .map { Pending(metric = "hr", ts = Convert.seconds(it.getTimeInstant(boot)), value = it.value) }
            if (rows.isEmpty()) return
            val last = rows.maxBy { it.ts }
            WatchState.noteHr(last.value, (last.ts * 1000).toLong())
            lifecycleScope.launch(Dispatchers.IO) { QueueDb.get(applicationContext).pending().insert(rows) }
            Flush.request(applicationContext)
        }
    }
    private var measuring = false

    private fun refreshPerms() {
        permsOk = Permissions.foreground().all { Permissions.has(this, it) }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        refreshPerms()
        if (!permsOk) askForeground.launch(Permissions.foreground())
        else (application as KonsilietWearApp).reregister()
        startaFranIntent(intent)
        setContent {
            MaterialTheme(colorScheme = ColorScheme(primary = Accent, onPrimary = Color(0xFF0E1A1E))) {
                AppScaffold(timeText = {}) { Screen(permsOk, onAskPerms = { askForeground.launch(Permissions.foreground()) }) }
            }
        }
    }

    override fun onNewIntent(intent: android.content.Intent) {
        super.onNewIntent(intent)
        startaFranIntent(intent)
    }

    /** Från passpåminnelsen eller rutan: starta dagens planerade pass direkt. */
    private fun startaFranIntent(i: android.content.Intent?) {
        if (i?.getBooleanExtra("starta_pass", false) == true && permsOk && !WatchState.status.value.exerciseActive) {
            i.removeExtra("starta_pass")
            ExerciseService.start(this, se.konsiliet.wear.exercise.planensTyp(se.konsiliet.wear.data.PhoneStatus.snapshot.value.idag?.typ))
        }
    }

    override fun onStart() {
        super.onStart()
        refreshPerms()
        if (Permissions.has(this, Permissions.heartRate)) {
            HealthServices.getClient(this).measureClient.registerMeasureCallback(DataType.HEART_RATE_BPM, measure)
            measuring = true
        }
        Flush.request(this, urgent = true)
    }

    override fun onStop() {
        super.onStop()
        if (measuring) {
            lifecycleScope.launch {
                runCatching {
                    HealthServices.getClient(this@MainActivity).measureClient
                        .unregisterMeasureCallbackAsync(DataType.HEART_RATE_BPM, measure).await()
                }
            }
            measuring = false
        }
    }
}

private val hm = SimpleDateFormat("HH:mm", Locale("sv", "SE"))

private fun ago(ms: Long, now: Long): String {
    if (ms == 0L) return "aldrig"
    val s = (now - ms) / 1000
    return when {
        s < 60 -> "nyss"
        s < 3600 -> "${s / 60} min sedan"
        else -> hm.format(Date(ms))
    }
}

@Composable
private fun Screen(permsOk: Boolean, onAskPerms: () -> Unit) {
    val ctx = androidx.compose.ui.platform.LocalContext.current
    val status by WatchState.status.collectAsState()
    val phone by se.konsiliet.wear.data.PhoneStatus.snapshot.collectAsState()
    val pending by remember { QueueDb.get(ctx).pending().countFlow() }.collectAsState(initial = 0)
    val msg by ExerciseService.message.collectAsState()
    val live by se.konsiliet.wear.exercise.PassLogg.live.collectAsState()
    val senaste by se.konsiliet.wear.exercise.PassLogg.senaste.collectAsState()
    var now by remember { mutableLongStateOf(System.currentTimeMillis()) }
    var available by remember { mutableStateOf<List<String>>(emptyList()) }
    var choosing by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()
    LaunchedEffect(Unit) {
        available = runCatching { Passive.available(ctx) }.getOrDefault(emptyList())
        while (true) { delay(1000); now = System.currentTimeMillis() }
    }
    val listState = rememberTransformingLazyColumnState()
    val spec = rememberTransformationSpec()

    // Rund skärm: ScreenScaffold ger utfyllnad så att listan börjar under klockan (TimeText) och slutar
    // ovanför nederkanten, och tonar bort klockan när man skrollar. TransformingLazyColumn krymper och
    // tonar rader som närmar sig den runda kanten (SurfaceTransformation för knappar, samma
    // container-transformation för textblock), så att inget skärs av cirkeln.
    val side = (LocalConfiguration.current.screenWidthDp * 0.08f).dp
    // Klockan överst visas bara när listan står högst upp. Så fort man skrollar tonas den bort,
    // så att inget innehåll någonsin ligger under den.
    ScreenScaffold(
        scrollState = listState,
        timeText = {
            AnimatedVisibility(visible = !listState.canScrollBackward, enter = fadeIn(), exit = fadeOut()) { TimeText() }
        },
    ) { contentPadding ->
        TransformingLazyColumn(
            state = listState,
            modifier = Modifier.fillMaxSize(),
            contentPadding = PaddingValues(
                start = side, end = side,
                top = contentPadding.calculateTopPadding(), bottom = contentPadding.calculateBottomPadding(),
            ),
        ) {
            senaste?.let { p ->
                item {
                    val z = p.optJSONArray("zon_minuter")
                    val zt = if (z != null) (0 until z.length()).filter { z.optInt(it) > 0 }.joinToString(", ") { "z${it + 1} ${z.optInt(it)} min" } else ""
                    Column(Modifier.fillMaxWidth().morph(this, spec), horizontalAlignment = Alignment.CenterHorizontally) {
                        Text("Pass klart: ${p.optInt("minuter")} min", color = Ink, fontSize = 15.sp, fontWeight = FontWeight.Medium)
                        if (!p.isNull("puls_medel")) Text("Medel ${p.optInt("puls_medel")}, max ${p.optInt("puls_max")} BPM", color = Ink, fontSize = 12.sp, style = Tab)
                        if (zt.isNotEmpty()) Text(zt, color = Dim, fontSize = 11.sp, textAlign = TextAlign.Center, style = Tab)
                        if (!p.isNull("i_malzon_procent")) Text("${p.optInt("i_malzon_procent")} % i målzon ${p.optInt("malzon")}", color = Accent, fontSize = 12.sp)
                        Text(p.optString("rad"), color = Dim, fontSize = 11.sp, textAlign = TextAlign.Center)
                    }
                }
                item {
                    Button(onClick = { se.konsiliet.wear.exercise.PassLogg.kvittera(ctx) }, modifier = Modifier.fillMaxWidth().transformedHeight(this, spec),
                        transformation = SurfaceTransformation(spec), colors = ButtonDefaults.filledTonalButtonColors()) { Text("Ok") }
                }
            }
            if (status.exerciseActive) {
                item {
                    // Live under passet: puls, zon och målzonen med gränser i BPM.
                    val mal = live.malzon
                    val (lo, hi) = se.konsiliet.wear.exercise.Zoner.grans(mal.coerceIn(1, 5))
                    val bpm = status.lastHr
                    val zon = bpm?.let { se.konsiliet.wear.exercise.Zoner.zon(it) }
                    val iMal = (live.sekunderIZon[mal] / 60).toInt()
                    val min = (now - status.exerciseStartedAt) / 60000
                    val rad = when {
                        bpm == null || zon == null -> "Väntar på puls"
                        zon > mal -> "Över målzonen, sakta ner"
                        zon < mal -> "Under målzonen, öka lite"
                        else -> "I målzonen"
                    }
                    Column(Modifier.fillMaxWidth().morph(this, spec), horizontalAlignment = Alignment.CenterHorizontally) {
                        Text("Pass $min min (stresstest)", color = Dim, fontSize = 12.sp, style = Tab)
                        Row(verticalAlignment = Alignment.Bottom) {
                            Text(bpm?.let { "%.0f".format(it) } ?: "--", style = Tab, fontSize = 40.sp, fontWeight = FontWeight.Medium, color = Ink)
                            Text(" BPM", color = Dim, fontSize = 12.sp, modifier = Modifier.padding(bottom = 8.dp))
                        }
                        Text(if (zon != null && zon > 0) "Zon $zon: ${se.konsiliet.wear.exercise.Zoner.NAMN[zon]}" else "Under zon 1",
                            color = if (zon == mal) Accent else Warn, fontSize = 14.sp)
                        Text("Mål zon $mal: $lo-$hi BPM", color = Ink, fontSize = 12.sp, style = Tab)
                        Text("$rad · $iMal min i målzon", color = Dim, fontSize = 11.sp, textAlign = TextAlign.Center)
                    }
                }
            }
            if (!status.exerciseActive) item {
                ListHeader(Modifier.fillMaxWidth().transformedHeight(this, spec), transformation = SurfaceTransformation(spec)) {
                    Text("Klockfrekvens (puls)", color = Dim)
                }
            }
            if (!status.exerciseActive) item {
                Column(Modifier.fillMaxWidth().morph(this, spec), horizontalAlignment = Alignment.CenterHorizontally) {
                    Row(verticalAlignment = Alignment.Bottom) {
                        Text(status.lastHr?.let { "%.0f".format(it) } ?: "--",
                            style = Tab, fontSize = 44.sp, fontWeight = FontWeight.Medium, color = Ink)
                        Text(" BPM", color = Dim, fontSize = 12.sp, modifier = Modifier.padding(bottom = 8.dp))
                    }
                    Text(ago(status.lastHrAt, now), color = Dim, fontSize = 12.sp, style = Tab)
                }
            }
            item {
                // Samma rader som tilen, så att den som trycker på tilen känner igen sig.
                val (cText, cColor) = se.konsiliet.wear.tile.TileLayout.consultLine(phone)
                val (sText, sColor) = se.konsiliet.wear.tile.TileLayout.syncLine(phone, now)
                Column(Modifier.fillMaxWidth().morph(this, spec).padding(top = 6.dp), horizontalAlignment = Alignment.CenterHorizontally) {
                    phone.idag?.let { i ->
                        Text(i.rubrik, color = if (i.beslut == "vila") Warn else Accent, fontSize = 15.sp, fontWeight = FontWeight.Medium,
                            textAlign = TextAlign.Center)
                        Text(i.plan, color = Ink, fontSize = 12.sp, textAlign = TextAlign.Center)
                        Text("Pass ${i.pass} av ${i.mal} i veckan", color = Dim, fontSize = 11.sp, style = Tab)
                    }
                    Text("Headroom " + (phone.score?.toString() ?: "--") + " av 100", color = Ink, fontSize = 14.sp, style = Tab)
                    Text("återhämtning", color = Dim, fontSize = 11.sp)
                    Text(cText, color = Color(cColor), fontSize = 12.sp, textAlign = TextAlign.Center)
                    Text(sText, color = Color(sColor), fontSize = 11.sp, style = Tab)
                }
            }
            if (WatchState.isEmulator()) {
                item { Text("Emulator: syntetisk testdata", color = Warn, fontSize = 11.sp, textAlign = TextAlign.Center,
                    modifier = Modifier.fillMaxWidth().morph(this, spec)) }
            }
            item {
                Column(horizontalAlignment = Alignment.CenterHorizontally, modifier = Modifier.fillMaxWidth().morph(this, spec).padding(top = 6.dp)) {
                    Text("Senast skickat: ${ago(status.lastSentAt, now)}", color = Ink, fontSize = 13.sp, style = Tab)
                    Text("I kö på klockan: $pending", color = Dim, fontSize = 12.sp, style = Tab)
                    status.lastError?.let {
                        Text(it, color = Warn, fontSize = 11.sp, textAlign = TextAlign.Center,
                            )
                    }
                }
            }
            if (!permsOk) {
                item {
                    Button(onClick = onAskPerms, modifier = Modifier.fillMaxWidth().transformedHeight(this, spec), transformation = SurfaceTransformation(spec)) { Text("Ge behörighet") }
                }
            }
            if (status.exerciseActive) {
                item {
                    Button(onClick = { ExerciseService.stop(ctx) }, modifier = Modifier.fillMaxWidth().transformedHeight(this, spec), transformation = SurfaceTransformation(spec),
                        colors = ButtonDefaults.filledTonalButtonColors()) { Text("Avsluta passet") }
                }
            } else if (choosing) {
                EXERCISE_CHOICES.forEach { (type, label) ->
                    item {
                        Button(onClick = { choosing = false; ExerciseService.start(ctx, type) },
                            modifier = Modifier.fillMaxWidth().transformedHeight(this, spec), transformation = SurfaceTransformation(spec),
                            colors = ButtonDefaults.filledTonalButtonColors()) { Text(label) }
                    }
                }
                item { Button(onClick = { choosing = false }, modifier = Modifier.fillMaxWidth().transformedHeight(this, spec), transformation = SurfaceTransformation(spec)) { Text("Avbryt") } }
            } else {
                val planTyp = phone.idag?.typ
                item {
                    // Ett tryck: dagens planerade pass. Annan sorts pass via "Välj pass".
                    Button(onClick = { ExerciseService.start(ctx, se.konsiliet.wear.exercise.planensTyp(planTyp)) }, enabled = permsOk,
                        modifier = Modifier.fillMaxWidth().transformedHeight(this, spec), transformation = SurfaceTransformation(spec),
                        secondaryLabel = { Text(phone.idag?.let { "${it.typ} ${it.minuter} min" } ?: "Stresstest") }) {
                        Text("Starta pass")
                    }
                }
                item {
                    Button(onClick = { choosing = true }, enabled = permsOk, modifier = Modifier.fillMaxWidth().transformedHeight(this, spec),
                        transformation = SurfaceTransformation(spec), colors = ButtonDefaults.filledTonalButtonColors()) { Text("Välj pass") }
                }
                item {
                    Button(onClick = { ctx.startActivity(android.content.Intent(ctx, AndasActivity::class.java)) },
                        modifier = Modifier.fillMaxWidth().transformedHeight(this, spec), transformation = SurfaceTransformation(spec),
                        colors = ButtonDefaults.filledTonalButtonColors(), secondaryLabel = { Text("In 4 s, ut 6 s") }) { Text("Andas 60 s") }
                }
            }
            msg?.let { m -> item { Text(m, color = Warn, fontSize = 11.sp, textAlign = TextAlign.Center,
                modifier = Modifier.fillMaxWidth().morph(this, spec)) } }
            item {
                Button(onClick = { scope.launch { Flush.request(ctx, urgent = true) } }, modifier = Modifier.fillMaxWidth().transformedHeight(this, spec), transformation = SurfaceTransformation(spec),
                    colors = ButtonDefaults.outlinedButtonColors()) { Text("Skicka nu") }
            }
            item {
                Column(horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(2.dp),
                    modifier = Modifier.fillMaxWidth().morph(this, spec).padding(vertical = 8.dp)) {
                    Text("Registrerat passivt", color = Dim, fontSize = 11.sp)
                    Text(status.registered ?: "inget ännu", color = Ink, fontSize = 11.sp, textAlign = TextAlign.Center)
                    Text("Klockan erbjuder", color = Dim, fontSize = 11.sp)
                    Text(available.joinToString(", ").ifEmpty { "okänt" }, color = Ink, fontSize = 11.sp, textAlign = TextAlign.Center)
                }
            }
        }
    }
}


/** Textblock i listan krymper och tonar mot den runda kanten på samma sätt som knapparna. */
private fun Modifier.morph(scope: TransformingLazyColumnItemScope, spec: TransformationSpec): Modifier =
    // Text har ingen yta som kan krympa, så den får extra sidomarginal för att rymmas i cirkelns korda.
    transformedHeight(scope, spec).padding(horizontal = 12.dp).graphicsLayer {
        val progress = with(scope) { scrollProgress }
        with(spec) {
            applyContainerTransformation(progress)
            applyContentTransformation(progress)
        }
    }
