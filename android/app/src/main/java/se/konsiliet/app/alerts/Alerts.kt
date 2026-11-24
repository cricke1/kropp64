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
            NotificationChannel(KONSILIET, "Konsiliet", NotificationManager.IMPORTANCE_DEFAULT).apply {
                description = "När läkarteamet sammanträder och när bedömningen är klar"
            },
            NotificationChannel(SMS, "Sms till anhöriga", NotificationManager.IMPORTANCE_HIGH).apply {
                description = "Bekräftelse när ett sms har skickats eller inte kunde skickas"
            },
            NotificationChannel(ROROLSE, "Rörelse", NotificationManager.IMPORTANCE_DEFAULT).apply {
                description = "Påminnelser från stillasittandevakten. Skickas även till klockan."
            },
            NotificationChannel(BRIEF, "Morgonbrief", NotificationManager.IMPORTANCE_DEFAULT).apply {
                description = "Morgonens sammanfattning med återhämtning"
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
    const val EXTRA_ALERT = "alert"
    /** Äldre händelser än så här (t.ex. historik vid första anslutningen) ger ingen notis. */
    private const val MAX_AGE_S = 2 * 3600

    private val hm = SimpleDateFormat("HH:mm", Locale("sv", "SE"))

    fun onEvent(ctx: Context, ev: EventRow) {
        val last = Prefs.getLong("lastNotifiedEvent", -1)
        if (ev.id <= last) return
        Prefs.putLong("lastNotifiedEvent", ev.id)
        if (System.currentTimeMillis() / 1000.0 - ev.ts > MAX_AGE_S) return
        val p = runCatching { JSONObject(ev.payload) }.getOrNull() ?: return
        when (ev.kind) {
            "alert.raise" -> raise(ctx, ev.id, p.optString("level"), p.optString("title"), p.optString("body"))
            "vakt.anomaly" -> if (p.optString("level") == "avvikelse") {
                notify(ctx, Channels.AVVIKELSE, ev.id.toInt(), p.optString("title"), p.optString("detail"), consultId = null)
            }
            "consult.start" -> {
                val trig = p.optJSONObject("trigger")
                val what = trig?.optString("title")?.takeIf { it.isNotEmpty() }
                    ?: trig?.optString("question")?.takeIf { it.isNotEmpty() } ?: "Manuell fråga"
                notify(ctx, Channels.KONSILIET, ev.id.toInt(), "Konsiliet sammanträder", what, p.optString("consult_id"))
            }
            "nudge.move" -> {
                notify(ctx, Channels.ROROLSE, ev.id.toInt(), p.optString("title"), p.optString("body"), null)
                WatchListenerService.forwardNudge(ctx, p.optString("title"), p.optString("body"))
            }
            "brief.morgon" -> notify(ctx, Channels.BRIEF, ev.id.toInt(),
                "Morgonbrief" + p.optString("datum").let { if (it.isNotEmpty()) " $it" else "" },
                p.optString("text"), null)
            "consult.verdict" -> {
                val v = p.optJSONObject("verdict")
                notify(ctx, Channels.KONSILIET, ev.id.toInt(), "Bedömningen är klar",
                    v?.optString("sammanfattning").orEmpty(), p.optString("consult_id"))
            }
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

    private fun notify(ctx: Context, channel: String, id: Int, title: String, body: String, consultId: String?) {
        if (!canNotify(ctx)) return
        val n = NotificationCompat.Builder(ctx, channel)
            .setSmallIcon(R.drawable.ic_stat)
            .setContentTitle(title)
            .setContentText(body)
            .setStyle(NotificationCompat.BigTextStyle().bigText(body))
            .setAutoCancel(true)
            .setContentIntent(openIntent(ctx, consultId?.takeIf { it.isNotEmpty() }, id))
            .build()
        runCatching { NotificationManagerCompat.from(ctx).notify(id, n) }
    }

    fun raise(ctx: Context, id: Long, level: String, title: String, body: String) {
        if (level != "akut") {
            notify(ctx, Channels.AVVIKELSE, id.toInt(), title, body, null)
            return
        }
        val cfg = Prefs.config.value
        val smsArmed = cfg.smsEnabled && cfg.contacts.isNotEmpty()
        val due = System.currentTimeMillis() + cfg.smsDelayMin * 60_000L
        if (smsArmed) {
            Prefs.putString("pendingSms", JSONObject().put("id", id).put("title", title).put("body", body)
                .put("due", due).toString())
            scheduleSms(ctx, id, due)
        }
        if (!canNotify(ctx)) return
        val dismiss = PendingIntent.getBroadcast(ctx, id.toInt(),
            Intent(ctx, AlertReceiver::class.java).setAction(ACTION_DISMISS).putExtra(EXTRA_ALERT, id),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
        val text = if (smsArmed) "$body\n\nTryck \"Jag mår bra\" före ${hm.format(Date(due))}, annars skickas sms till " +
            cfg.contacts.joinToString { it.name } + "." else body
        val n = NotificationCompat.Builder(ctx, Channels.AKUT)
            .setSmallIcon(R.drawable.ic_stat)
            .setContentTitle(title)
            .setContentText(body)
            .setStyle(NotificationCompat.BigTextStyle().bigText(text))
            .setPriority(NotificationCompat.PRIORITY_MAX)
            .setCategory(NotificationCompat.CATEGORY_ALARM)
            .setOngoing(smsArmed)
            .setAutoCancel(!smsArmed)
            .setContentIntent(openIntent(ctx, null, id.toInt()))
            .addAction(0, if (smsArmed) "Jag mår bra, skicka inget sms" else "Jag mår bra", dismiss)
            .build()
        runCatching { NotificationManagerCompat.from(ctx).notify(id.toInt(), n) }
    }

    private fun scheduleSms(ctx: Context, id: Long, due: Long) {
        val am = ctx.getSystemService(AlarmManager::class.java)
        val pi = PendingIntent.getBroadcast(ctx, id.toInt(),
            Intent(ctx, AlertReceiver::class.java).setAction(ACTION_SMS_DUE).putExtra(EXTRA_ALERT, id),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
        // Exakt alarm även i Doze om användaren tillåtit det, annars det närmaste systemet ger.
        if (Build.VERSION.SDK_INT < 31 || am.canScheduleExactAlarms()) {
            am.setExactAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, due, pi)
        } else {
            am.setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, due, pi)
        }
    }

    fun pendingSms(): JSONObject? = Prefs.getString("pendingSms")?.let { runCatching { JSONObject(it) }.getOrNull() }

    fun dismiss(ctx: Context, id: Long) {
        val p = pendingSms()
        if (p != null && p.optLong("id") == id) Prefs.putString("pendingSms", null)
        val pi = PendingIntent.getBroadcast(ctx, id.toInt(),
            Intent(ctx, AlertReceiver::class.java).setAction(ACTION_SMS_DUE).putExtra(EXTRA_ALERT, id),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_NO_CREATE)
        if (pi != null) ctx.getSystemService(AlarmManager::class.java).cancel(pi)
        NotificationManagerCompat.from(ctx).cancel(id.toInt())
    }

    /** Alarm försvinner vid omstart. Ett larm som väntade på sms schemaläggs om (eller skickas direkt). */
    fun restorePendingSms(ctx: Context) {
        val p = pendingSms() ?: return
        scheduleSms(ctx, p.optLong("id"), maxOf(p.optLong("due"), System.currentTimeMillis() + 5_000))
    }

    fun sendDueSms(ctx: Context, id: Long) {
        val p = pendingSms() ?: return
        if (p.optLong("id") != id) return
        Prefs.putString("pendingSms", null)
        val cfg = Prefs.config.value
        if (!cfg.smsEnabled || cfg.contacts.isEmpty()) return
        val granted = ContextCompat.checkSelfPermission(ctx, Manifest.permission.SEND_SMS) == PackageManager.PERMISSION_GRANTED
        val msg = "Konsiliet (automatiskt larm): ${p.optString("title")}. ${p.optString("body")} " +
            "Larmet bekräftades inte i mobilen inom ${cfg.smsDelayMin} min. Ring och hör hur det är."
        val sent = mutableListOf<String>()
        val failed = mutableListOf<String>()
        if (granted) {
            val sms = ctx.getSystemService(SmsManager::class.java)
            for (c in cfg.contacts) {
                try {
                    sms.sendMultipartTextMessage(c.number, null, sms.divideMessage(msg), null, null)
                    sent += c.name
                } catch (e: Exception) {
                    Log.e(TAG, "sms till ${c.name} misslyckades", e); failed += c.name
                }
            }
        } else failed += cfg.contacts.map { it.name }
        NotificationManagerCompat.from(ctx).cancel(id.toInt())
        val text = buildString {
            if (sent.isNotEmpty()) append("Sms skickat till ${sent.joinToString()}. ")
            if (failed.isNotEmpty()) append("Kunde inte skicka till ${failed.joinToString()}" +
                (if (!granted) " (sms-behörighet saknas)." else "."))
        }
        if (canNotify(ctx)) {
            runCatching {
                NotificationManagerCompat.from(ctx).notify((id + 1_000_000).toInt(),
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
        }
    }
}
