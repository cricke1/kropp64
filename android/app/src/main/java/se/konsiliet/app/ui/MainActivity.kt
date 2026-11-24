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
import androidx.compose.foundation.layout.Box
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
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.lifecycleScope
import kotlinx.coroutines.launch
import se.konsiliet.app.hc.HcScheduler
import se.konsiliet.app.link.LiveService
import se.konsiliet.app.link.UploadScheduler
import se.konsiliet.app.link.WatchListenerService
import se.konsiliet.app.ui.screens.AskScreen
import se.konsiliet.app.ui.screens.ConsultDetail
import se.konsiliet.app.ui.screens.ConsultsScreen
import se.konsiliet.app.ui.screens.SettingsScreen
import se.konsiliet.app.ui.screens.TimelineScreen
import se.konsiliet.app.ui.screens.TodayScreen
import se.konsiliet.app.ui.theme.KonsilietTheme
import se.konsiliet.app.ui.theme.LocalTokens
import se.konsiliet.app.ui.theme.Type

enum class Tab(val label: String) { Idag("Idag"), Tidslinje("Tidslinje"), Konsiliet("Konsiliet"), Fraga("Fråga"), Installningar("Inställningar") }

class MainActivity : ComponentActivity() {
    companion object { const val EXTRA_CONSULT = "consult_id" }

    private var openConsult by mutableStateOf<String?>(null)

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
    }

    @Composable
    private fun Root() {
        val t = LocalTokens.current
        var tab by rememberSaveable { mutableStateOf(Tab.Idag) }
        val consult = openConsult
        Column(Modifier.fillMaxSize().background(t.bg).statusBarsPadding()) {
            Box(Modifier.weight(1f)) {
                if (consult != null) {
                    BackHandler { openConsult = null }
                    ConsultDetail(consult, onBack = { openConsult = null })
                } else when (tab) {
                    Tab.Idag -> TodayScreen()
                    Tab.Tidslinje -> TimelineScreen(onOpenConsult = { openConsult = it })
                    Tab.Konsiliet -> ConsultsScreen(onOpen = { openConsult = it })
                    Tab.Fraga -> AskScreen(onStarted = { openConsult = it })
                    Tab.Installningar -> SettingsScreen()
                }
            }
            Box(Modifier.fillMaxWidth().height(1.dp).background(t.rule))
            Row(Modifier.fillMaxWidth().background(t.surface).navigationBarsPadding()) {
                Tab.entries.forEach { e ->
                    val sel = e == tab && consult == null
                    Column(
                        Modifier.weight(1f).clickable { tab = e; openConsult = null },
                        horizontalAlignment = Alignment.CenterHorizontally,
                    ) {
                        Box(Modifier.fillMaxWidth().height(2.dp).background(if (sel) t.accent else t.surface))
                        Text(e.label, style = Type.label.copy(fontWeight = if (sel) FontWeight(600) else FontWeight(500)),
                            color = if (sel) t.ink else t.ink3, maxLines = 1,
                            modifier = Modifier.padding(top = 12.dp, bottom = 14.dp))
                    }
                }
            }
        }
    }
}
