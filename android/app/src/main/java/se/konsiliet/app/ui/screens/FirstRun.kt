package se.konsiliet.app.ui.screens

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.launch
import se.konsiliet.app.data.Prefs
import se.konsiliet.app.link.LiveService
import se.konsiliet.app.link.UploadScheduler
import se.konsiliet.app.net.Api
import se.konsiliet.app.ui.theme.LocalTokens
import se.konsiliet.app.ui.theme.Type

/** Giltig adress: http(s)://värd[:port], utan avslutande snedstreck. */
fun normalizeServerUrl(raw: String): String? {
    val s = raw.trim().trimEnd('/')
    val u = runCatching { java.net.URI(s) }.getOrNull() ?: return null
    if (u.scheme != "http" && u.scheme != "https") return null
    if (u.host.isNullOrBlank()) return null
    return s
}

/**
 * Första start. Appen har ingen inbyggd serveradress (repot är publikt och servern är min egen),
 * så ingenting skickas förrän användaren angett vart. Klockdata som kommer in innan dess ligger kvar
 * i kön och laddas upp när adressen är satt.
 */
@Composable
fun FirstRunScreen() {
    val t = LocalTokens.current
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    var url by remember { mutableStateOf("") }
    var token by remember { mutableStateOf("") }
    var status by remember { mutableStateOf<String?>(null) }
    var ok by remember { mutableStateOf<Boolean?>(null) }
    var busy by remember { mutableStateOf(false) }
    val valid = normalizeServerUrl(url)

    fun save() {
        Prefs.updateConfig { it.copy(serverUrl = valid!!, deviceToken = token) }
        LiveService.start(ctx); UploadScheduler.now(ctx)
    }

    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).imePadding().padding(horizontal = 20.dp, vertical = 28.dp)) {
        Text("Konsiliet", style = Type.title, color = t.ink)
        Spacer(Modifier.height(10.dp))
        Text("Appen skickar data från klockan och Health Connect till din egen Konsiliet-server. " +
            "Ange serverns adress för att börja. Inget skickas någon annanstans.", style = Type.body, color = t.ink2)
        Spacer(Modifier.height(20.dp))
        OutlinedTextField(url, { url = it; ok = null; status = null }, label = { Text("Serveradress") },
            placeholder = { Text("http://100.x.y.z:8790 eller https://...") },
            singleLine = true, modifier = Modifier.fillMaxWidth(),
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri),
            isError = url.isNotBlank() && valid == null,
            supportingText = {
                Text(if (url.isNotBlank() && valid == null) "Adressen ska börja med http:// eller https://"
                else "Via Tailscale: Mac minins Tailscale-adress. Utifrån: Cloudflare Tunnel-adressen.")
            })
        Spacer(Modifier.height(8.dp))
        OutlinedTextField(token, { token = it }, label = { Text("Enhetstoken (valfri via Tailscale)") },
            singleLine = true, modifier = Modifier.fillMaxWidth())
        Spacer(Modifier.height(20.dp))
        Row(verticalAlignment = Alignment.CenterVertically) {
            Button(enabled = valid != null && !busy, onClick = {
                busy = true; status = "Testar ..."
                scope.launch {
                    val up = Api.healthAt(valid!!, token)
                    if (up) { save(); status = null } else {
                        ok = false
                        status = "Servern svarar inte på $valid/api/health. Kontrollera adressen och att Tailscale är på."
                    }
                    busy = false
                }
            }) { Text("Testa och fortsätt") }
            if (ok == false) {
                TextButton(onClick = { save() }) { Text("Spara ändå") }
            }
        }
        status?.let { Text(it, style = Type.small, color = if (ok == false) t.avvikelse else t.ink3, modifier = Modifier.padding(top = 10.dp)) }
    }
}
