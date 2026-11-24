package se.konsiliet.app.ui

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Text
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import se.konsiliet.app.ui.theme.KonsilietTheme
import se.konsiliet.app.ui.theme.LocalTokens
import se.konsiliet.app.ui.theme.Type

/** Visas av Health Connect när användaren frågar varför appen vill läsa hälsodata. */
class PrivacyActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            KonsilietTheme {
                val t = LocalTokens.current
                Column(Modifier.fillMaxSize().background(t.bg).safeDrawingPadding().verticalScroll(rememberScrollState()).padding(20.dp)) {
                    Text("Hur Konsiliet använder din hälsodata", style = Type.title, color = t.ink)
                    Spacer(Modifier.height(12.dp))
                    Text(
                        "Konsiliet läser puls, HRV, vilopuls, syremättnad, hudtemperatur, andningsfrekvens, " +
                            "sömn, steg och träningspass från Health Connect och skickar dem till din egen server " +
                            "(den adress du angett under Inställningar). Där jämförs värdena med din egen baslinje " +
                            "och ett lokalt läkarteam av språkmodeller kan ta fram underlag att ta med till vården.\n\n" +
                            "Ingen data skickas till någon annan än din server. Appen skriver ingenting till Health Connect. " +
                            "Systemet ställer inga diagnoser.\n\n" +
                            "Du kan när som helst ta bort behörigheten i Health Connect.",
                        style = Type.body, color = t.ink2,
                    )
                }
            }
        }
    }
}
