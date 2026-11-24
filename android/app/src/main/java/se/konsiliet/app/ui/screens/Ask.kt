package se.konsiliet.app.ui.screens

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.launch
import org.json.JSONObject
import se.konsiliet.app.net.Api
import se.konsiliet.app.ui.theme.LocalTokens
import se.konsiliet.app.ui.theme.Type

/** Startar en tråd med en fråga. Snabbsvaret ur datan kommer inom sekunder, teamets svar efter några minuter. */
suspend fun startaFraga(q: String, hours: Int = 72): String =
    Api.postJson("/api/consult", JSONObject().put("question", q.trim()).put("hours", hours)).getString("consult_id")

@Composable
fun AskScreen(onStarted: (String) -> Unit) {
    val t = LocalTokens.current
    var q by rememberSaveable { mutableStateOf("") }
    var hours by rememberSaveable { mutableIntStateOf(72) }
    var busy by rememberSaveable { mutableStateOf(false) }
    var err by rememberSaveable { mutableStateOf<String?>(null) }
    val scope = rememberCoroutineScope()
    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(20.dp)) {
        Text("Starta en tråd", style = Type.title, color = t.ink)
        Spacer(Modifier.height(6.dp))
        Text("Teamet läser din data och journal för den valda perioden. Varje påstående i svaret måste peka på en mätpunkt, " +
            "en journalrad eller en källa. Inga diagnoser, bara underlag.", style = Type.body, color = t.ink2)
        Spacer(Modifier.height(16.dp))
        Text("Färdiga frågor (startar direkt)", style = Type.label, color = t.ink2)
        FRAGOR.forEach { f ->
            Text(f, style = Type.body, color = t.accent, modifier = Modifier.fillMaxWidth().clickable(enabled = !busy) {
                busy = true; err = null
                scope.launch {
                    runCatching { startaFraga(f, hours) }.onSuccess { onStarted(it) }.onFailure { err = "Kunde inte starta: ${it.message}" }
                    busy = false
                }
            }.padding(vertical = 10.dp))
        }
        Spacer(Modifier.height(10.dp))
        OutlinedTextField(q, { q = it }, modifier = Modifier.fillMaxWidth().heightIn(min = 120.dp),
            label = { Text("Din fråga") }, textStyle = Type.body)
        Spacer(Modifier.height(14.dp))
        Text("Period", style = Type.label, color = t.ink2)
        Row {
            listOf(24 to "1 dygn", 72 to "3 dygn", 168 to "7 dygn", 720 to "30 dygn").forEach { (h, l) ->
                Text(l, style = Type.label, color = if (hours == h) t.ink else t.ink3,
                    modifier = Modifier.clickable { hours = h }.padding(end = 16.dp, top = 8.dp, bottom = 8.dp))
            }
        }
        Spacer(Modifier.height(14.dp))
        Button(enabled = q.isNotBlank() && !busy, onClick = {
            busy = true; err = null
            scope.launch {
                runCatching { Api.postJson("/api/consult", JSONObject().put("question", q.trim()).put("hours", hours)) }
                    .onSuccess { onStarted(it.getString("consult_id")); q = "" }
                    .onFailure { err = "Kunde inte starta: ${it.message}" }
                busy = false
            }
        }) { Text(if (busy) "Skickar ..." else "Starta tråden") }
        err?.let { Text(it, style = Type.small, color = t.akut, modifier = Modifier.padding(top = 10.dp)) }
    }
}
