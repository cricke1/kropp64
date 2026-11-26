package se.konsiliet.wear.ui

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.DirectionsRun
import androidx.compose.material.icons.automirrored.filled.DirectionsWalk
import androidx.compose.material.icons.filled.Air
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Favorite
import androidx.compose.material.icons.filled.FitnessCenter
import androidx.compose.material.icons.filled.PedalBike
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material.icons.filled.Stop
import androidx.compose.material.icons.filled.Sync
import androidx.compose.runtime.Composable
import androidx.compose.runtime.Immutable
import androidx.compose.runtime.State
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.derivedStateOf
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.produceState
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.concurrent.futures.await
import androidx.health.services.client.HealthServices
import androidx.health.services.client.MeasureCallback
import androidx.health.services.client.data.Availability
import androidx.health.services.client.data.DataPointContainer
import androidx.health.services.client.data.DataType
import androidx.health.services.client.data.DeltaDataType
import androidx.health.services.client.data.ExerciseType
import androidx.lifecycle.lifecycleScope
import androidx.wear.compose.foundation.lazy.TransformingLazyColumn
import androidx.wear.compose.foundation.lazy.TransformingLazyColumnItemScope
import androidx.wear.compose.foundation.lazy.rememberTransformingLazyColumnState
import androidx.wear.compose.material3.AppScaffold
import androidx.wear.compose.material3.Button
import androidx.wear.compose.material3.ButtonDefaults
import androidx.wear.compose.material3.CardDefaults
import androidx.wear.compose.material3.ColorScheme
import androidx.wear.compose.material3.Dialog
import androidx.wear.compose.material3.EdgeButton
import androidx.wear.compose.material3.EdgeButtonSize
import androidx.wear.compose.material3.Icon
import androidx.wear.compose.material3.ListHeader
import androidx.wear.compose.material3.MaterialTheme
import androidx.wear.compose.material3.ScreenScaffold
import androidx.wear.compose.material3.SurfaceTransformation
import androidx.wear.compose.material3.Text
import androidx.wear.compose.material3.TitleCard
import androidx.wear.compose.material3.dynamicColorScheme
import androidx.wear.compose.material3.lazy.TransformationSpec
import androidx.wear.compose.material3.lazy.rememberTransformationSpec
import androidx.wear.compose.material3.lazy.transformedHeight
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.distinctUntilChanged
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.launch
import org.json.JSONObject
import se.konsiliet.wear.KonsilietWearApp
import se.konsiliet.wear.data.Pending
import se.konsiliet.wear.data.PhoneStatus
import se.konsiliet.wear.data.QueueDb
import se.konsiliet.wear.data.WatchState
import se.konsiliet.wear.exercise.EXERCISE_CHOICES
import se.konsiliet.wear.exercise.ExerciseService
import se.konsiliet.wear.exercise.PassLogg
import se.konsiliet.wear.exercise.Zoner
import se.konsiliet.wear.exercise.planensTyp
import se.konsiliet.wear.health.Convert
import se.konsiliet.wear.health.Passive
import se.konsiliet.wear.health.Permissions
import se.konsiliet.wear.link.Flush
import se.konsiliet.wear.tile.TileLayout

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
            ExerciseService.start(this, planensTyp(PhoneStatus.snapshot.value.idag?.typ))
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

/**
 * En del av ett StateFlow som eget State. Pulsen ändras varje sekund medan skärmen är på, och om hela
 * Status lästes högst upp skulle varje puls komponera om hela listan (det var laggen vid scrollning).
 * Nu komponeras bara det kort om som faktiskt visar värdet.
 */
@Composable
private fun <T, R> StateFlow<T>.select(f: (T) -> R): State<R> =
    remember(this) { map(f).distinctUntilChanged() }.collectAsState(initial = f(value))

/** Klockan för "3 min sedan" och passminuter. Läses bara i de kort som behöver den. */
@Composable
private fun rememberNow(aktiv: Boolean): State<Long> = produceState(System.currentTimeMillis(), aktiv) {
    // Under ett pass räknas minuterna. Annars räcker var 20:e sekund ("nyss", "3 min sedan").
    while (true) { value = System.currentTimeMillis(); delay(if (aktiv) 1000 else 20000) }
}

/** Passets sammanfattning, tolkad en gång i stället för JSON-uppslag i varje komposition. */
@Immutable
private data class PassSummary(val rubrik: String, val puls: String?, val malzon: String?, val zoner: String, val rad: String)

private fun PassSummary(p: JSONObject): PassSummary {
    val z = p.optJSONArray("zon_minuter")
    val zt = if (z != null) (0 until z.length()).filter { z.optInt(it) > 0 }.joinToString(", ") { "z${it + 1} ${z.optInt(it)} min" } else ""
    return PassSummary(
        rubrik = "Pass klart: ${p.optInt("minuter")} min",
        puls = if (!p.isNull("puls_medel")) "Medel ${p.optInt("puls_medel")}, max ${p.optInt("puls_max")} BPM" else null,
        malzon = if (!p.isNull("i_malzon_procent")) "${p.optInt("i_malzon_procent")} % i målzon ${p.optInt("malzon")}" else null,
        zoner = zt,
        rad = p.optString("rad"),
    )
}

private fun passIkon(t: ExerciseType): ImageVector = when (t) {
    ExerciseType.WALKING -> Icons.AutoMirrored.Filled.DirectionsWalk
    ExerciseType.RUNNING -> Icons.AutoMirrored.Filled.DirectionsRun
    ExerciseType.BIKING -> Icons.Filled.PedalBike
    ExerciseType.STRENGTH_TRAINING -> Icons.Filled.FitnessCenter
    else -> Icons.AutoMirrored.Filled.DirectionsRun
}

@Composable
private fun Screen(permsOk: Boolean, onAskPerms: () -> Unit) {
    val ctx = LocalContext.current
    val cs = MaterialTheme.colorScheme
    val typo = MaterialTheme.typography
    // Bara det som styr listans struktur läses här. Pulsen och klockan läses i sina egna kort.
    val aktiv by WatchState.status.select { it.exerciseActive }
    val startedAt by WatchState.status.select { it.exerciseStartedAt }
    val lastError by WatchState.status.select { it.lastError }
    val registered by WatchState.status.select { it.registered }
    val phone by PhoneStatus.snapshot.collectAsState()
    val msg by ExerciseService.message.collectAsState()
    val senasteJson by PassLogg.senaste.collectAsState()
    val senaste = remember(senasteJson) { senasteJson?.let { PassSummary(it) } }
    val now = rememberNow(aktiv)
    val available by produceState(emptyList<String>(), aktiv) {
        value = runCatching { Passive.available(ctx) }.getOrDefault(emptyList())
    }
    val sensorText = remember(available) { "Sensorer: " + available.joinToString(", ").ifEmpty { "okänt" } }
    var choosing by remember { mutableStateOf(false) }
    val listState = rememberTransformingLazyColumnState()
    val spec = rememberTransformationSpec()
    val idag = phone.idag
    val planTyp = idag?.typ
    val emulator = remember { WatchState.isEmulator() }

    ScreenScaffold(
        scrollState = listState,
        edgeButton = {
            when {
                !permsOk -> EdgeButton(onClick = onAskPerms, buttonSize = EdgeButtonSize.Medium) { Text("Ge behörighet") }
                aktiv -> EdgeButton(onClick = { ExerciseService.stop(ctx) }, buttonSize = EdgeButtonSize.Medium,
                    colors = ButtonDefaults.filledTonalButtonColors()) {
                    Icon(Icons.Filled.Stop, contentDescription = null)
                    Text("Avsluta")
                }
                else -> EdgeButton(onClick = { ExerciseService.start(ctx, planensTyp(planTyp)) },
                    buttonSize = EdgeButtonSize.Medium) {
                    Icon(Icons.Filled.PlayArrow, contentDescription = null)
                    Text("Starta pass")
                }
            }
        },
    ) { contentPadding ->
        TransformingLazyColumn(state = listState, modifier = Modifier.fillMaxSize(), contentPadding = contentPadding) {
            // Puls överst, stort, som klockans egen pulsapp.
            item(key = "puls") { PulsBlock(aktiv, startedAt, now, Modifier.fillMaxWidth().morph(this, spec)) }
            if (aktiv) item(key = "zon") {
                ZonKort(Modifier.fillMaxWidth().transformedHeight(this, spec), SurfaceTransformation(spec))
            }
            senaste?.let { p ->
                item(key = "senaste") {
                    TitleCard(onClick = { PassLogg.kvittera(ctx) }, title = { Text(p.rubrik) },
                        modifier = Modifier.fillMaxWidth().transformedHeight(this, spec), transformation = SurfaceTransformation(spec),
                        subtitle = { p.puls?.let { Text(it, style = Tab) } }) {
                        p.malzon?.let { Text(it, color = cs.primary) }
                        if (p.zoner.isNotEmpty()) Text(p.zoner, style = Tab)
                        Text(p.rad)
                        Text("Tryck för att stänga", style = typo.labelSmall, color = cs.onSurfaceVariant)
                    }
                }
            }
            if (!aktiv && idag != null) item(key = "idag") {
                TitleCard(onClick = {}, title = { Text(idag.rubrik) },
                    modifier = Modifier.fillMaxWidth().transformedHeight(this, spec), transformation = SurfaceTransformation(spec),
                    subtitle = { Text("Pass ${idag.pass} av ${idag.mal} i veckan", style = Tab) },
                    colors = if (idag.beslut == "vila") CardDefaults.cardColors(containerColor = cs.errorContainer) else CardDefaults.cardColors()) {
                    Text(idag.plan)
                }
            }
            if (!aktiv) item(key = "headroom") {
                val cText = remember(phone) { TileLayout.consultLine(phone).first }
                TitleCard(onClick = {}, title = { Text("Headroom " + (phone.score?.toString() ?: "--"), style = Tab) },
                    modifier = Modifier.fillMaxWidth().transformedHeight(this, spec), transformation = SurfaceTransformation(spec),
                    subtitle = { Text("återhämtning av 100") }) {
                    Text(cText)
                }
            }
            if (emulator) item(key = "emu") {
                Text("Emulator: syntetisk testdata", style = typo.labelSmall, color = cs.error, textAlign = TextAlign.Center,
                    modifier = Modifier.fillMaxWidth().morph(this, spec))
            }
            if (!aktiv) {
                item(key = "valj") {
                    Button(onClick = { choosing = true }, enabled = permsOk, modifier = Modifier.fillMaxWidth().transformedHeight(this, spec),
                        transformation = SurfaceTransformation(spec), colors = ButtonDefaults.filledTonalButtonColors(),
                        icon = { Icon(passIkon(planensTyp(planTyp)), contentDescription = null) },
                        secondaryLabel = { Text(idag?.let { "Planen: ${it.typ} ${it.minuter} min" } ?: "Planen: stresstest") }) { Text("Välj pass") }
                }
                item(key = "andas") {
                    Button(onClick = { ctx.startActivity(android.content.Intent(ctx, AndasActivity::class.java)) },
                        modifier = Modifier.fillMaxWidth().transformedHeight(this, spec), transformation = SurfaceTransformation(spec),
                        colors = ButtonDefaults.filledTonalButtonColors(), icon = { Icon(Icons.Filled.Air, contentDescription = null) },
                        secondaryLabel = { Text("In 4 s, ut 6 s") }) { Text("Andas 60 s") }
                }
            }
            msg?.let { m -> item(key = "msg") { Text(m, style = typo.labelSmall, color = cs.error, textAlign = TextAlign.Center,
                modifier = Modifier.fillMaxWidth().morph(this, spec)) } }
            item(key = "synkrubrik") { ListHeader(Modifier.fillMaxWidth().transformedHeight(this, spec), transformation = SurfaceTransformation(spec)) { Text("Synk") } }
            item(key = "synk") {
                SynkKnapp(phone, now, Modifier.fillMaxWidth().transformedHeight(this, spec), SurfaceTransformation(spec))
            }
            lastError?.let { e -> item(key = "fel") { Text(e, style = typo.labelSmall, color = cs.error, textAlign = TextAlign.Center,
                modifier = Modifier.fillMaxWidth().morph(this, spec)) } }
            item(key = "info") {
                Column(horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(2.dp),
                    modifier = Modifier.fillMaxWidth().morph(this, spec).padding(vertical = 8.dp)) {
                    Text("Mäter passivt: " + (registered ?: "inget ännu"), style = typo.labelSmall, color = cs.onSurfaceVariant, textAlign = TextAlign.Center)
                    Text(sensorText, style = typo.labelSmall, color = cs.onSurfaceVariant, textAlign = TextAlign.Center)
                }
            }
        }
    }

    // Passväljaren som en egen helskärmsdialog (svep för att stänga), som klockans träningsapp.
    Dialog(visible = choosing, onDismissRequest = { choosing = false }) {
        PassValjare(planTyp = planTyp, planMinuter = idag?.minuter,
            onPick = { t -> choosing = false; ExerciseService.start(ctx, t) },
            onCancel = { choosing = false })
    }
}

@Composable
private fun PulsBlock(aktiv: Boolean, startedAt: Long, now: State<Long>, modifier: Modifier) {
    val cs = MaterialTheme.colorScheme
    val typo = MaterialTheme.typography
    val hr by WatchState.status.select { it.lastHr }
    val hrAt by WatchState.status.select { it.lastHrAt }
    val hrText = remember(hr) { hr?.let { "%.0f".format(it) } ?: "--" }
    Column(modifier, horizontalAlignment = Alignment.CenterHorizontally) {
        if (aktiv) {
            val min by remember(startedAt) { derivedStateOf { (now.value - startedAt) / 60000 } }
            Text("Pass $min min", style = typo.labelMedium, color = cs.onSurfaceVariant)
        }
        Row(verticalAlignment = Alignment.Bottom) {
            Icon(Icons.Filled.Favorite, contentDescription = null, tint = cs.error,
                modifier = Modifier.padding(end = 4.dp, bottom = 10.dp).size(18.dp))
            Text(hrText, style = typo.displayMedium.merge(Tab), color = cs.onSurface)
            Text(" BPM", style = typo.labelMedium, color = cs.onSurfaceVariant, modifier = Modifier.padding(bottom = 8.dp))
        }
        if (!aktiv) {
            val agoText by remember(hrAt) { derivedStateOf { ago(hrAt, now.value) } }
            Text(agoText, style = typo.labelSmall, color = cs.onSurfaceVariant)
        }
    }
}

@Composable
private fun ZonKort(modifier: Modifier, transformation: SurfaceTransformation) {
    val live by PassLogg.live.collectAsState()
    val hr by WatchState.status.select { it.lastHr }
    val mal = live.malzon
    val (lo, hi) = remember(mal) { Zoner.grans(mal.coerceIn(1, 5)) }
    val zon = hr?.let { Zoner.zon(it) }
    val iMal = (live.sekunderIZon[mal] / 60).toInt()
    val rad = when {
        zon == null -> "Väntar på puls"
        zon > mal -> "Över målzonen, sakta ner"
        zon < mal -> "Under målzonen, öka lite"
        else -> "I målzonen"
    }
    TitleCard(onClick = {}, title = { Text(if (zon != null && zon > 0) "Zon $zon: ${Zoner.NAMN[zon]}" else "Under zon 1") },
        modifier = modifier, transformation = transformation,
        subtitle = { Text("Mål zon $mal: $lo-$hi BPM", style = Tab) }) {
        Text("$rad · $iMal min i målzon")
    }
}

@Composable
private fun SynkKnapp(phone: se.konsiliet.wear.data.Snapshot, now: State<Long>, modifier: Modifier, transformation: SurfaceTransformation) {
    val ctx = LocalContext.current
    val pending by remember { QueueDb.get(ctx).pending().countFlow() }.collectAsState(initial = 0)
    val sentAt by WatchState.status.select { it.lastSentAt }
    val label by remember(phone, pending, sentAt) {
        derivedStateOf {
            if (pending > 0) "$pending i kö · ${ago(sentAt, now.value)}" else TileLayout.syncLine(phone, now.value).first
        }
    }
    Button(onClick = { Flush.request(ctx, urgent = true) },
        modifier = modifier, transformation = transformation,
        colors = ButtonDefaults.outlinedButtonColors(), icon = { Icon(Icons.Filled.Sync, contentDescription = null) },
        secondaryLabel = { Text(label) }) { Text("Skicka nu") }
}

@Composable
private fun PassValjare(planTyp: String?, planMinuter: Int?, onPick: (ExerciseType) -> Unit, onCancel: () -> Unit) {
    val state = rememberTransformingLazyColumnState()
    val spec = rememberTransformationSpec()
    val plan = remember(planTyp) { planensTyp(planTyp) }
    ScreenScaffold(scrollState = state) { pad ->
        TransformingLazyColumn(state = state, modifier = Modifier.fillMaxSize(), contentPadding = pad) {
            item(key = "rubrik") {
                ListHeader(Modifier.fillMaxWidth().transformedHeight(this, spec), transformation = SurfaceTransformation(spec)) { Text("Välj pass") }
            }
            EXERCISE_CHOICES.forEach { (type, label) ->
                item(key = type.id) {
                    val planerat = type == plan && planTyp != null
                    Button(onClick = { onPick(type) },
                        modifier = Modifier.fillMaxWidth().transformedHeight(this, spec), transformation = SurfaceTransformation(spec),
                        colors = if (planerat) ButtonDefaults.buttonColors() else ButtonDefaults.filledTonalButtonColors(),
                        icon = { Icon(passIkon(type), contentDescription = null) },
                        secondaryLabel = if (planerat) {
                            { Text(planMinuter?.let { "Dagens plan · $it min" } ?: "Dagens plan") }
                        } else null) { Text(label) }
                }
            }
            item(key = "avbryt") {
                Button(onClick = onCancel, modifier = Modifier.fillMaxWidth().transformedHeight(this, spec),
                    transformation = SurfaceTransformation(spec), colors = ButtonDefaults.outlinedButtonColors(),
                    icon = { Icon(Icons.Filled.Close, contentDescription = null) }) { Text("Avbryt") }
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
