package se.konsiliet.app.ui.screens

import android.Manifest
import android.annotation.SuppressLint
import android.app.AlarmManager
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.PowerManager
import android.provider.Settings
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import androidx.health.connect.client.PermissionController
import kotlinx.coroutines.launch
import se.konsiliet.app.data.Contact
import se.konsiliet.app.data.KonsilietDb
import se.konsiliet.app.data.Prefs
import se.konsiliet.app.hc.HcScheduler
import se.konsiliet.app.hc.HealthConnectSync
import se.konsiliet.app.link.LiveService
import se.konsiliet.app.link.UploadScheduler
import se.konsiliet.app.net.Api
import se.konsiliet.app.ui.components.Fmt
import se.konsiliet.app.ui.components.ReadoutRow
import se.konsiliet.app.ui.components.Section
import se.konsiliet.app.ui.theme.LocalTokens
import se.konsiliet.app.ui.theme.Type

@SuppressLint("BatteryLife")
@Composable
fun SettingsScreen() {
    val t = LocalTokens.current
    val ctx = LocalContext.current
    val cfg by Prefs.config.collectAsState()
    val scope = rememberCoroutineScope()
    var url by remember { mutableStateOf(cfg.serverUrl) }
    var token by remember { mutableStateOf(cfg.deviceToken) }
    var goal by remember { mutableStateOf(cfg.stepsGoal.toString()) }
    var test by remember { mutableStateOf<String?>(null) }
    var cName by remember { mutableStateOf("") }
    var cNum by remember { mutableStateOf("") }
    var hcGranted by remember { mutableIntStateOf(-1) }
    var tick by remember { mutableIntStateOf(0) }
    val rejected by remember { KonsilietDb.get(ctx).samples().rejectedFlow() }.collectAsState(0)

    LaunchedEffect(tick) {
        hcGranted = if (HealthConnectSync.available(ctx)) runCatching {
            HealthConnectSync.granted(ctx).intersect(HealthConnectSync.permissions).size }.getOrDefault(0) else -2
    }
    val hcLauncher = rememberLauncherForActivityResult(PermissionController.createRequestPermissionResultContract()) {
        tick++; HcScheduler.now(ctx)
    }
    val smsLauncher = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { ok ->
        if (ok) Prefs.updateConfig { it.copy(smsEnabled = true) }
    }
    val smsGranted = ContextCompat.checkSelfPermission(ctx, Manifest.permission.SEND_SMS) == PackageManager.PERMISSION_GRANTED
    val pm = ctx.getSystemService(PowerManager::class.java)
    val unrestricted = remember(tick) { pm.isIgnoringBatteryOptimizations(ctx.packageName) }
    val exact = remember(tick) { Build.VERSION.SDK_INT < 31 || ctx.getSystemService(AlarmManager::class.java).canScheduleExactAlarms() }

    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(bottom = 32.dp)) {
        Text("Inställningar", style = Type.title, color = t.ink, modifier = Modifier.padding(start = 20.dp, top = 12.dp))

        PlanSettings()
        BesoksunderlagKnapp()

        Section("Server") {
            Column(Modifier.padding(horizontal = 20.dp, vertical = 10.dp)) {
                OutlinedTextField(url, { url = it }, label = { Text("Adress") }, singleLine = true, modifier = Modifier.fillMaxWidth(),
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri))
                Spacer(Modifier.height(8.dp))
                OutlinedTextField(token, { token = it }, label = { Text("Enhetstoken (X-Device-Token)") }, singleLine = true, modifier = Modifier.fillMaxWidth())
                if (url.startsWith("http://") && !url.contains("://100.") && !url.contains("://10.") && !url.contains("://192.168.") && !url.contains("localhost")) {
                    Text("Okrypterad http till en publik adress. Använd https via Cloudflare Tunnel.", style = Type.small, color = t.avvikelse,
                        modifier = Modifier.padding(top = 6.dp))
                }
                Row(verticalAlignment = Alignment.CenterVertically) {
                    TextButton(onClick = {
                        Prefs.updateConfig { it.copy(serverUrl = url, deviceToken = token) }
                        LiveService.start(ctx); UploadScheduler.now(ctx)
                        test = "Sparat. Testar ..."
                        scope.launch { test = if (Api.health()) "Servern svarar." else "Servern svarar inte på ${Prefs.config.value.serverUrl}/api/health." }
                    }) { Text("Spara och testa") }
                    test?.let { Text(it, style = Type.small, color = t.ink2) }
                }
            }
        }

        Section("Health Connect") {
            ReadoutRow("Behörigheter", when (hcGranted) {
                -2 -> null; -1 -> "..."; else -> "$hcGranted av ${HealthConnectSync.permissions.size}"
            }, note = if (hcGranted == -2) "Health Connect finns inte på enheten" else Prefs.link.value.hcStatus)
            Row(Modifier.padding(horizontal = 8.dp)) {
                TextButton(enabled = hcGranted != -2, onClick = { hcLauncher.launch(HealthConnectSync.permissions) }) { Text("Ge behörighet") }
                TextButton(enabled = hcGranted > 0, onClick = { HcScheduler.now(ctx) }) { Text("Läs nu") }
            }
        }

        Section("Sms till anhöriga vid akut larm") {
            Column(Modifier.padding(horizontal = 20.dp, vertical = 10.dp)) {
                Text("När vakten slår akut larm visas en notis. Trycker du inte \"Jag mår bra\" inom vald tid skickas ett sms " +
                    "från din mobil till kontakterna nedan. Avstängt som standard.", style = Type.body, color = t.ink2)
                Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.padding(top = 8.dp)) {
                    Text("Skicka sms", style = Type.body, color = t.ink, modifier = Modifier.weight(1f))
                    Switch(checked = cfg.smsEnabled, onCheckedChange = { on ->
                        if (!on) Prefs.updateConfig { it.copy(smsEnabled = false) }
                        else if (smsGranted) Prefs.updateConfig { it.copy(smsEnabled = true) }
                        else smsLauncher.launch(Manifest.permission.SEND_SMS)
                    })
                }
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text("Väntetid innan sms", style = Type.body, color = t.ink, modifier = Modifier.weight(1f))
                    listOf(2, 5, 10, 15).forEach { m ->
                        Text("$m min", style = Type.label, color = if (cfg.smsDelayMin == m) t.ink else t.ink3,
                            modifier = Modifier.padding(start = 12.dp, top = 10.dp, bottom = 10.dp)
                                .clickable { Prefs.updateConfig { it.copy(smsDelayMin = m) } })
                    }
                }
                if (cfg.smsEnabled && cfg.contacts.isEmpty()) {
                    Text("Inga kontakter: inget sms kan skickas.", style = Type.small, color = t.avvikelse)
                }
                if (!exact) {
                    Text("Exakta alarm är inte tillåtna, så sms:et kan komma några minuter sent i viloläge.", style = Type.small, color = t.avvikelse)
                    TextButton(onClick = {
                        if (Build.VERSION.SDK_INT >= 31) ctx.startActivity(Intent(Settings.ACTION_REQUEST_SCHEDULE_EXACT_ALARM, Uri.parse("package:" + ctx.packageName)))
                        tick++
                    }) { Text("Tillåt exakta alarm") }
                }
            }
            cfg.contacts.forEachIndexed { i, c ->
                Row(Modifier.fillMaxWidth().padding(horizontal = 20.dp, vertical = 4.dp), verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Text(c.name, style = Type.body, color = t.ink)
                        Text(c.number, style = Type.small, color = t.ink3)
                    }
                    TextButton(onClick = { Prefs.updateConfig { it.copy(contacts = it.contacts.filterIndexed { j, _ -> j != i }) } }) { Text("Ta bort") }
                }
            }
            Row(Modifier.padding(horizontal = 20.dp), verticalAlignment = Alignment.CenterVertically) {
                OutlinedTextField(cName, { cName = it }, label = { Text("Namn") }, singleLine = true, modifier = Modifier.weight(1f))
                Spacer(Modifier.width(8.dp))
                OutlinedTextField(cNum, { cNum = it }, label = { Text("Nummer") }, singleLine = true, modifier = Modifier.weight(1f),
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Phone))
            }
            TextButton(enabled = cName.isNotBlank() && cNum.count { it.isDigit() } >= 6, modifier = Modifier.padding(horizontal = 8.dp), onClick = {
                Prefs.updateConfig { it.copy(contacts = it.contacts + Contact(cName.trim(), cNum.trim())) }
                cName = ""; cNum = ""
            }) { Text("Lägg till kontakt") }
        }

        Section("Mål") {
            Row(Modifier.padding(horizontal = 20.dp, vertical = 10.dp), verticalAlignment = Alignment.CenterVertically) {
                OutlinedTextField(goal, { goal = it.filter(Char::isDigit).take(6) }, label = { Text("Steg per dag") }, singleLine = true,
                    modifier = Modifier.weight(1f), keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number))
                TextButton(onClick = { goal.toIntOrNull()?.let { g -> Prefs.updateConfig { it.copy(stepsGoal = g) } } }) { Text("Spara") }
            }
        }

        Section("Batteri och bakgrund") {
            ReadoutRow("Batterioptimering", if (unrestricted) "av" else "på",
                note = if (unrestricted) "Appen får nätverk även i viloläge" else "Android kan pausa uppladdning och live-länk i viloläge (Doze)",
                noteColor = if (unrestricted) null else t.avvikelse)
            if (!unrestricted) TextButton(modifier = Modifier.padding(horizontal = 8.dp), onClick = {
                ctx.startActivity(Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS, Uri.parse("package:" + ctx.packageName)))
                tick++
            }) { Text("Stäng av batterioptimering för Kropp64") }
            ReadoutRow("Avvisade av servern", Fmt.int(rejected.toDouble()), "punkter", note = "Sparas lokalt för felsökning, skickas inte igen")
        }
    }
}
