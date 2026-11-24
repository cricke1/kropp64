package se.konsiliet.wear.ui

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
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
import androidx.wear.compose.foundation.lazy.ScalingLazyColumn
import androidx.wear.compose.foundation.lazy.rememberScalingLazyListState
import androidx.wear.compose.material3.AppScaffold
import androidx.wear.compose.material3.Button
import androidx.wear.compose.material3.ButtonDefaults
import androidx.wear.compose.material3.ColorScheme
import androidx.wear.compose.material3.MaterialTheme
import androidx.wear.compose.material3.ScreenScaffold
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
        setContent {
            MaterialTheme(colorScheme = ColorScheme(primary = Accent, onPrimary = Color(0xFF0E1A1E))) {
                AppScaffold { Screen(permsOk, onAskPerms = { askForeground.launch(Permissions.foreground()) }) }
            }
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
    val pending by remember { QueueDb.get(ctx).pending().countFlow() }.collectAsState(initial = 0)
    val msg by ExerciseService.message.collectAsState()
    var now by remember { mutableLongStateOf(System.currentTimeMillis()) }
    var available by remember { mutableStateOf<List<String>>(emptyList()) }
    var choosing by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()
    LaunchedEffect(Unit) {
        available = runCatching { Passive.available(ctx) }.getOrDefault(emptyList())
        while (true) { delay(1000); now = System.currentTimeMillis() }
    }
    val listState = rememberScalingLazyListState()

    ScreenScaffold(scrollState = listState) {
        ScalingLazyColumn(state = listState, modifier = Modifier.fillMaxWidth(),
            horizontalAlignment = Alignment.CenterHorizontally) {
            item {
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    Text("Puls", color = Dim, fontSize = 12.sp)
                    Row(verticalAlignment = Alignment.Bottom) {
                        Text(status.lastHr?.let { "%.0f".format(it) } ?: "--",
                            style = Tab, fontSize = 44.sp, fontWeight = FontWeight.Medium, color = Ink)
                        Text(" slag/min", color = Dim, fontSize = 12.sp, modifier = Modifier.padding(bottom = 8.dp))
                    }
                    Text(ago(status.lastHrAt, now), color = Dim, fontSize = 12.sp, style = Tab)
                }
            }
            if (WatchState.isEmulator()) {
                item { Text("Emulator: syntetisk testdata", color = Warn, fontSize = 11.sp) }
            }
            item {
                Column(horizontalAlignment = Alignment.CenterHorizontally, modifier = Modifier.padding(top = 6.dp)) {
                    Text("Senast skickat ${ago(status.lastSentAt, now)}", color = Ink, fontSize = 13.sp, style = Tab)
                    Text("I kö på klockan: $pending", color = Dim, fontSize = 12.sp, style = Tab)
                    status.lastError?.let {
                        Text(it, color = Warn, fontSize = 11.sp, textAlign = TextAlign.Center,
                            modifier = Modifier.padding(horizontal = 12.dp))
                    }
                }
            }
            if (!permsOk) {
                item {
                    Button(onClick = onAskPerms, modifier = Modifier.fillMaxWidth()) { Text("Ge behörighet") }
                }
            }
            if (status.exerciseActive) {
                item {
                    val min = (now - status.exerciseStartedAt) / 60000
                    Column(horizontalAlignment = Alignment.CenterHorizontally) {
                        Text("Pass pågår, $min min", color = Accent, fontSize = 13.sp, style = Tab)
                        Spacer(Modifier.height(4.dp))
                        Button(onClick = { ExerciseService.stop(ctx) }, modifier = Modifier.fillMaxWidth(),
                            colors = ButtonDefaults.filledTonalButtonColors()) { Text("Avsluta pass") }
                    }
                }
            } else if (choosing) {
                EXERCISE_CHOICES.forEach { (type, label) ->
                    item {
                        Button(onClick = { choosing = false; ExerciseService.start(ctx, type) },
                            modifier = Modifier.fillMaxWidth(),
                            colors = ButtonDefaults.filledTonalButtonColors()) { Text(label) }
                    }
                }
                item { Button(onClick = { choosing = false }, modifier = Modifier.fillMaxWidth()) { Text("Avbryt") } }
            } else {
                item {
                    Button(onClick = { choosing = true }, enabled = permsOk, modifier = Modifier.fillMaxWidth()) {
                        Text("Starta träningspass")
                    }
                }
            }
            msg?.let { m -> item { Text(m, color = Warn, fontSize = 11.sp, textAlign = TextAlign.Center) } }
            item {
                Button(onClick = { scope.launch { Flush.request(ctx, urgent = true) } }, modifier = Modifier.fillMaxWidth(),
                    colors = ButtonDefaults.outlinedButtonColors()) { Text("Skicka nu") }
            }
            item {
                Column(horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(2.dp),
                    modifier = Modifier.padding(horizontal = 14.dp, vertical = 8.dp)) {
                    Text("Registrerat passivt", color = Dim, fontSize = 11.sp)
                    Text(status.registered ?: "inget ännu", color = Ink, fontSize = 11.sp, textAlign = TextAlign.Center)
                    Text("Klockan erbjuder", color = Dim, fontSize = 11.sp)
                    Text(available.joinToString(", ").ifEmpty { "okänt" }, color = Ink, fontSize = 11.sp, textAlign = TextAlign.Center)
                }
            }
        }
    }
}

