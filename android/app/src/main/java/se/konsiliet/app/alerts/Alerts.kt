package se.konsiliet.app.alerts

import android.Manifest
import android.app.AlarmManager
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.telephony.SmsManager
import android.util.Log
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import kotlinx.coroutines.launch
import org.json.JSONObject
import se.konsiliet.app.R
import se.konsiliet.app.data.EventRow
import se.konsiliet.app.data.Prefs
import se.konsiliet.app.link.WatchListenerService
import se.konsiliet.app.ui.MainActivity

private const val TAG = "KonsilietAlerts"

object Channels {
    const val AKUT = "akut"
    const val AVVIKELSE = "avvikelse"
    const val KONSILIET = "konsiliet"
    const val LINK = "lank"
    const val SMS = "sms"
    const val ROROLSE = "rorelse"
    const val BRIEF = "brief"
    const val KNUFF = "knuff"
    const val TRANING = "traning"

    fun create(ctx: Context) {
        val nm = ctx.getSystemService(NotificationManager::class.java)
        nm.createNotificationChannels(listOf(
            NotificationChannel(AKUT, "Akut", NotificationManager.IMPORTANCE_HIGH).apply {
                description = "Akuta larm från vakten, t.ex. mycket hög puls i vila eller låg syremättnad"
                enableVibration(true)
                setBypassDnd(true)
            },
            NotificationChannel(AVVIKELSE, "Avvikelse", NotificationManager.IMPORTANCE_DEFAULT).apply {
                description = "Värden som avviker från din egen baslinje"
            },
            NotificationChannel(KONSILIET, "Supporttråden", NotificationManager.IMPORTANCE_DEFAULT).apply {
                description = "När en tråd startar och när trådstartaren markerar en lösning"
            },
            NotificationChannel(SMS, "Sms till anhöriga", NotificationManager.IMPORTANCE_HIGH).apply {
                description = "Bekräftelse när ett sms har skickats eller inte kunde skickas"
            },
            NotificationChannel(ROROLSE, "AFK för länge", NotificationManager.IMPORTANCE_DEFAULT).apply {
                description = "Påminnelser från stillasittandevakten. Skickas även till klockan."
            },
            NotificationChannel(BRIEF, "POST-skärmen", NotificationManager.IMPORTANCE_DEFAULT).apply {
                description = "Morgonens sammanfattning med headroom (återhämtning)"
            },
            NotificationChannel(KNUFF, "Knuffar: läggdags, pass, stress", NotificationManager.IMPORTANCE_DEFAULT).apply {
                description = "Läggdags, passdag och hög puls vid datorn. Högst det antal per dag du valt, aldrig under tysta timmar."
            },
            NotificationChannel(TRANING, "Efter passet", NotificationManager.IMPORTANCE_LOW).apply {
                description = "Sammanfattning efter ett träningspass och veckans siffror"
            },
            NotificationChannel(LINK, "Anslutning", NotificationManager.IMPORTANCE_MIN).apply {
                description = "Visar att länken mellan klocka, mobil och server är igång"
                setShowBadge(false)
            },
        ))
    }
}

/**
 * Gör händelser från servern till notiser och sköter sms-kedjan:
 * akut larm, användaren har N minuter på sig att trycka "Jag mår bra", annars går ett sms till
 * de kontakter användaren själv lagt in. Funktionen är avstängd tills den slås på i Inställningar.
 */
object Alerts {
    const val ACTION_DISMISS = "se.konsiliet.DISMISS"
    const val ACTION_SMS_DUE = "se.konsiliet.SMS_DUE"
    const val ACTION_KNUFF = "se.konsiliet.KNUFF"
    const val EXTRA_ALERT = "alert"
    /** Äldre händelser än så här (t.ex. historik vid första anslutningen) ger ingen notis. */
    private const val MAX_AGE_S = 2 * 3600

    private val hm = SimpleDateFormat("HH:mm", Locale("sv", "SE"))

    /** Hanterade id:n, persistenta. Se [EventGate]. */
    private fun handledIds(): List<Long> =
        Prefs.getString("handledEvents")?.split(',')?.mapNotNull { it.toLongOrNull() } ?: emptyList()

    fun onEvent(ctx: Context, ev: EventRow, replay: Boolean) {
        val act = synchronized(this) {
            val handled = handledIds()
            val ok = EventGate.shouldAct(ev.kind, replay, ev.id, ev.ts, System.currentTimeMillis() / 1000.0, handled)
            if (ok) Prefs.putString("handledEvents", EventGate.remember(handled, ev.id).joinToString(","))
            ok
        }
        if (!act) return
        if (System.currentTimeMillis() / 1000.0 - ev.ts > MAX_AGE_S) return
        val p = runCatching { JSONObject(ev.payload) }.getOrNull() ?: return
        when (ev.kind) {
            "alert.raise" -> {
                // Teamets "ta upp med vården" kommer redan i trådens egen notis. Bara akuta larm får en egen.
                if (p.optString("consult_id").isNotBlank() && p.optString("level") != "akut") return
                raise(ctx, SmsPolicy.Alert(
                    id = ev.id, ts = ev.ts, level = p.optString("level"), title = p.optString("title"),
                    body = p.optString("body"), rule = p.optString("rule").ifBlank { null },
                    consultId = p.optString("consult_id").ifBlank { null }))
            }
            // Avvikelser får ingen egen notis: tråden som startar av dem är notisen (en per tråd, uppdateras på plats).
            "vakt.anomaly" -> {}
            "consult.start" -> {
                val cid = p.optString("consult_id")
                val trig = p.optJSONObject("trigger")
                val tyst = trig?.optBoolean("tyst") == true
                if (trig?.optString("kind") == "anomaly") {
                    TradNotis.mark(cid, notified = true, tyst = false)
                    notify(ctx, Channels.KONSILIET, TradNotis.id(cid), "Vakten såg något: " + trig.optString("title"),
                        trig.optString("detail") + "\nTeamet tittar på det. Snabbsvar om några sekunder.", cid, onlyOnce = true)
                } else {
                    // Egen fråga: du vet redan att den startade. Veckans tråd är tyst om den inte hittar något.
                    TradNotis.mark(cid, notified = false, tyst = tyst)
                }
            }
            "consult.kort" -> {
                val cid = p.optString("consult_id")
                if (TradNotis.notified(cid)) {
                    val rader = p.optJSONArray("rader")
                    val text = "Snabbsvar: " + p.optString("bradska_text") + "." +
                        (if (rader != null) (0 until minOf(3, rader.length())).joinToString("") { "\n" + rader.optString(it) } else "")
                    notify(ctx, Channels.KONSILIET, TradNotis.id(cid), "Teamet tittar på det", text, cid, onlyOnce = true)
                }
            }
            "nudge.move", "nudge.stress", "nudge.sova", "nudge.pass" -> {
                val typ = p.optString("typ").ifBlank { if (ev.kind == "nudge.move") "afk" else ev.kind.removePrefix("nudge.") }
                knuff(ctx, ev.id.toInt(), typ, p)
                WatchListenerService.forwardNudge(ctx, p.optString("title"), p.optString("body"), typ)
            }
            "pass.klart" -> notify(ctx, Channels.TRANING, ev.id.toInt(), p.optString("title"), p.optString("body"), null)
            "vecka.summering" -> {
                val pass = p.optJSONObject("pass")
                notify(ctx, Channels.TRANING, ev.id.toInt(),
                    "Veckan: " + (pass?.let { "${it.optInt("pass")} av ${it.optInt("mal")} pass" } ?: "sammanfattning"),
                    p.optString("text"), null)
            }
            "brief.morgon" -> {
                val rubrik = p.optString("rubrik").ifBlank { "POST-skärmen" + p.optString("datum").let { if (it.isNotEmpty()) " $it" else "" } }
                val kort = p.optString("kort")
                val varfor = p.optString("varfor")
                notify(ctx, Channels.BRIEF, ev.id.toInt(), rubrik,
                    if (kort.isNotBlank()) kort + (if (varfor.isNotBlank()) ".\nVarför: $varfor." else "") else p.optString("text"), null)
            }
            "consult.verdict" -> {
                val cid = p.optString("consult_id")
                val v = p.optJSONObject("verdict")
                val b = v?.optString("bradska")
                val serious = b in setOf("ta_upp_med_varden", "kontakta_vard_nu")
                if (TradNotis.tyst(cid) && !serious) return
                val atg = v?.optJSONArray("atgarder")
                val forsta = if (atg != null && atg.length() > 0) "\nGör så här: " + atg.optString(0) else ""
                // Brådskande bedömningar skrivs sakligt, utan forumtermer.
                val titel = when (b) {
                    "kontakta_vard_nu" -> "Kontakta vården nu"
                    "ta_upp_med_varden" -> "Ta upp med vården (inte akut)"
                    else -> "Markerad som lösning"
                }
                notify(ctx, Channels.KONSILIET, TradNotis.id(cid), titel, v?.optString("sammanfattning").orEmpty() + forsta, cid,
                    onlyOnce = !serious && TradNotis.notified(cid))
            }
        }
    }

    /** En knuff med svarsknappar (snooze, inte nu, fokusläge, andas). Svaret går till servern. */
    private fun knuff(ctx: Context, id: Int, typ: String, p: JSONObject) {
        if (!canNotify(ctx)) return
        val b = NotificationCompat.Builder(ctx, if (typ == "afk") Channels.ROROLSE else Channels.KNUFF)
            .setSmallIcon(R.drawable.ic_stat)
            .setContentTitle(p.optString("title"))
            .setContentText(p.optString("body"))
            .setStyle(NotificationCompat.BigTextStyle().bigText(p.optString("body")))
            .setAutoCancel(true)
            .setCategory(NotificationCompat.CATEGORY_REMINDER)
            .setContentIntent(openIntent(ctx, null, id))
        val acts = p.optJSONArray("actions")
        if (acts != null) for (k in 0 until minOf(3, acts.length())) {
            val a = acts.optJSONObject(k) ?: continue
            val pi = PendingIntent.getBroadcast(ctx, id * 4 + k,
                Intent(ctx, AlertReceiver::class.java).setAction(ACTION_KNUFF)
                    .putExtra("notis", id).putExtra("typ", typ).putExtra("svar", a.optString("id")).putExtra("minuter", a.optInt("minuter")),
                PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
            b.addAction(0, a.optString("label"), pi)
        }
        if (TradNotis.tystaTimmar()) b.setSilent(true)
        runCatching { NotificationManagerCompat.from(ctx).notify(id, b.build()) }
    }

    fun svaraKnuff(ctx: Context, notisId: Int, typ: String, svar: String, minuter: Int) {
        NotificationManagerCompat.from(ctx).cancel(notisId)
        if (svar == "andas") WatchListenerService.startBreathing(ctx)
        kotlinx.coroutines.CoroutineScope(kotlinx.coroutines.Dispatchers.IO).launch {
            runCatching {
                se.konsiliet.app.net.Api.postJson("/api/knuff/svar", JSONObject().put("typ", typ).put("svar", svar)
                    .apply { if (minuter > 0) put("minuter", minuter) })
            }.onFailure { Log.w(TAG, "kunde inte skicka svaret på knuffen: ${it.message}") }
        }
    }

    private fun canNotify(ctx: Context) =
        Build.VERSION.SDK_INT < 33 ||
            ContextCompat.checkSelfPermission(ctx, Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED

    private fun openIntent(ctx: Context, consultId: String?, req: Int): PendingIntent {
        val i = Intent(ctx, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP)
        if (consultId != null) i.putExtra(MainActivity.EXTRA_CONSULT, consultId)
        return PendingIntent.getActivity(ctx, req, i, PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
    }

    private fun notify(ctx: Context, channel: String, id: Int, title: String, body: String, consultId: String?, onlyOnce: Boolean = false) {
        if (!canNotify(ctx)) return
        val n = NotificationCompat.Builder(ctx, channel)
            .setOnlyAlertOnce(onlyOnce)
            .setSilent(TradNotis.tystaTimmar())
            .setSmallIcon(R.drawable.ic_stat)
            .setContentTitle(title)
            .setContentText(body)
            .setStyle(NotificationCompat.BigTextStyle().bigText(body))
            .setAutoCancel(true)
            .setContentIntent(openIntent(ctx, consultId?.takeIf { it.isNotEmpty() }, id))
            .build()
        runCatching { NotificationManagerCompat.from(ctx).notify(id, n) }
    }

    fun raise(ctx: Context, a: SmsPolicy.Alert) {
        val nowMs = System.currentTimeMillis()
        // Historik som skickas om vid återanslutning: gamla larm ger varken notis eller sms.
        if (SmsPolicy.tooOld(a, nowMs / 1000.0)) return
        val consultId = a.consultId?.takeIf { it.isNotBlank() }
        if (a.level != "akut") {
            notify(ctx, Channels.AVVIKELSE, a.id.toInt(), a.title, a.body, consultId)
            return
        }
        // Klockan får ett eget meddelande med det långa akutmönstret, inte bara den speglade notisen.
        WatchListenerService.forwardAlert(ctx, a.id, a.title, a.body)
        val cfg = Prefs.config.value
        val smsArmed = cfg.smsEnabled && cfg.contacts.isNotEmpty() && SmsPolicy.triggersSms(a, nowMs / 1000.0)
        var chain: SmsPolicy.Chain? = null
        if (smsArmed) synchronized(this) {
            val before = loadChain()
            chain = SmsPolicy.add(before, a, cfg.smsDelayMin * 60_000L)
            saveChain(chain)
            // Alarmet sätts bara när kedjan skapas. Ett senare larm flyttar aldrig fristen.
            if (before == null) scheduleSms(ctx, chain!!.firstId, chain!!.due)
        }
        if (!canNotify(ctx)) return
        val dismiss = PendingIntent.getBroadcast(ctx, a.id.toInt(),
            Intent(ctx, AlertReceiver::class.java).setAction(ACTION_DISMISS).putExtra(EXTRA_ALERT, a.id),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
        val c = chain
        val text = when {
            c == null -> a.body
            c.due <= nowMs -> "${a.body}\n\nLarmet kom fram sent och fristen har redan gått ut. Sms skickas till " +
                cfg.contacts.joinToString { it.name } + "."
            else -> "${a.body}\n\nTryck \"Jag mår bra\" före ${hm.format(Date(c.due))}, annars skickas sms till " +
                cfg.contacts.joinToString { it.name } + "."
        }
        val n = NotificationCompat.Builder(ctx, Channels.AKUT)
            .setSmallIcon(R.drawable.ic_stat)
            .setContentTitle(a.title)
            .setContentText(a.body)
            .setStyle(NotificationCompat.BigTextStyle().bigText(text))
            .setPriority(NotificationCompat.PRIORITY_MAX)
            .setCategory(NotificationCompat.CATEGORY_ALARM)
            .setOngoing(c != null)
            .setAutoCancel(c == null)
            .setContentIntent(openIntent(ctx, consultId, a.id.toInt()))
            .addAction(0, if (c != null) "Jag mår bra, skicka inget sms" else "Jag mår bra", dismiss)
            .build()
        runCatching { NotificationManagerCompat.from(ctx).notify(a.id.toInt(), n) }
    }

    private fun smsIntent(ctx: Context, firstId: Long, flags: Int): PendingIntent? =
        PendingIntent.getBroadcast(ctx, firstId.toInt(),
            Intent(ctx, AlertReceiver::class.java).setAction(ACTION_SMS_DUE).putExtra(EXTRA_ALERT, firstId),
            PendingIntent.FLAG_IMMUTABLE or flags)

    private fun scheduleSms(ctx: Context, firstId: Long, due: Long) {
        val am = ctx.getSystemService(AlarmManager::class.java)
        val pi = smsIntent(ctx, firstId, PendingIntent.FLAG_UPDATE_CURRENT)!!
        // Exakt alarm även i Doze (USE_EXACT_ALARM), annars det närmaste systemet ger.
        if (Build.VERSION.SDK_INT < 31 || am.canScheduleExactAlarms()) {
            am.setExactAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, due, pi)
        } else {
            am.setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, due, pi)
        }
    }

    // Kedjan sparas i SharedPreferences så att den överlever processdöd och omstart.
    fun loadChain(): SmsPolicy.Chain? = Prefs.getString("smsChain")?.let { raw ->
        runCatching {
            val o = JSONObject(raw)
            val arr = o.getJSONArray("items")
            SmsPolicy.Chain(o.getLong("firstId"), o.getLong("due"), (0 until arr.length()).map {
                val i = arr.getJSONObject(it)
                SmsPolicy.Item(i.getLong("id"), i.optString("title"), i.optString("body"))
            })
        }.getOrNull()
    }

    private fun saveChain(c: SmsPolicy.Chain?) {
        if (c == null) { Prefs.putString("smsChain", null); return }
        val arr = org.json.JSONArray()
        c.items.forEach { arr.put(JSONObject().put("id", it.id).put("title", it.title).put("body", it.body)) }
        Prefs.putString("smsChain", JSONObject().put("firstId", c.firstId).put("due", c.due).put("items", arr).toString())
    }

    /** "Jag mår bra" på något av larmen i kedjan stoppar hela kedjan. */
    fun dismiss(ctx: Context, id: Long) {
        synchronized(this) {
            val c = loadChain()
            if (c != null && c.contains(id)) {
                saveChain(null)
                smsIntent(ctx, c.firstId, PendingIntent.FLAG_NO_CREATE)?.let { ctx.getSystemService(AlarmManager::class.java).cancel(it) }
                c.items.forEach { NotificationManagerCompat.from(ctx).cancel(it.id.toInt()) }
            }
        }
        NotificationManagerCompat.from(ctx).cancel(id.toInt())
    }

    /** Alarm försvinner vid omstart. En väntande kedja schemaläggs om med sin ursprungliga frist. */
    fun restorePendingSms(ctx: Context) {
        val c = loadChain() ?: return
        scheduleSms(ctx, c.firstId, maxOf(c.due, System.currentTimeMillis() + 5_000))
    }

    fun sendDueSms(ctx: Context, firstId: Long) {
        val c = synchronized(this) {
            val c = loadChain() ?: return
            if (c.firstId != firstId) return
            saveChain(null)
            c
        }
        val cfg = Prefs.config.value
        if (!cfg.smsEnabled || cfg.contacts.isEmpty()) return
        val granted = ContextCompat.checkSelfPermission(ctx, Manifest.permission.SEND_SMS) == PackageManager.PERMISSION_GRANTED
        val msg = SmsPolicy.message(c, cfg.smsDelayMin)
        val sent = mutableListOf<String>()
        val failed = mutableListOf<String>()
        if (granted) {
            val sms = ctx.getSystemService(SmsManager::class.java)
            for (k in cfg.contacts) {
                try {
                    sms.sendMultipartTextMessage(k.number, null, sms.divideMessage(msg), null, null)
                    sent += k.name
                } catch (e: Exception) {
                    Log.e(TAG, "sms till ${k.name} misslyckades", e); failed += k.name
                }
            }
        } else failed += cfg.contacts.map { it.name }
        c.items.forEach { NotificationManagerCompat.from(ctx).cancel(it.id.toInt()) }
        Log.i(TAG, "sms-kedja ${c.firstId} med ${c.items.size} larm: skickat till ${sent.size}, misslyckat ${failed.size}")
        val text = buildString {
            if (sent.isNotEmpty()) append("Sms skickat till ${sent.joinToString()} om ${c.items.size} larm. ")
            if (failed.isNotEmpty()) append("Kunde inte skicka till ${failed.joinToString()}" +
                (if (!granted) " (sms-behörighet saknas)." else "."))
        }
        if (canNotify(ctx)) {
            runCatching {
                NotificationManagerCompat.from(ctx).notify((firstId + 1_000_000).toInt(),
                    NotificationCompat.Builder(ctx, Channels.SMS).setSmallIcon(R.drawable.ic_stat)
                        .setContentTitle("Sms till anhöriga").setContentText(text)
                        .setStyle(NotificationCompat.BigTextStyle().bigText(text)).build())
            }
        }
    }
}

class AlertReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        val id = intent.getLongExtra(Alerts.EXTRA_ALERT, -1)
        when (intent.action) {
            Alerts.ACTION_DISMISS -> Alerts.dismiss(context, id)
            Alerts.ACTION_SMS_DUE -> Alerts.sendDueSms(context, id)
            Alerts.ACTION_KNUFF -> Alerts.svaraKnuff(context, intent.getIntExtra("notis", 0), intent.getStringExtra("typ").orEmpty(),
                intent.getStringExtra("svar").orEmpty(), intent.getIntExtra("minuter", 0))
        }
    }
}

/**
 * En notis per tråd: start (bara när vakten startade den), snabbsvaret och lösningen uppdaterar samma notis.
 * Kommer ihåg vilka trådar som är tysta (veckans genomgång) eller egna frågor.
 */
object TradNotis {
    fun id(cid: String): Int = 500_000 + (cid.hashCode() and 0x3fffff)

    private fun map(): JSONObject = Prefs.getString("tradNotis")?.let { runCatching { JSONObject(it) }.getOrNull() } ?: JSONObject()

    @Synchronized fun mark(cid: String, notified: Boolean, tyst: Boolean) {
        val m = map()
        m.put(cid, JSONObject().put("n", notified).put("t", tyst).put("at", System.currentTimeMillis()))
        // högst 30 trådar sparas
        val keys = m.keys().asSequence().toList().sortedBy { m.optJSONObject(it)?.optLong("at") ?: 0 }
        keys.dropLast(30).forEach { m.remove(it) }
        Prefs.putString("tradNotis", m.toString())
    }

    fun notified(cid: String) = map().optJSONObject(cid)?.optBoolean("n") == true
    fun tyst(cid: String) = map().optJSONObject(cid)?.optBoolean("t") == true

    /** Tysta timmar som servern har (hämtas av Idag-vyn). Notiser då visas men låter och vibrerar inte. Akuta larm undantas. */
    fun tystaTimmar(nowMs: Long = System.currentTimeMillis()): Boolean {
        val s = Prefs.getString("tystaTimmar") ?: "23:00-08:00"
        return runCatching {
            val (a, b) = s.split("-").map { x -> x.split(":").let { it[0].toInt() * 60 + it[1].toInt() } }
            val c = java.util.Calendar.getInstance().apply { timeInMillis = nowMs }
            val m = c.get(java.util.Calendar.HOUR_OF_DAY) * 60 + c.get(java.util.Calendar.MINUTE)
            if (a > b) m >= a || m < b else m in a until b
        }.getOrDefault(false)
    }
}
