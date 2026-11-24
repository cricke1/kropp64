package se.konsiliet.wear.alerts

import android.Manifest
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.media.AudioAttributes
import android.os.Build
import android.os.VibrationAttributes
import android.os.VibrationEffect
import android.os.Vibrator
import android.os.VibratorManager
import android.util.Log
import androidx.core.app.NotificationCompat
import se.konsiliet.wear.R
import se.konsiliet.wear.ui.MainActivity

/**
 * Tre vibrationsmönster som ska gå att skilja åt utan att titta på klockan:
 *
 *  AKUT     tre långa, starka stötar, två gånger (ca 3,6 s). Går igenom Stör ej.
 *  RORELSE  två korta, mjuka knackningar (ca 0,4 s).
 *  KLART    en mellanlång stöt följd av en kort (ca 0,6 s), som en kvittens.
 *
 * AKUT spelas här med Vibrator och USAGE_ALARM (styrd amplitud, går igenom Stör ej), och akutkanalen
 * har ingen egen vibration. RORELSE och KLART ligger som mönster på sina notiskanaler och spelas av
 * systemet när notisen visas. Wear OS släppte inte igenom en app-egen vibration med USAGE_NOTIFICATION
 * ("ignored_app_ops" i dumpsys vibrator_manager, se RESAN.md), och via kanalen följer de dessutom
 * Stör ej och användarens kanalinställningar.
 */
enum class Pattern(val timings: LongArray, val amplitudes: IntArray) {
    AKUT(
        longArrayOf(0, 500, 150, 500, 150, 500, 600, 500, 150, 500, 150, 500),
        intArrayOf(0, 255, 0, 255, 0, 255, 0, 255, 0, 255, 0, 255),
    ),
    RORELSE(
        longArrayOf(0, 90, 160, 90),
        intArrayOf(0, 110, 0, 110),
    ),
    KLART(
        longArrayOf(0, 280, 140, 70),
        intArrayOf(0, 180, 0, 140),
    ),
}

object Haptics {
    private const val TAG = "KonsilietHaptics"
    const val CH_AKUT = "akut_v2"
    const val CH_RORELSE = "rorelse_v3"
    const val CH_KLART = "klart_v2"

    /** Senast spelade mönster, för test (debugbryggan läser det). */
    @Volatile var last: Pattern? = null

    fun channels(ctx: Context) {
        val nm = ctx.getSystemService(NotificationManager::class.java)
        // Kanalinställningar kan inte ändras i efterhand, så ändrade mönster kräver nya kanal-id.
        listOf("rorelse", "rorelse_v2", "konsilium_klart").forEach { nm.deleteNotificationChannel(it) }
        nm.createNotificationChannels(listOf(
            NotificationChannel(CH_AKUT, "Akut larm", NotificationManager.IMPORTANCE_HIGH).apply {
                description = "Akuta larm från vakten. Lång, stark vibration."
                enableVibration(false); setBypassDnd(true)
            },
            NotificationChannel(CH_RORELSE, "Rörelse", NotificationManager.IMPORTANCE_DEFAULT).apply {
                description = "AFK för länge: påminnelser från stillasittandevakten. Två korta knackningar."
                enableVibration(true); vibrationPattern = Pattern.RORELSE.timings
            },
            NotificationChannel(CH_KLART, "Tråden löst", NotificationManager.IMPORTANCE_DEFAULT).apply {
                description = "När supporttråden har en markerad lösning. En stöt och en kort."
                enableVibration(true); vibrationPattern = Pattern.KLART.timings
            },
        ))
    }

    fun play(ctx: Context, p: Pattern) {
        // Påminnelser och kvittenser respekterar Stör ej och teaterläge. Akuta larm gör det inte.
        if (p != Pattern.AKUT) {
            val filter = ctx.getSystemService(NotificationManager::class.java).currentInterruptionFilter
            if (filter != NotificationManager.INTERRUPTION_FILTER_ALL && filter != NotificationManager.INTERRUPTION_FILTER_UNKNOWN) {
                Log.i(TAG, "hoppar över $p, Stör ej är på")
                return
            }
        }
        val vib: Vibrator = if (Build.VERSION.SDK_INT >= 31)
            ctx.getSystemService(VibratorManager::class.java).defaultVibrator
        else @Suppress("DEPRECATION") ctx.getSystemService(Vibrator::class.java)
        if (!vib.hasVibrator()) return
        val effect = if (vib.hasAmplitudeControl()) VibrationEffect.createWaveform(p.timings, p.amplitudes, -1)
        else VibrationEffect.createWaveform(p.timings, -1)
        if (Build.VERSION.SDK_INT >= 33) {
            val usage = if (p == Pattern.AKUT) VibrationAttributes.USAGE_ALARM else VibrationAttributes.USAGE_NOTIFICATION
            vib.vibrate(effect, VibrationAttributes.createForUsage(usage))
        } else {
            @Suppress("DEPRECATION")
            vib.vibrate(effect, AudioAttributes.Builder().setUsage(
                if (p == Pattern.AKUT) AudioAttributes.USAGE_ALARM else AudioAttributes.USAGE_NOTIFICATION).build())
        }
        last = p
        Log.i(TAG, "vibration $p")
    }

    /** Notis plus mönster. Notisen öppnar klockappen. */
    fun notify(ctx: Context, p: Pattern, id: Int, title: String, body: String) {
        channels(ctx)
        if (p == Pattern.AKUT) play(ctx, p) else last = p
        if (Build.VERSION.SDK_INT >= 33 &&
            ctx.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) return
        val open = PendingIntent.getActivity(ctx, id, Intent(ctx, MainActivity::class.java),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
        val (channel, category) = when (p) {
            Pattern.AKUT -> CH_AKUT to NotificationCompat.CATEGORY_ALARM
            Pattern.RORELSE -> CH_RORELSE to NotificationCompat.CATEGORY_REMINDER
            Pattern.KLART -> CH_KLART to NotificationCompat.CATEGORY_STATUS
        }
        val n = NotificationCompat.Builder(ctx, channel)
            .setSmallIcon(R.drawable.ic_stat)
            .setContentTitle(title)
            .setContentText(body)
            .setStyle(NotificationCompat.BigTextStyle().bigText(body))
            .setAutoCancel(true)
            .setCategory(category)
            .setPriority(if (p == Pattern.AKUT) NotificationCompat.PRIORITY_MAX else NotificationCompat.PRIORITY_DEFAULT)
            .setContentIntent(open)
            .build()
        ctx.getSystemService(NotificationManager::class.java).notify(id, n)
    }
}
