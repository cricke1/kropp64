package se.konsiliet.wear.ui

import androidx.wear.compose.material3.EdgeButton
import androidx.wear.compose.material3.EdgeButtonSize
import androidx.wear.compose.material3.TitleCard
import androidx.wear.compose.material3.CardDefaults
import androidx.wear.compose.material3.Icon
import androidx.wear.compose.material3.dynamicColorScheme
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material.icons.filled.Favorite
import androidx.compose.material.icons.filled.DirectionsRun
import androidx.compose.material.icons.filled.Air
import androidx.compose.material.icons.filled.Sync
import androidx.compose.foundation.layout.size

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
            MaterialTheme(colorScheme = dynamicColorScheme(this@MainActivity) ?: ColorScheme()) {
                AppScaffold { Screen(permsOk, onAskPerms = { askForeground.launch(Permissions.foreground()) }) }
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
    val cs = MaterialTheme.colorScheme
    val typo = MaterialTheme.typography
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
    val aktiv = status.exerciseActive
    LaunchedEffect(aktiv) {
        available = runCatching { Passive.available(ctx) }.getOrDefault(emptyList())
        // Under ett pass räknas minuterna varje sekund. Annars räcker var 20:e sekund ("nyss", "3 min sedan"),
        // så att hela listan inte ritas om i onödan (det var en del av laggen).
        while (true) { now = System.currentTimeMillis(); delay(if (aktiv) 1000 else 20000) }
    }
    val listState = rememberTransformingLazyColumnState()
    val spec = rememberTransformationSpec()
    val planTyp = phone.idag?.typ

    ScreenScaffold(
        scrollState = listState,
        edgeButton = {
            when {
                !permsOk -> EdgeButton(onClick = onAskPerms, buttonSize = EdgeButtonSize.Medium) { Text("Ge behörighet") }
                aktiv -> EdgeButton(onClick = { ExerciseService.stop(ctx) }, buttonSize = EdgeButtonSize.Medium,
                    colors = ButtonDefaults.filledTonalButtonColors()) { Text("Avsluta") }
                else -> EdgeButton(onClick = { ExerciseService.start(ctx, se.konsiliet.wear.exercise.planensTyp(planTyp)) },
                    buttonSize = EdgeButtonSize.Medium) {
                    Icon(Icons.Filled.PlayArrow, contentDescription = null)
                    Text("Starta pass")
                }
            }
        },
    ) { contentPadding ->
        TransformingLazyColumn(state = listState, modifier = Modifier.fillMaxSize(), contentPadding = contentPadding) {
            // Puls överst, stort, som klockans egen pulsapp.
            item {
                Column(Modifier.fillMaxWidth().morph(this, spec), horizontalAlignment = Alignment.CenterHorizontally) {
                    if (aktiv) {
                        val min = (now - status.exerciseStartedAt) / 60000
                        Text("Pass $min min", style = typo.labelMedium, color = cs.onSurfaceVariant)
                    }
                    Row(verticalAlignment = Alignment.Bottom) {
                        Icon(Icons.Filled.Favorite, contentDescription = null, tint = cs.error,
                            modifier = Modifier.padding(end = 4.dp, bottom = 10.dp).size(18.dp))
                        Text(status.lastHr?.let { "%.0f".format(it) } ?: "--", style = typo.displayMedium.merge(Tab), color = cs.onSurface)
                        Text(" BPM", style = typo.labelMedium, color = cs.onSurfaceVariant, modifier = Modifier.padding(bottom = 8.dp))
                    }
                    if (!aktiv) Text(ago(status.lastHrAt, now), style = typo.labelSmall, color = cs.onSurfaceVariant)
                }
            }
            if (aktiv) item {
                val mal = live.malzon
                val (lo, hi) = se.konsiliet.wear.exercise.Zoner.grans(mal.coerceIn(1, 5))
                val zon = status.lastHr?.let { se.konsiliet.wear.exercise.Zoner.zon(it) }
                val iMal = (live.sekunderIZon[mal] / 60).toInt()
                val rad = when {
                    zon == null -> "Väntar på puls"
                    zon > mal -> "Över målzonen, sakta ner"
                    zon < mal -> "Under målzonen, öka lite"
                    else -> "I målzonen"
                }
                TitleCard(onClick = {}, title = { Text(if (zon != null && zon > 0) "Zon $zon: ${se.konsiliet.wear.exercise.Zoner.NAMN[zon]}" else "Under zon 1") },
                    modifier = Modifier.fillMaxWidth().transformedHeight(this, spec), transformation = SurfaceTransformation(spec),
                    subtitle = { Text("Mål zon $mal: $lo-$hi BPM", style = Tab) }) {
                    Text("$rad · $iMal min i målzon")
                }
            }
            senaste?.let { p ->
                item {
                    val z = p.optJSONArray("zon_minuter")
                    val zt = if (z != null) (0 until z.length()).filter { z.optInt(it) > 0 }.joinToString(", ") { "z${it + 1} ${z.optInt(it)} min" } else ""
                    TitleCard(onClick = { se.konsiliet.wear.exercise.PassLogg.kvittera(ctx) },
                        title = { Text("Pass klart: ${p.optInt("minuter")} min") },
                        modifier = Modifier.fillMaxWidth().transformedHeight(this, spec), transformation = SurfaceTransformation(spec),
                        subtitle = { if (!p.isNull("puls_medel")) Text("Medel ${p.optInt("puls_medel")}, max ${p.optInt("puls_max")} BPM", style = Tab) }) {
                        if (!p.isNull("i_malzon_procent")) Text("${p.optInt("i_malzon_procent")} % i målzon ${p.optInt("malzon")}", color = cs.primary)
                        if (zt.isNotEmpty()) Text(zt, style = Tab)
                        Text(p.optString("rad"))
                        Text("Tryck för att stänga", style = typo.labelSmall, color = cs.onSurfaceVariant)
                    }
                }
            }
            if (!aktiv) phone.idag?.let { i ->
                item {
                    TitleCard(onClick = {}, title = { Text(i.rubrik) },
                        modifier = Modifier.fillMaxWidth().transformedHeight(this, spec), transformation = SurfaceTransformation(spec),
                        subtitle = { Text("Pass ${i.pass} av ${i.mal} i veckan", style = Tab) },
                        colors = if (i.beslut == "vila") CardDefaults.cardColors(containerColor = cs.errorContainer) else CardDefaults.cardColors()) {
                        Text(i.plan)
                    }
                }
            }
            if (!aktiv) item {
                val (cText, _) = se.konsiliet.wear.tile.TileLayout.consultLine(phone)
                TitleCard(onClick = {}, title = { Text("Headroom " + (phone.score?.toString() ?: "--"), style = Tab) },
                    modifier = Modifier.fillMaxWidth().transformedHeight(this, spec), transformation = SurfaceTransformation(spec),
                    subtitle = { Text("återhämtning av 100") }) {
                    Text(cText)
                }
            }
            if (WatchState.isEmulator()) item {
                Text("Emulator: syntetisk testdata", style = typo.labelSmall, color = cs.error, textAlign = TextAlign.Center,
                    modifier = Modifier.fillMaxWidth().morph(this, spec))
            }
            if (!aktiv && !choosing) {
                item {
                    Button(onClick = { choosing = true }, enabled = permsOk, modifier = Modifier.fillMaxWidth().transformedHeight(this, spec),
                        transformation = SurfaceTransformation(spec), colors = ButtonDefaults.filledTonalButtonColors(),
                        icon = { Icon(Icons.Filled.DirectionsRun, contentDescription = null) },
                        secondaryLabel = { Text(phone.idag?.let { "Planen: ${it.typ} ${it.minuter} min" } ?: "Planen: stresstest") }) { Text("Välj pass") }
                }
                item {
                    Button(onClick = { ctx.startActivity(android.content.Intent(ctx, AndasActivity::class.java)) },
                        modifier = Modifier.fillMaxWidth().transformedHeight(this, spec), transformation = SurfaceTransformation(spec),
                        colors = ButtonDefaults.filledTonalButtonColors(), icon = { Icon(Icons.Filled.Air, contentDescription = null) },
                        secondaryLabel = { Text("In 4 s, ut 6 s") }) { Text("Andas 60 s") }
                }
            }
            if (choosing) {
                item { ListHeader(Modifier.fillMaxWidth().transformedHeight(this, spec), transformation = SurfaceTransformation(spec)) { Text("Välj pass") } }
                EXERCISE_CHOICES.forEach { (type, label) ->
                    item {
                        Button(onClick = { choosing = false; ExerciseService.start(ctx, type) },
                            modifier = Modifier.fillMaxWidth().transformedHeight(this, spec), transformation = SurfaceTransformation(spec),
                            colors = ButtonDefaults.filledTonalButtonColors()) { Text(label) }
                    }
                }
                item { Button(onClick = { choosing = false }, modifier = Modifier.fillMaxWidth().transformedHeight(this, spec),
                    transformation = SurfaceTransformation(spec), colors = ButtonDefaults.outlinedButtonColors()) { Text("Avbryt") } }
            }
            msg?.let { m -> item { Text(m, style = typo.labelSmall, color = cs.error, textAlign = TextAlign.Center,
                modifier = Modifier.fillMaxWidth().morph(this, spec)) } }
            item { ListHeader(Modifier.fillMaxWidth().transformedHeight(this, spec), transformation = SurfaceTransformation(spec)) { Text("Synk") } }
            item {
                val (sText, _) = se.konsiliet.wear.tile.TileLayout.syncLine(phone, now)
                Button(onClick = { scope.launch { Flush.request(ctx, urgent = true) } },
                    modifier = Modifier.fillMaxWidth().transformedHeight(this, spec), transformation = SurfaceTransformation(spec),
                    colors = ButtonDefaults.outlinedButtonColors(), icon = { Icon(Icons.Filled.Sync, contentDescription = null) },
                    secondaryLabel = { Text(if (pending > 0) "$pending i kö · ${ago(status.lastSentAt, now)}" else sText) }) { Text("Skicka nu") }
            }
            status.lastError?.let { e -> item { Text(e, style = typo.labelSmall, color = cs.error, textAlign = TextAlign.Center,
                modifier = Modifier.fillMaxWidth().morph(this, spec)) } }
            item {
                Column(horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(2.dp),
                    modifier = Modifier.fillMaxWidth().morph(this, spec).padding(vertical = 8.dp)) {
                    Text("Mäter passivt: " + (status.registered ?: "inget ännu"), style = typo.labelSmall, color = cs.onSurfaceVariant, textAlign = TextAlign.Center)
                    Text("Sensorer: " + available.joinToString(", ").ifEmpty { "okänt" }, style = typo.labelSmall, color = cs.onSurfaceVariant, textAlign = TextAlign.Center)
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
