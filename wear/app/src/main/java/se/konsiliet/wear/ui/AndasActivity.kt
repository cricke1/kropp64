package se.konsiliet.wear.ui

import android.os.Bundle
import android.view.WindowManager
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.Favorite
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.State
import androidx.compose.runtime.derivedStateOf
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.runtime.withFrameMillis
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
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
import androidx.lifecycle.lifecycleScope
import androidx.wear.compose.foundation.lazy.TransformingLazyColumn
import androidx.wear.compose.foundation.lazy.rememberTransformingLazyColumnState
import androidx.wear.compose.material3.AppScaffold
import androidx.wear.compose.material3.CircularProgressIndicator
import androidx.wear.compose.material3.ColorScheme
import androidx.wear.compose.material3.EdgeButton
import androidx.wear.compose.material3.EdgeButtonSize
import androidx.wear.compose.material3.Icon
import androidx.wear.compose.material3.MaterialTheme
import androidx.wear.compose.material3.ProgressIndicatorDefaults
import androidx.wear.compose.material3.ScreenScaffold
import androidx.wear.compose.material3.Text
import androidx.wear.compose.material3.dynamicColorScheme
import kotlin.math.PI
import kotlin.math.cos
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import se.konsiliet.wear.alerts.Haptics
import se.konsiliet.wear.data.Pending
import se.konsiliet.wear.data.QueueDb
import se.konsiliet.wear.link.Flush

private const val TOTAL_MS = 60_000L
private const val IN_MS = 4_000L
private const val CYKEL_MS = 10_000L
private val Tab = TextStyle(fontFeatureSettings = "tnum")

/**
 * 60 sekunder lugn andning: in 4 s, ut 6 s (sex andetag i minuten). Pulsen mäts under tiden och visas
 * före och efter, så att man ser om det hjälpte. Startas från stressknuffen ("Andas 60 s") eller från
 * klockans startsida. Andningen loggas som mätvärdet "andning" (sekunder) så att servern kan jämföra pulsen.
 *
 * Cirkeln växer under inandningen och krymper under utandningen (mjuk cosinuskurva), ringen längs kanten
 * visar minuten. Animationen läses bara i ritfasen, så texten komponeras om högst en gång per sekund.
 */
class AndasActivity : ComponentActivity() {
    private var puls by mutableStateOf<Double?>(null)
    private var forstaPuls: Double? = null

    private val cb = object : MeasureCallback {
        override fun onAvailabilityChanged(dataType: DeltaDataType<*, *>, availability: Availability) {}
        override fun onDataReceived(data: DataPointContainer) {
            data.getData(DataType.HEART_RATE_BPM).lastOrNull { it.value > 0 }?.let {
                puls = it.value
                if (forstaPuls == null) forstaPuls = it.value
            }
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        val start = System.currentTimeMillis()
        setContent {
            MaterialTheme(colorScheme = dynamicColorScheme(this@AndasActivity) ?: ColorScheme()) {
                AppScaffold {
                    var klar by remember { mutableStateOf(false) }
                    var slutPuls by remember { mutableStateOf<Double?>(null) }
                    val gatt = remember { mutableLongStateOf(0L) }
                    LaunchedEffect(Unit) {
                        while (gatt.longValue < TOTAL_MS) {
                            withFrameMillis { gatt.longValue = (System.currentTimeMillis() - start).coerceAtMost(TOTAL_MS) }
                        }
                        slutPuls = puls; klar = true
                        Haptics.andning(applicationContext, Haptics.Andning.KLAR)
                        lifecycleScope.launch(Dispatchers.IO) {
                            QueueDb.get(applicationContext).pending().insert(listOf(Pending(metric = "andning", ts = start / 1000.0, value = 60.0)))
                            Flush.request(applicationContext)
                        }
                    }
                    if (!klar) Andas(gatt, puls = { puls }) else Klart(forstaPuls, slutPuls, onOk = { finish() })
                }
            }
        }
    }

    override fun onStart() {
        super.onStart()
        runCatching { HealthServices.getClient(this).measureClient.registerMeasureCallback(DataType.HEART_RATE_BPM, cb) }
    }

    override fun onStop() {
        super.onStop()
        lifecycleScope.launch { runCatching { HealthServices.getClient(this@AndasActivity).measureClient.unregisterMeasureCallbackAsync(DataType.HEART_RATE_BPM, cb).await() } }
    }
}

/** 0..1: hur fylld cirkeln är vid tiden t (ms in i cykeln). Mjuk start och landning i båda faserna. */
private fun fyllnad(t: Long): Float =
    if (t < IN_MS) ((1 - cos(PI * t / IN_MS)) / 2).toFloat()
    else ((1 + cos(PI * (t - IN_MS) / (CYKEL_MS - IN_MS))) / 2).toFloat()

@Composable
private fun Andas(gatt: State<Long>, puls: () -> Double?) {
    val ctx = LocalContext.current
    val cs = MaterialTheme.colorScheme
    val typo = MaterialTheme.typography
    // Bara dessa läses i kompositionen, och de ändras högst en gång per sekund.
    val inandning by remember { derivedStateOf { gatt.value % CYKEL_MS < IN_MS } }
    val sekKvarIFas by remember {
        derivedStateOf {
            val t = gatt.value % CYKEL_MS
            ((if (t < IN_MS) IN_MS - t else CYKEL_MS - t) + 999) / 1000
        }
    }
    val sekKvar by remember { derivedStateOf { (TOTAL_MS - gatt.value + 999) / 1000 } }
    LaunchedEffect(inandning) { Haptics.andning(ctx, if (inandning) Haptics.Andning.IN else Haptics.Andning.UT) }

    val karna = cs.primary
    val glod = cs.primaryContainer
    val kant = cs.onPrimary.copy(alpha = 0.18f)
    Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
        // Minuten som en ring längs kanten, som klockans egna timers.
        CircularProgressIndicator(
            progress = { gatt.value / TOTAL_MS.toFloat() },
            modifier = Modifier.fillMaxSize().padding(2.dp),
            strokeWidth = 6.dp,
            colors = ProgressIndicatorDefaults.colors(indicatorColor = cs.tertiary, trackColor = cs.surfaceContainer),
        )
        Canvas(Modifier.fillMaxSize().padding(22.dp)) {
            val f = fyllnad(gatt.value % CYKEL_MS)
            val max = size.minDimension / 2
            val r = max * (0.46f + 0.54f * f)
            // Svag halo som andas med, och en mjuk kant runt kärnan.
            drawCircle(Brush.radialGradient(listOf(glod.copy(alpha = 0.10f + 0.45f * f), Color.Transparent), center, max), radius = max)
            drawCircle(glod.copy(alpha = 0.30f + 0.30f * f), radius = r + 7.dp.toPx())
            drawCircle(Brush.radialGradient(listOf(karna, karna.copy(alpha = 0.70f)), center, r), radius = r)
            drawCircle(kant, radius = r, style = Stroke(1.5.dp.toPx()))
        }
        Column(horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.Center) {
            Text(if (inandning) "Andas in" else "Andas ut", style = typo.titleMedium, color = cs.onPrimary,
                modifier = Modifier.semantics { liveRegion = LiveRegionMode.Polite })
            Text("$sekKvarIFas", style = typo.displayMedium.merge(Tab), color = cs.onPrimary)
        }
        Text(
            "$sekKvar s" + (puls()?.let { " · ${it.toInt()} BPM" } ?: ""),
            style = typo.labelSmall.merge(Tab), color = cs.onSurfaceVariant,
            modifier = Modifier.align(Alignment.BottomCenter).padding(bottom = 26.dp),
        )
    }
}

@Composable
private fun Klart(forstaPuls: Double?, slutPuls: Double?, onOk: () -> Unit) {
    val cs = MaterialTheme.colorScheme
    val typo = MaterialTheme.typography
    val a = forstaPuls; val b = slutPuls
    val text = if (a != null && b != null) "Klockfrekvens från ${a.toInt()} till ${b.toInt()} BPM."
               else "Klart. Ingen puls uppmätt under minuten."
    val state = rememberTransformingLazyColumnState()
    ScreenScaffold(scrollState = state, edgeButton = {
        EdgeButton(onClick = onOk, buttonSize = EdgeButtonSize.Medium) {
            Icon(Icons.Filled.Check, contentDescription = "Ok")
        }
    }) { pad ->
        TransformingLazyColumn(state = state, contentPadding = pad, modifier = Modifier.fillMaxSize()) {
            item {
                Column(Modifier.fillMaxWidth().padding(horizontal = 16.dp).padding(top = 18.dp),
                    horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.Center) {
                    Text("Klart", style = typo.titleLarge, color = cs.onSurface)
                    if (a != null && b != null) {
                        Row(verticalAlignment = Alignment.CenterVertically,
                            modifier = Modifier.padding(top = 6.dp).semantics(mergeDescendants = true) { contentDescription = text }) {
                            Icon(Icons.Filled.Favorite, contentDescription = null, tint = cs.error, modifier = Modifier.size(20.dp))
                            Text(" ${a.toInt()} → ${b.toInt()}", style = typo.displaySmall.merge(Tab), color = cs.onSurface)
                        }
                        Text("BPM före och efter", style = typo.labelSmall, color = cs.onSurfaceVariant)
                    } else {
                        Text(text, style = typo.bodyMedium, color = cs.onSurfaceVariant, textAlign = TextAlign.Center,
                            modifier = Modifier.fillMaxWidth().padding(top = 6.dp).semantics { contentDescription = text })
                    }
                }
            }
        }
    }
}
