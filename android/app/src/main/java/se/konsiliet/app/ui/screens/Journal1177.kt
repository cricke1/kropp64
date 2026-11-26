package se.konsiliet.app.ui.screens

import android.app.PendingIntent
import android.content.ActivityNotFoundException
import android.content.Context
import android.content.Intent
import android.net.Uri
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Description
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.FilledTonalButton
import androidx.compose.material3.Icon
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
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
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.work.CoroutineWorker
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import java.util.concurrent.TimeUnit
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.launch
import org.json.JSONObject
import se.konsiliet.app.R
import se.konsiliet.app.alerts.Channels
import se.konsiliet.app.data.KonsilietDb
import se.konsiliet.app.data.Prefs
import se.konsiliet.app.net.Api
import se.konsiliet.app.ui.MainActivity
import se.konsiliet.app.ui.components.Fmt

/**
 * Journalen från 1177, inbyggd i appen.
 *
 * Ett tryck startar hämtningen på Mac minin. När servern har en BankID-länk öppnas BankID-appen direkt
 * (autostarttoken, redirect=null: på Android går BankID tillbaka till appen som öppnade den). Godkännandet
 * kan aldrig automatiseras bort, men resten sköts av sig själv: förloppet syns här, oförändrade sidor
 * tolkas inte om, och en påminnelse kommer om journalen inte hämtats på en vecka.
 */
object Journal1177 {
    const val EXTRA_START = "starta_1177"
    private const val DAGAR = 7

    fun periodic(ctx: Context) {
        WorkManager.getInstance(ctx).enqueueUniquePeriodicWork(
            "journal1177-paminnelse", ExistingPeriodicWorkPolicy.KEEP,
            PeriodicWorkRequestBuilder<Journal1177Worker>(1, TimeUnit.DAYS).build(),
        )
    }

    /** Påminnelse när journalen är äldre än en vecka, högst var tredje dag. Ett tryck startar hämtningen. */
    suspend fun paminnOmGammal(ctx: Context) {
        val s = runCatching { Api.getObject("/api/1177/status") }.getOrNull() ?: return
        if (s.optBoolean("pagar")) return
        val senast = if (s.isNull("senast_klar")) 0.0 else s.optDouble("senast_klar")
        val nu = System.currentTimeMillis()
        if (senast > 0 && nu / 1000.0 - senast < DAGAR * 86400) return
        if (nu - Prefs.getLong("paminnelse1177") < 3 * 86_400_000L) return
        Prefs.putLong("paminnelse1177", nu)
        val i = Intent(ctx, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP).putExtra(EXTRA_START, true)
        val pi = PendingIntent.getActivity(ctx, 1177, i, PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
        val text = if (senast > 0) "Senast hämtad ${Fmt.day(senast)}. Tryck för att hämta nya anteckningar och provsvar med BankID."
                   else "Hämta journal och provsvar med BankID, så kan läkarteamet läsa dem."
        val n = NotificationCompat.Builder(ctx, Channels.KNUFF).setSmallIcon(R.drawable.ic_stat)
            .setContentTitle("Dags att hämta journalen från 1177").setContentText(text)
            .setStyle(NotificationCompat.BigTextStyle().bigText(text)).setAutoCancel(true).setContentIntent(pi).build()
        runCatching { NotificationManagerCompat.from(ctx).notify(1177, n) }
    }

    fun oppnaBankId(ctx: Context, url: String): Boolean = try {
        ctx.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url)).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
        true
    } catch (e: ActivityNotFoundException) { false }
}

class Journal1177Worker(ctx: Context, params: WorkerParameters) : CoroutineWorker(ctx, params) {
    override suspend fun doWork(): Result {
        Journal1177.paminnOmGammal(applicationContext)
        return Result.success()
    }
}

private val STATUS_TEXT = mapOf(
    "loggar_in" to "Öppnar 1177 ...", "bankid_lank" to "Godkänn i BankID-appen.", "qr" to "Godkänn i BankID-appen.",
    "inloggad" to "Inloggad. Hämtar journalen ...", "hamtar" to "Hämtar ...", "tolkar" to "Läser anteckningarna ...",
    "klar" to "Klart.", "misslyckades" to "Hämtningen misslyckades.",
)

@Composable
fun Journal1177Card(autoStart: Boolean, onAutoStarted: () -> Unit) {
    val ctx = LocalContext.current
    val cs = MaterialTheme.colorScheme
    val typo = MaterialTheme.typography
    val scope = rememberCoroutineScope()
    var refresh by remember { mutableIntStateOf(0) }
    var startedAt by remember { mutableLongStateOf(0L) }
    var oppnadFor by remember { mutableLongStateOf(-1L) }
    var fel by remember { mutableStateOf<String?>(null) }
    val ev by remember { KonsilietDb.get(ctx).events().recent(200).map { l -> l.firstOrNull { it.kind == "sync.1177" } } }.collectAsState(null)
    val status by produceState<JSONObject?>(null, refresh, ev?.id) {
        value = runCatching { Api.getObject("/api/1177/status") }.getOrNull()
    }
    // Händelsen hör till den här hämtningen om den kom efter knapptrycket (eller om en hämtning pågår).
    val aktuell = ev?.takeIf { startedAt > 0 && it.ts * 1000 >= startedAt - 5000 || status?.optBoolean("pagar") == true }
    val p = aktuell?.let { runCatching { JSONObject(it.payload) }.getOrNull() }
    val st = p?.optString("status")

    fun starta() {
        fel = null; startedAt = System.currentTimeMillis()
        scope.launch {
            runCatching { Api.postJson("/api/sync/1177", JSONObject()) }.onFailure { fel = "Når inte servern: ${it.message}" }
            refresh++
        }
    }
    LaunchedEffect(autoStart) { if (autoStart) { starta(); onAutoStarted() } }
    // BankID öppnas av sig själv när länken kommer, en gång per länk.
    LaunchedEffect(aktuell?.id) {
        val e = aktuell ?: return@LaunchedEffect
        if (st == "bankid_lank" && oppnadFor != e.id) {
            oppnadFor = e.id
            p?.optString("url")?.takeIf { it.startsWith("bankid:") }?.let { url ->
                if (!Journal1177.oppnaBankId(ctx, url)) fel = "BankID-appen finns inte på telefonen."
            }
        }
    }
    LaunchedEffect(st) { while (st != null && st != "klar" && st != "misslyckades") { delay(5000); refresh++ } }

    Card(Modifier.fillMaxWidth().padding(start = 12.dp, end = 12.dp, top = 12.dp), shape = RoundedCornerShape(28.dp),
        colors = CardDefaults.cardColors(containerColor = cs.surfaceContainerLow)) {
        Column(Modifier.padding(20.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Box(Modifier.size(40.dp).background(cs.primary.copy(alpha = 0.16f), CircleShape), contentAlignment = Alignment.Center) {
                    Icon(Icons.Filled.Description, null, tint = cs.primary, modifier = Modifier.size(22.dp))
                }
                Column(Modifier.padding(start = 12.dp).weight(1f)) {
                    Text("Journalen från 1177", style = typo.titleMedium, color = cs.onSurface)
                    val s = status
                    Text(
                        when {
                            s == null -> "Hämtar status ..."
                            s.isNull("senast_klar") -> "Inte hämtad än"
                            else -> "Hämtad ${Fmt.day(s.optDouble("senast_klar"))} · ${s.optInt("anteckningar")} anteckningar · ${s.optInt("provsvar")} provsvar"
                        }, style = typo.bodySmall, color = cs.onSurfaceVariant,
                    )
                }
            }
            if (st != null) {
                Text(STATUS_TEXT[st] ?: st, style = typo.bodyMedium, color = if (st == "misslyckades") cs.error else cs.onSurface,
                    modifier = Modifier.padding(top = 14.dp))
                p?.optString("detail")?.takeIf { it.isNotBlank() }?.let { Text(it, style = typo.bodySmall, color = cs.onSurfaceVariant) }
                if (st == "hamtar" && p.optInt("av") > 0) {
                    LinearProgressIndicator(progress = { p.optInt("steg").toFloat() / p.optInt("av") },
                        modifier = Modifier.fillMaxWidth().padding(top = 8.dp))
                    Text("${p.optString("kategori")} (${p.optInt("steg")} av ${p.optInt("av")})", style = typo.bodySmall, color = cs.onSurfaceVariant)
                }
                if (st == "klar") Text("${p.optInt("nya_anteckningar")} nya anteckningar och ${p.optInt("nya_provsvar")} nya provsvar." +
                    (if (p.optInt("oforandrade") > 0) " ${p.optInt("oforandrade")} sidor var oförändrade." else ""),
                    style = typo.bodySmall, color = cs.onSurfaceVariant)
                if (st == "bankid_lank") p?.optString("url")?.let { url ->
                    FilledTonalButton(onClick = { Journal1177.oppnaBankId(ctx, url) }, modifier = Modifier.padding(top = 8.dp)) { Text("Öppna BankID") }
                }
            }
            fel?.let { Text(it, style = typo.bodySmall, color = cs.error, modifier = Modifier.padding(top = 8.dp)) }
            val pagar = st != null && st != "klar" && st != "misslyckades"
            if (!pagar) Row(Modifier.padding(top = 12.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                FilledTonalButton(onClick = { starta() }) { Text(if (status?.isNull("senast_klar") == false) "Hämta nytt" else "Hämta med BankID") }
            }
            Text("Inloggningen sker med ditt BankID direkt mot 1177. Journalen sparas bara på Mac minin.",
                style = typo.bodySmall, color = cs.onSurfaceVariant, modifier = Modifier.padding(top = 10.dp))
        }
    }
}
