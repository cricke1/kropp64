package se.konsiliet.app.ui

import android.Manifest
import android.content.Intent
import android.os.Build
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.BackHandler
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.IntrinsicSize
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.role
import androidx.compose.ui.semantics.selected
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import androidx.lifecycle.lifecycleScope
import kotlinx.coroutines.launch
import se.konsiliet.app.hc.HcScheduler
import se.konsiliet.app.link.LiveService
import se.konsiliet.app.link.UploadScheduler
import se.konsiliet.app.link.WatchListenerService
import se.konsiliet.app.data.Prefs
import se.konsiliet.app.ui.screens.AskScreen
import se.konsiliet.app.ui.screens.FirstRunScreen
import se.konsiliet.app.ui.screens.IdagScreen
import se.konsiliet.app.ui.screens.startaFraga
import se.konsiliet.app.ui.screens.ConsultDetail
import se.konsiliet.app.ui.screens.ConsultsScreen
import se.konsiliet.app.ui.screens.SettingsScreen
import se.konsiliet.app.ui.screens.TimelineScreen
import se.konsiliet.app.ui.screens.TodayScreen
import se.konsiliet.app.ui.theme.KonsilietTheme
import se.konsiliet.app.ui.theme.LocalTokens
import se.konsiliet.app.ui.theme.Type

// Idag först: svaret på "ska jag träna i dag?" utan att leta. Ny tråd nås från Idag och Trådar.
enum class Tab(val label: String) { Idag("Idag"), Sensorer("Sensorer"), Tidslinje("Tidslinje"), Konsiliet("Trådar"), Installningar("Inställningar") }

class MainActivity : ComponentActivity() {
    companion object { const val EXTRA_CONSULT = "consult_id" }

    private var openConsult by mutableStateOf<String?>(null)
    private var asking by mutableStateOf(false)

    private val askNotif = registerForActivityResult(ActivityResultContracts.RequestPermission()) {}

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        openConsult = intent?.getStringExtra(EXTRA_CONSULT)
        if (Build.VERSION.SDK_INT >= 33) askNotif.launch(Manifest.permission.POST_NOTIFICATIONS)
        LiveService.start(this)
        setContent { KonsilietTheme { Root() } }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        intent.getStringExtra(EXTRA_CONSULT)?.let { openConsult = it }
    }

    override fun onResume() {
        super.onResume()
        // När appen öppnas: be klockan tömma sin kö, ladda upp, läs Health Connect.
        lifecycleScope.launch { WatchListenerService.requestFlush(applicationContext) }
        UploadScheduler.now(this)
        HcScheduler.now(this)
        se.konsiliet.app.widget.Summary.refreshSoon(this, delaySeconds = 0)
    }

    @Composable
    private fun Root() {
        val t = LocalTokens.current
        var tab by rememberSaveable { mutableStateOf(Tab.Idag) }
        val consult = openConsult
        // Första start: ingen serveradress än. Bara första-gångs-vyn, ingen flikrad.
        val firstRun = Prefs.config.collectAsState().value.serverUrl.isBlank()
        Column(Modifier.fillMaxSize().background(t.bg).statusBarsPadding()) {
            Box(Modifier.weight(1f)) {
                if (firstRun) {
                    FirstRunScreen()
                } else if (consult != null) {
                    BackHandler { openConsult = null }
                    ConsultDetail(consult, onBack = { openConsult = null })
                } else if (asking) {
                    BackHandler { asking = false }
                    AskScreen(onStarted = { asking = false; openConsult = it })
                } else when (tab) {
                    Tab.Idag -> IdagScreen(
                        onAsk = { q ->
                            if (q.isBlank()) asking = true
                            else lifecycleScope.launch { runCatching { startaFraga(q) }.onSuccess { openConsult = it } }
                        },
                        onOpenConsult = { openConsult = it },
                        onSettings = { tab = Tab.Installningar },
                    )
                    Tab.Sensorer -> TodayScreen()
                    Tab.Tidslinje -> TimelineScreen(onOpenConsult = { openConsult = it })
                    Tab.Konsiliet -> ConsultsScreen(onOpen = { openConsult = it }, onAsk = { asking = true })
                    Tab.Installningar -> SettingsScreen()
                }
            }
            if (!firstRun) Box(Modifier.fillMaxWidth().height(1.dp).background(t.rule))
            if (!firstRun) Row(Modifier.fillMaxWidth().background(t.surface).navigationBarsPadding().padding(horizontal = 8.dp),
                horizontalArrangement = Arrangement.SpaceBetween) {
                Tab.entries.forEach { e ->
                    val sel = e == tab && consult == null && !asking
                    Column(
                        Modifier.width(IntrinsicSize.Max).clickable { tab = e; openConsult = null; asking = false }.padding(horizontal = 2.dp)
                            .semantics { selected = sel; role = Role.Tab },
                        horizontalAlignment = Alignment.CenterHorizontally,
                    ) {
                        Box(Modifier.fillMaxWidth().height(2.dp).background(if (sel) t.accent else t.surface))
                        // Flikarnas text växer högst till 115 %: vid 130 % klipptes "Inställningar" i kanten.
                        // Resten av appen följer systemets textstorlek fullt ut.
                        val d = androidx.compose.ui.platform.LocalDensity.current
                        androidx.compose.runtime.CompositionLocalProvider(
                            androidx.compose.ui.platform.LocalDensity provides androidx.compose.ui.unit.Density(d.density, minOf(d.fontScale, 1.15f)),
                        ) {
                            Text(e.label, style = Type.label.copy(fontWeight = if (sel) FontWeight(600) else FontWeight(500)),
                                color = if (sel) t.ink else t.ink3, maxLines = 1, textAlign = TextAlign.Center, softWrap = false,
                                modifier = Modifier.padding(top = 12.dp, bottom = 14.dp))
                        }
                    }
                }
            }
        }
    }
}
