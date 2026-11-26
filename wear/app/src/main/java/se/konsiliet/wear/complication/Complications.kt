package se.konsiliet.wear.complication

import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.graphics.drawable.Icon
import androidx.wear.watchface.complications.data.ComplicationData
import androidx.wear.watchface.complications.data.ComplicationType
import androidx.wear.watchface.complications.data.LongTextComplicationData
import androidx.wear.watchface.complications.data.MonochromaticImage
import androidx.wear.watchface.complications.data.NoDataComplicationData
import androidx.wear.watchface.complications.data.PlainComplicationText
import androidx.wear.watchface.complications.data.RangedValueComplicationData
import androidx.wear.watchface.complications.data.ShortTextComplicationData
import androidx.wear.watchface.complications.datasource.ComplicationRequest
import androidx.wear.watchface.complications.datasource.SuspendingComplicationDataSourceService
import se.konsiliet.wear.R
import se.konsiliet.wear.data.PhoneStatus
import se.konsiliet.wear.data.Snapshot
import se.konsiliet.wear.data.Status
import se.konsiliet.wear.data.WatchState
import se.konsiliet.wear.data.Urgency
import se.konsiliet.wear.ui.MainActivity

private fun text(s: String) = PlainComplicationText.Builder(s).build()

private fun openApp(ctx: Context): PendingIntent =
    PendingIntent.getActivity(ctx, 0, Intent(ctx, MainActivity::class.java), PendingIntent.FLAG_IMMUTABLE)

private fun icon(ctx: Context, res: Int = R.drawable.ic_stat) =
    MonochromaticImage.Builder(Icon.createWithResource(ctx, res)).build()

/**
 * Återhämtningspoängen 0-100 som RANGED_VALUE (en båge eller stapel på urtavlan), med SHORT_TEXT
 * som reserv för urtavlor som bara har textplatser. Data kommer från mobilens cachade status och
 * skickas när den ändras (UPDATE_PERIOD_SECONDS = 0, Surfaces.update ber om ny hämtning).
 */
class RecoveryComplication : SuspendingComplicationDataSourceService() {

    override fun getPreviewData(type: ComplicationType): ComplicationData? =
        build(this, type, Snapshot(score = 72, receivedAt = 1))

    override suspend fun onComplicationRequest(request: ComplicationRequest): ComplicationData? =
        build(this, request.complicationType, PhoneStatus.snapshot.value)

    companion object {
        fun build(ctx: Context, type: ComplicationType, p: Snapshot): ComplicationData? {
            val score = p.score
            val desc = text(if (score == null) "Headroom okänt" else "Headroom $score av 100")
            if (score == null && type != ComplicationType.SHORT_TEXT) {
                return NoDataComplicationData(
                    ShortTextComplicationData.Builder(text("--"), desc).setMonochromaticImage(icon(ctx, R.drawable.ic_headroom)).setTapAction(openApp(ctx)).build())
            }
            return when (type) {
                ComplicationType.RANGED_VALUE ->
                    RangedValueComplicationData.Builder(score!!.toFloat(), 0f, 100f, desc)
                        .setText(text(score.toString()))
                        // Ingen titel: "Headroom" får inte plats i en rund plats. Mätarikonen och
                        // beskrivningen (skärmläsare) säger vad siffran är.
                        .setMonochromaticImage(icon(ctx, R.drawable.ic_headroom))
                        .setTapAction(openApp(ctx))
                        .build()
                ComplicationType.SHORT_TEXT ->
                    ShortTextComplicationData.Builder(text(score?.toString() ?: "--"), desc)
                        .setMonochromaticImage(icon(ctx, R.drawable.ic_headroom))
                        .setTapAction(openApp(ctx))
                        .build()
                else -> null
            }
        }
    }
}

/**
 * "Tråd pågår" eller brådskan i senaste "Markerad som lösning". SHORT_TEXT (högst 7 tecken) och LONG_TEXT.
 */
class ConsultComplication : SuspendingComplicationDataSourceService() {

    override fun getPreviewData(type: ComplicationType): ComplicationData? =
        build(this, type, Snapshot(urgency = "bevaka", receivedAt = 1))

    override suspend fun onComplicationRequest(request: ComplicationRequest): ComplicationData? =
        build(this, request.complicationType, PhoneStatus.snapshot.value)

    companion object {
        fun build(ctx: Context, type: ComplicationType, p: Snapshot): ComplicationData? {
            val short = when {
                !p.hasData -> "--"
                p.consultRunning -> "Pågår"
                else -> Urgency.short(p.urgency)
            }
            val long = when {
                !p.hasData -> "Tråden: ingen kontakt"
                p.consultRunning -> "Tråd pågår"
                p.urgency != null -> "Lösning: " + Urgency.label(p.urgency)
                else -> "Ingen tråd ännu"
            }
            val desc = text(long)
            return when (type) {
                ComplicationType.SHORT_TEXT ->
                    ShortTextComplicationData.Builder(text(short), desc)
                        .setMonochromaticImage(icon(ctx))
                        .setTapAction(openApp(ctx))
                        .build()
                ComplicationType.LONG_TEXT ->
                    LongTextComplicationData.Builder(text(long), desc)
                        .setMonochromaticImage(icon(ctx))
                        .setTapAction(openApp(ctx))
                        .build()
                else -> null
            }
        }
    }
}

/**
 * Klockfrekvensen (senaste pulsen klockan sett) som SHORT_TEXT med enfärgat hjärta, som klockans egen
 * pulskomplikation. Äldre än 30 minuter visas som "--". Uppdateras när passiv puls kommer
 * (Surfaces.updateHr) och annars var femte minut.
 */
class HeartRateComplication : SuspendingComplicationDataSourceService() {

    override fun getPreviewData(type: ComplicationType): ComplicationData? =
        build(this, type, Status(lastHr = 72.0, lastHrAt = System.currentTimeMillis()), System.currentTimeMillis())

    override suspend fun onComplicationRequest(request: ComplicationRequest): ComplicationData? =
        build(this, request.complicationType, WatchState.status.value, System.currentTimeMillis())

    companion object {
        fun build(ctx: Context, type: ComplicationType, w: Status, now: Long): ComplicationData? {
            if (type != ComplicationType.SHORT_TEXT) return null
            val bpm = w.lastHr?.takeIf { now - w.lastHrAt < 30 * 60_000L }?.let { "%.0f".format(it) }
            return ShortTextComplicationData.Builder(text(bpm ?: "--"),
                    text(if (bpm == null) "Klockfrekvens okänd" else "Klockfrekvens $bpm BPM"))
                .setTitle(text("BPM"))
                .setMonochromaticImage(icon(ctx, R.drawable.ic_heart))
                .setTapAction(openApp(ctx))
                .build()
        }
    }
}
