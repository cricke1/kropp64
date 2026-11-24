package se.konsiliet.wear.ui

import android.os.Bundle
import android.view.WindowManager
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.semantics
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
import androidx.wear.compose.material3.Button
import androidx.wear.compose.material3.MaterialTheme
import androidx.wear.compose.material3.Text
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import se.konsiliet.wear.data.Pending
import se.konsiliet.wear.data.QueueDb
import se.konsiliet.wear.link.Flush

/**
 * 60 sekunder lugn andning: in 4 s, ut 6 s (sex andetag i minuten). Pulsen mäts under tiden och visas
 * före och efter, så att man ser om det hjälpte. Startas från stressknuffen ("Andas 60 s") eller från
 * klockans startsida. Andningen loggas som mätvärdet "andning" (sekunder) så att servern kan jämföra pulsen.
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
            MaterialTheme {
                var nu by remember { mutableLongStateOf(System.currentTimeMillis()) }
                var klar by remember { mutableStateOf(false) }
                var slutPuls by remember { mutableStateOf<Double?>(null) }
                LaunchedEffect(Unit) {
                    while (nu - start < 60_000) { delay(100); nu = System.currentTimeMillis() }
                    slutPuls = puls; klar = true
                    lifecycleScope.launch(Dispatchers.IO) {
                        QueueDb.get(applicationContext).pending().insert(listOf(Pending(metric = "andning", ts = start / 1000.0, value = 60.0)))
                        Flush.request(applicationContext)
                    }
                }
                val t = ((nu - start) % 10_000) / 1000f
                val inandning = t < 4f
                // 0..1: växer under inandningen, krymper under utandningen
                val f = if (inandning) t / 4f else 1f - (t - 4f) / 6f
                Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    Column(horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.Center,
                        modifier = Modifier.padding(24.dp)) {
                        if (!klar) {
                            Canvas(Modifier.size(110.dp)) {
                                drawCircle(Color(0xFF2A3134), radius = size.minDimension / 2)
                                drawCircle(Color(0xFF8FC1CC), radius = size.minDimension / 2 * (0.35f + 0.65f * f))
                            }
                            Text(if (inandning) "Andas in" else "Andas ut", fontSize = 20.sp, color = Color(0xFFE8ECEA),
                                modifier = Modifier.padding(top = 8.dp).semantics { liveRegion = LiveRegionMode.Polite })
                            Text("${60 - (nu - start) / 1000} s" + (puls?.let { " · ${it.toInt()} BPM" } ?: ""),
                                fontSize = 13.sp, color = Color(0xFF8E9894))
                        } else {
                            val a = forstaPuls; val b = slutPuls
                            val text = if (a != null && b != null) "Klockfrekvens från ${a.toInt()} till ${b.toInt()} BPM."
                                       else "Klart. Ingen puls uppmätt under minuten."
                            Text("Klart", fontSize = 18.sp, color = Color(0xFFE8ECEA))
                            Text(text, fontSize = 13.sp, color = Color(0xFFE8ECEA), textAlign = TextAlign.Center,
                                modifier = Modifier.semantics { contentDescription = text })
                            Button(onClick = { finish() }, modifier = Modifier.padding(top = 8.dp)) { Text("Ok") }
                        }
                    }
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
