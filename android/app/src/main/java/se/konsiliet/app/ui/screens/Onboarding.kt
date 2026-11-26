package se.konsiliet.app.ui.screens

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.PowerManager
import android.provider.Settings
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.BatterySaver
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.Description
import androidx.compose.material.icons.filled.HealthAndSafety
import androidx.compose.material.icons.filled.Notifications
import androidx.compose.material.icons.filled.PhoneAndroid
import androidx.compose.material.icons.filled.Sms
import androidx.compose.material.icons.filled.Watch
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.FilledTonalButton
import androidx.compose.material3.Icon
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import androidx.health.connect.client.PermissionController
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.compose.LifecycleEventEffect
import kotlinx.coroutines.delay
import se.konsiliet.app.data.Prefs
import se.konsiliet.app.hc.HcScheduler
import se.konsiliet.app.hc.HealthConnectSync
import se.konsiliet.app.hc.Skarmtid
import se.konsiliet.app.net.Api

/**
 * Onboarding efter serveradressen: allt appen behöver frågas här, i ordning, med en rad om varför.
 * Varje steg kontrolleras igen när man kommer tillbaka från en systeminställning, och får en bock när
 * det är klart. Allt går att hoppa över och ändras senare under Mer.
 */
object Onboarding {
    const val KLAR = "onboarding_klar"
    fun klar() = Prefs.getBool(KLAR)
}

private class Steg(val ikon: ImageVector, val titel: String, val varfor: String, val klar: Boolean, val knapp: String?,
                   val valfritt: Boolean = false, val gor: () -> Unit)

@Composable
fun OnboardingScreen(onKlar: (hamta1177: Boolean) -> Unit) {
    val ctx = LocalContext.current
    val cs = MaterialTheme.colorScheme
    val typo = MaterialTheme.typography
    var tick by remember { mutableIntStateOf(0) }
    LifecycleEventEffect(Lifecycle.Event.ON_RESUME) { tick++ }
    // Klockans och 1177:s status ändras utan att appen pausas, så de läses om med jämna mellanrum.
    LaunchedEffect(Unit) { while (true) { delay(4000); tick++ } }

    val notisLauncher = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { tick++ }
    val hcLauncher = rememberLauncherForActivityResult(PermissionController.createRequestPermissionResultContract()) {
        tick++; HcScheduler.now(ctx)
    }
    val smsLauncher = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { ok ->
        if (ok) Prefs.updateConfig { it.copy(smsEnabled = true) }; tick++
    }
    var hcGranted by remember { mutableIntStateOf(-1) }
    var har1177 by remember { mutableStateOf(false) }
    LaunchedEffect(tick) {
        hcGranted = if (HealthConnectSync.available(ctx)) runCatching {
            HealthConnectSync.granted(ctx).intersect(HealthConnectSync.permissions).size }.getOrDefault(0) else -2
        har1177 = runCatching { !Api.getObject("/api/1177/status").isNull("senast_klar") }.getOrDefault(false)
    }
    val link by Prefs.link.collectAsState()
    @Suppress("UNUSED_EXPRESSION") tick

    val notiser = Build.VERSION.SDK_INT < 33 ||
        ContextCompat.checkSelfPermission(ctx, Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED
    val batteri = ctx.getSystemService(PowerManager::class.java).isIgnoringBatteryOptimizations(ctx.packageName)
    val skarm = Skarmtid.harBehorighet(ctx)
    val klocka = link.lastWatchAt > System.currentTimeMillis() - 86_400_000L
    val sms = ContextCompat.checkSelfPermission(ctx, Manifest.permission.SEND_SMS) == PackageManager.PERMISSION_GRANTED
    val total = HealthConnectSync.permissions.size

    val steg = listOf(
        Steg(Icons.Filled.Notifications, "Aviseringar", "Larm, svar från läkarteamet och knuffar.", notiser,
            "Tillåt") { if (Build.VERSION.SDK_INT >= 33) notisLauncher.launch(Manifest.permission.POST_NOTIFICATIONS) },
        Steg(Icons.Filled.HealthAndSafety, "Health Connect",
            if (hcGranted == -2) "Health Connect saknas på telefonen. Installera det från Play Butiken."
            else "Sömn, HRV, syremättnad, andning, hudtemperatur och steg. 30 dagar läses in som din baslinje.",
            hcGranted >= total, if (hcGranted == -2) "Installera" else "Ge behörighet") {
            if (hcGranted == -2) ctx.startActivity(Intent(Intent.ACTION_VIEW,
                Uri.parse("market://details?id=com.google.android.apps.healthdata")).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
            else hcLauncher.launch(HealthConnectSync.permissions)
        },
        Steg(Icons.Filled.Watch, "Klockan", "Öppna Kropp64 på Pixel Watch och tillåt puls i bakgrunden. Bocken kommer när första pulsen nått mobilen.",
            klocka, null) {},
        Steg(Icons.Filled.PhoneAndroid, "Skärmtid", "Minuter per kategori (spel, sociala, video ...) bredvid puls och sömn. Bara kategorin sparas, aldrig appen.",
            skarm, "Slå på") { Skarmtid.oppnaInstallning(ctx) },
        Steg(Icons.Filled.BatterySaver, "Batterioptimering", "Annars kan Android pausa länken till klockan och servern i viloläge.",
            batteri, "Stäng av") {
            ctx.startActivity(Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS, Uri.parse("package:" + ctx.packageName))
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
        },
        Steg(Icons.Filled.Description, "Journalen från 1177", "Journal och provsvar med ditt BankID, så kan läkarteamet läsa dem. Sparas bara på Mac minin.",
            har1177, "Hämta med BankID") { Prefs.putBool(Onboarding.KLAR, true); onKlar(true) },
        Steg(Icons.Filled.Sms, "Sms till anhörig vid larm", "Valfritt. Om du inte svarar på ett akut larm skickas sms till den du väljer. Kontakterna läggs till under Mer.",
            sms, "Tillåt sms", valfritt = true) { smsLauncher.launch(Manifest.permission.SEND_SMS) },
    )
    val klara = steg.count { it.klar }
    val nasta = steg.indexOfFirst { !it.klar && !it.valfritt }

    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).navigationBarsPadding().padding(bottom = 24.dp)) {
        Text("Kom igång", style = typo.headlineLarge, color = cs.onSurface, modifier = Modifier.padding(start = 24.dp, end = 24.dp, top = 28.dp))
        Text("Sju steg, ungefär två minuter. Allt kan ändras senare under Mer.", style = typo.bodyLarge, color = cs.onSurfaceVariant,
            modifier = Modifier.padding(horizontal = 24.dp, vertical = 8.dp))
        LinearProgressIndicator(progress = { klara.toFloat() / steg.size }, modifier = Modifier.fillMaxWidth().padding(horizontal = 24.dp, vertical = 8.dp))
        steg.forEachIndexed { k, s ->
            val aktiv = k == nasta
            Card(Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 5.dp), shape = RoundedCornerShape(24.dp),
                colors = CardDefaults.cardColors(containerColor = if (aktiv) cs.secondaryContainer else cs.surfaceContainerLow)) {
                Row(Modifier.padding(16.dp), verticalAlignment = Alignment.Top) {
                    Box(Modifier.size(40.dp).background((if (s.klar) cs.primary else cs.onSurfaceVariant).copy(alpha = 0.14f), CircleShape),
                        contentAlignment = Alignment.Center) {
                        Icon(if (s.klar) Icons.Filled.CheckCircle else s.ikon, null, tint = if (s.klar) cs.primary else cs.onSurfaceVariant,
                            modifier = Modifier.size(22.dp))
                    }
                    Column(Modifier.padding(start = 14.dp).weight(1f)) {
                        Text(s.titel, style = typo.titleMedium, color = cs.onSurface)
                        if (!s.klar || aktiv) Text(s.varfor, style = typo.bodyMedium, color = cs.onSurfaceVariant, modifier = Modifier.padding(top = 2.dp))
                        if (s.klar) Text("Klart", style = typo.labelLarge, color = cs.primary, modifier = Modifier.padding(top = 2.dp))
                        else if (s.knapp != null) {
                            if (aktiv) Button(onClick = s.gor, modifier = Modifier.padding(top = 10.dp)) { Text(s.knapp) }
                            else FilledTonalButton(onClick = s.gor, modifier = Modifier.padding(top = 10.dp)) { Text(s.knapp) }
                        }
                    }
                }
            }
        }
        Spacer(Modifier.height(12.dp))
        Row(Modifier.fillMaxWidth().padding(horizontal = 24.dp), horizontalArrangement = Arrangement.End, verticalAlignment = Alignment.CenterVertically) {
            if (nasta >= 0) TextButton(onClick = { Prefs.putBool(Onboarding.KLAR, true); onKlar(false) }) { Text("Hoppa över resten") }
            Button(onClick = { Prefs.putBool(Onboarding.KLAR, true); onKlar(false) }, enabled = nasta < 0) { Text("Klart") }
        }
    }
}
