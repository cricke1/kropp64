package se.konsiliet.app.ui.screens

import android.content.Context
import android.content.Intent
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.role
import androidx.compose.ui.semantics.selected
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.core.content.FileProvider
import java.io.File
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import se.konsiliet.app.net.Api
import se.konsiliet.app.ui.components.Section
import se.konsiliet.app.ui.theme.LocalTokens
import se.konsiliet.app.ui.theme.Type

private val DAGAR = listOf("mån", "tis", "ons", "tor", "fre", "lör", "sön")
private val KNUFFAR = listOf("afk" to "AFK för länge", "stress" to "Hög puls vid datorn", "sova" to "Läggdags", "pass" to "Passdag")
private val KLOCKA = Regex("^([01]?\\d|2[0-3]):[0-5]\\d$")

/** Plan, väckning, tysta timmar och notisbudget. Sparas på servern, som skickar knuffarna. */
@Composable
fun PlanSettings() {
    val t = LocalTokens.current
    val scope = rememberCoroutineScope()
    var inst by remember { mutableStateOf<JSONObject?>(null) }
    var msg by remember { mutableStateOf<String?>(null) }
    LaunchedEffect(Unit) { inst = runCatching { Api.getObject("/api/installningar") }.getOrNull() }

    fun spara(andring: JSONObject) {
        scope.launch {
            runCatching { Api.postJson("/api/installningar", andring) }
                .onSuccess { inst = it; msg = "Sparat." }
                .onFailure { msg = "Kunde inte spara: ${it.message}" }
        }
    }

    Section("Plan och knuffar", trailing = "sparas på servern") {
        val i = inst
        if (i == null) {
            Text("Hämtar ... (kräver kontakt med servern)", style = Type.body, color = t.ink3, modifier = Modifier.padding(20.dp))
            return@Section
        }
        Column(Modifier.padding(horizontal = 20.dp, vertical = 10.dp)) {
            Text("Passdagar (${i.optInt("pass_per_vecka")} pass i veckan)", style = Type.label, color = t.ink2)
            val valda = i.optJSONArray("passdagar")?.let { a -> (0 until a.length()).map { a.optInt(it) }.toSet() } ?: emptySet()
            Row(horizontalArrangement = Arrangement.spacedBy(4.dp), modifier = Modifier.padding(vertical = 6.dp)) {
                DAGAR.forEachIndexed { d, namn ->
                    val vald = d in valda
                    Text(namn, style = Type.label, color = if (vald) t.bg else t.ink2,
                        modifier = Modifier.background(if (vald) t.accent else t.surface).clickable {
                            val ny = if (vald) valda - d else valda + d
                            spara(JSONObject().put("passdagar", JSONArray(ny.sorted())))
                        }.padding(horizontal = 9.dp, vertical = 12.dp).semantics {
                            role = Role.Checkbox; selected = vald; contentDescription = "$namn, ${if (vald) "passdag" else "ingen passdag"}"
                        })
                }
            }
            KlockRad("Påminnelse om passet", i.optString("passtid")) { spara(JSONObject().put("passtid", it)) }
            KlockRad("Väckning vardagar", i.optString("vakna")) { spara(JSONObject().put("vakna", it)) }
            KlockRad("Väckning helger", i.optString("vakna_helg")) { spara(JSONObject().put("vakna_helg", it)) }
            KlockRad("Tysta timmar från", i.optString("tyst_fran")) { spara(JSONObject().put("tyst_fran", it)) }
            KlockRad("Tysta timmar till", i.optString("tyst_till")) { spara(JSONObject().put("tyst_till", it)) }
            Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.padding(top = 8.dp)) {
                Text("Knuffar per dag", style = Type.body, color = t.ink, modifier = Modifier.weight(1f))
                listOf(3, 6, 10).forEach { n ->
                    Text("$n", style = Type.label, color = if (i.optInt("notisbudget") == n) t.ink else t.ink3,
                        modifier = Modifier.clickable { spara(JSONObject().put("notisbudget", n)) }.padding(horizontal = 14.dp, vertical = 12.dp)
                            .semantics { selected = i.optInt("notisbudget") == n })
                }
            }
            Text("Akuta larm räknas aldrig och går alltid fram.", style = Type.small, color = t.ink3)
            val kn = i.optJSONObject("knuffar") ?: JSONObject()
            KNUFFAR.forEach { (k, namn) ->
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(namn, style = Type.body, color = t.ink, modifier = Modifier.weight(1f))
                    Switch(checked = kn.optBoolean(k, true), onCheckedChange = { on ->
                        spara(JSONObject().put("knuffar", JSONObject(kn.toString()).put(k, on)))
                    })
                }
            }
            msg?.let { Text(it, style = Type.small, color = t.ink2) }
        }
    }
}

@Composable
private fun KlockRad(label: String, varde: String, onSpara: (String) -> Unit) {
    val t = LocalTokens.current
    var text by remember(varde) { mutableStateOf(varde) }
    Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.fillMaxWidth().padding(vertical = 2.dp)) {
        Text(label, style = Type.body, color = t.ink, modifier = Modifier.weight(1f))
        OutlinedTextField(text, { text = it.filter { c -> c.isDigit() || c == ':' }.take(5) }, singleLine = true,
            modifier = Modifier.width(96.dp), textStyle = Type.body, isError = !KLOCKA.matches(text),
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number))
        TextButton(enabled = text != varde && KLOCKA.matches(text), onClick = { onSpara(text.padStart(5, '0')) }) { Text("Spara") }
    }
}

/** Besöksunderlaget (PDF) hämtas från servern och öppnas i telefonens PDF-visare. Inget sparas utanför appen. */
@Composable
fun BesoksunderlagKnapp() {
    val t = LocalTokens.current
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    var msg by remember { mutableStateOf<String?>(null) }
    Section("Inför besök på vårdcentralen") {
        Column(Modifier.padding(horizontal = 20.dp, vertical = 10.dp)) {
            Text("Besöksunderlaget: 30 dagars kurvor, trådarnas lösningar med källor, provsvar utanför referens och frågor att ställa. " +
                "Visa det för läkaren eller skriv ut.", style = Type.body, color = t.ink2)
            TextButton(onClick = {
                msg = "Skapar PDF ..."
                scope.launch { msg = runCatching { oppnaPdf(ctx); null }.getOrElse { "Gick inte: ${it.message}" } }
            }) { Text("Öppna besöksunderlaget (PDF)") }
            msg?.let { Text(it, style = Type.small, color = t.ink3) }
        }
    }
}

suspend fun oppnaPdf(ctx: Context) {
    val fil = withContext(Dispatchers.IO) {
        val dir = File(ctx.cacheDir, "pdf").apply { mkdirs() }
        val f = File(dir, "besoksunderlag.pdf")
        Api.http.newCall(Api.request("/api/besoksunderlag.pdf").get().build()).execute().use { r ->
            if (!r.isSuccessful) throw java.io.IOException("HTTP ${r.code}")
            f.outputStream().use { out -> r.body!!.byteStream().copyTo(out) }
        }
        f
    }
    val uri = FileProvider.getUriForFile(ctx, ctx.packageName + ".filer", fil)
    ctx.startActivity(Intent.createChooser(Intent(Intent.ACTION_VIEW).setDataAndType(uri, "application/pdf")
        .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION), "Öppna besöksunderlaget").addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
}
