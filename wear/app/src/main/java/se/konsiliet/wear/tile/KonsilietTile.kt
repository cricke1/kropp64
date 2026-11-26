package se.konsiliet.wear.tile

import android.content.Context
import androidx.wear.protolayout.ActionBuilders
import androidx.wear.protolayout.DeviceParametersBuilders
import androidx.wear.protolayout.DimensionBuilders.dp
import androidx.wear.protolayout.DimensionBuilders.expand
import androidx.wear.protolayout.LayoutElementBuilders
import androidx.wear.protolayout.LayoutElementBuilders.Box
import androidx.wear.protolayout.LayoutElementBuilders.Column
import androidx.wear.protolayout.LayoutElementBuilders.LayoutElement
import androidx.wear.protolayout.LayoutElementBuilders.Spacer
import androidx.wear.protolayout.ModifiersBuilders
import androidx.wear.protolayout.ResourceBuilders
import androidx.wear.protolayout.TimelineBuilders
import androidx.wear.protolayout.expression.DynamicBuilders.DynamicFloat
import androidx.wear.protolayout.expression.DynamicBuilders.DynamicString
import androidx.wear.protolayout.expression.PlatformHealthSources
import androidx.wear.protolayout.material3.Typography
import androidx.wear.protolayout.material3.circularProgressIndicator
import androidx.wear.protolayout.material3.icon
import androidx.wear.protolayout.material3.materialScope
import androidx.wear.protolayout.material3.primaryLayout
import androidx.wear.protolayout.material3.text
import androidx.wear.protolayout.material3.textEdgeButton
import androidx.wear.protolayout.modifiers.LayoutModifier
import androidx.wear.protolayout.modifiers.clickable
import androidx.wear.protolayout.modifiers.contentDescription
import androidx.wear.protolayout.types.LayoutString
import androidx.wear.protolayout.types.argb
import androidx.wear.protolayout.types.layoutString
import androidx.wear.protolayout.types.stringLayoutConstraint
import androidx.wear.tiles.RequestBuilders
import androidx.wear.tiles.TileBuilders
import androidx.wear.tiles.TileService
import com.google.common.util.concurrent.Futures
import com.google.common.util.concurrent.ListenableFuture
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import se.konsiliet.wear.R
import se.konsiliet.wear.data.PhoneStatus
import se.konsiliet.wear.data.Snapshot
import se.konsiliet.wear.data.Status
import se.konsiliet.wear.data.Urgency
import se.konsiliet.wear.data.WatchState

private const val RES_VERSION = "2"
private const val HEART = "heart"

/** Samma färger som klockappen. Röd och bärnsten bara för brådska och gammal data. */
private const val INK = 0xFFE8ECEA.toInt()
private const val DIM = 0xFF8E9894.toInt()
private const val ACCENT = 0xFF8FC1CC.toInt()
private const val WARN = 0xFFE0A458.toInt()
private const val AKUT = 0xFFF0645A.toInt()

/**
 * Ruta "Kropp64": headroom (återhämtningspoängen, båge och siffra), klockfrekvens (puls), supporttrådens läge och när
 * mobilen senast synkade. Läser bara cachen (PhoneStatus, WatchState), så den svarar direkt och
 * kostar inget nätverk. Ritas om när ny status kommer (Surfaces.requestTile, uppmätt 0,05-2 s, högst
 * en gång per 20 s enligt systemets strypning), och klockfrekvensen uppdateras dynamiskt av rendraren.
 */
class KonsilietTile : TileService() {
    companion object { @Volatile private var lastRendered = 0L }

    override fun onTileRequest(requestParams: RequestBuilders.TileRequest): ListenableFuture<TileBuilders.Tile> {
        lastRendered = System.currentTimeMillis()
        // Mätpunkt för hur snabbt rutan ritas om efter ny status (se RESAN.md).
        android.util.Log.i("KonsilietTile", "onTileRequest, status mottagen för ${lastRendered - PhoneStatus.snapshot.value.receivedAt} ms sedan")
        val layout = TileLayout.build(this, requestParams.deviceConfiguration, PhoneStatus.snapshot.value,
            WatchState.status.value, System.currentTimeMillis())
        return Futures.immediateFuture(
            TileBuilders.Tile.Builder()
                .setResourcesVersion(RES_VERSION)
                // Ny status ritar om rutan direkt (Surfaces.requestTile). Färskhetsintervallet är bara ett
                // skyddsnät: en minut medan en tråd pågår, annars 15 minuter. Klockfrekvensen är dynamisk
                // och behöver ingen omritning.
                .setFreshnessIntervalMillis(if (PhoneStatus.snapshot.value.consultRunning) 60_000L else 15 * 60_000L)
                .setTileTimeline(TimelineBuilders.Timeline.fromLayoutElement(layout))
                .build()
        )
    }

    /**
     * Wear OS kan strunta i requestUpdate (strypning, skärmen av). Visas tilen med en rendering som är
     * äldre än senaste statusen eller pulsen ber vi om en ny direkt. Se RESAN.md.
     */
    @Deprecated("Ersätts av onRecentInteractionEventsAsync, men finns kvar i tiles 1.5")
    override fun onTileEnterEvent(requestParams: androidx.wear.tiles.EventBuilders.TileEnterEvent) {
        if (PhoneStatus.snapshot.value.receivedAt > lastRendered) {
            se.konsiliet.wear.link.Surfaces.requestTile(this)
        }
    }

    override fun onTileResourcesRequest(requestParams: RequestBuilders.ResourcesRequest): ListenableFuture<ResourceBuilders.Resources> =
        Futures.immediateFuture(ResourceBuilders.Resources.Builder().setVersion(RES_VERSION)
            .addIdToImageMapping(HEART, ResourceBuilders.ImageResource.Builder()
                .setAndroidResourceByResId(ResourceBuilders.AndroidImageResourceByResId.Builder()
                    .setResourceId(R.drawable.ic_heart).build())
                .build())
            .build())
}

object TileLayout {
    private val hm = SimpleDateFormat("HH:mm", Locale("sv", "SE"))

    /** "nyss", "12 min sedan" eller klockslag. */
    fun ago(ms: Long, now: Long): String {
        val s = (now - ms) / 1000
        return when {
            s < 90 -> "nyss"
            s < 3600 -> "${s / 60} min sedan"
            else -> hm.format(Date(ms))
        }
    }

    fun consultLine(p: Snapshot): Pair<String, Int> = when {
        !p.hasData -> "Tråden: okänd" to DIM
        p.consultRunning -> "Tråd pågår" to ACCENT
        p.urgency == "kontakta_vard_nu" -> Urgency.label(p.urgency) to AKUT
        p.urgency == "ta_upp_med_varden" -> Urgency.label(p.urgency) to WARN
        p.urgency != null -> "Lösning: " + Urgency.label(p.urgency) to INK
        else -> "Ingen tråd ännu" to DIM
    }

    fun syncLine(p: Snapshot, now: Long): Pair<String, Int> = when {
        !p.hasData -> "Väntar på mobilen" to WARN
        now - p.receivedAt > 2 * 3600_000L -> "Ej synkad sedan ${hm.format(Date(p.receivedAt))}" to WARN
        // Klockslag, inte "nyss": en tile kan visas långt efter att den ritades.
        else -> "Synkad ${hm.format(Date(p.receivedAt))}" to DIM
    }

    private fun launch(pkg: String, startaPass: Boolean): ActionBuilders.LaunchAction =
        ActionBuilders.LaunchAction.Builder()
            .setAndroidActivity(ActionBuilders.AndroidActivity.Builder()
                .setPackageName(pkg)
                .setClassName("se.konsiliet.wear.ui.MainActivity")
                .apply { if (startaPass) addKeyToExtraMapping("starta_pass", ActionBuilders.AndroidBooleanExtra.Builder().setValue(true).build()) }
                .build())
            .build()

    /**
     * Material 3-ruta i samma stil som Pixel/Fitbit-rutorna: Headroom som en båge längs kanten (öppen
     * nedtill för knappen), poängen stort i mitten, dagens svar, klockfrekvensen (dynamisk, uppdateras av
     * rendraren utan ny hämtning) och supporttrådens läge. Kantknappen startar dagens planerade pass.
     */
    fun build(ctx: Context, device: DeviceParametersBuilders.DeviceParameters, p: Snapshot, w: Status, now: Long): LayoutElement =
        materialScope(ctx, device, allowDynamicTheme = true) {
            val score = p.score
            val hrFresh = w.lastHr != null && now - w.lastHrAt < 30 * 60_000L
            val (cText, cColor) = consultLine(p)
            val (sText, sColor) = syncLine(p, now)
            val cs = colorScheme
            // Statusraden: tråden om något händer där, annars synken (gul om den är gammal).
            val (rad, radFarg) = if (p.hasData && (p.consultRunning || p.urgency != null) && sColor != WARN) cText to cColor else sText to sColor
            val open = clickable(launch(ctx.packageName, false), "oppna")
            val start = clickable(launch(ctx.packageName, !w.exerciseActive), "starta")
            val desc = "Kropp64. Headroom ${score ?: "okänt"} av 100. ${p.idag?.let { it.rubrik + ": " + it.plan + "." } ?: ""} $cText. $sText."

            val bpm = PlatformHealthSources.heartRateBpm()
                .format(DynamicFloat.FloatFormatter.Builder().setMaxFractionDigits(0).setGroupingUsed(false).build())
                .concat(DynamicString.constant(" BPM"))
            val puls = LayoutElementBuilders.Row.Builder()
                .setVerticalAlignment(LayoutElementBuilders.VERTICAL_ALIGN_CENTER)
                .addContent(icon(HEART, width = dp(14f), height = dp(14f), tintColor = cs.error))
                .addContent(Spacer.Builder().setWidth(dp(4f)).build())
                .addContent(text(LayoutString(if (hrFresh) "%.0f BPM".format(w.lastHr) else "-- BPM", bpm,
                    stringLayoutConstraint("000 BPM")), typography = Typography.LABEL_MEDIUM, color = cs.onSurface))
                .build()

            val mitt = Column.Builder()
                .setWidth(expand()).setHeight(expand())
                .setHorizontalAlignment(LayoutElementBuilders.HORIZONTAL_ALIGN_CENTER)
                .addContent(text((score?.toString() ?: "--").layoutString, typography = Typography.NUMERAL_MEDIUM,
                    color = if (score == null) cs.onSurfaceVariant else cs.onSurface))
                // Dagens svar: träna, ta det lugnt eller vila.
                .addContent(text((p.idag?.rubrik ?: if (score == null) (p.scoreNote ?: "ingen poäng") else "av 100").layoutString,
                    typography = Typography.LABEL_MEDIUM, maxLines = 1,
                    color = if (p.idag?.beslut == "vila") WARN.argb else if (p.idag != null) cs.primary else cs.onSurfaceVariant))
                .addContent(Spacer.Builder().setHeight(dp(4f)).build())
                .addContent(puls)
                .addContent(Spacer.Builder().setHeight(dp(2f)).build())
                .addContent(text(rad.layoutString, typography = Typography.LABEL_SMALL, maxLines = 1,
                    color = if (radFarg == DIM) cs.onSurfaceVariant else radFarg.argb))
                .build()

            val layout = primaryLayout(
                titleSlot = { text("Headroom".layoutString) },
                mainSlot = { mitt },
                bottomSlot = {
                    textEdgeButton(onClick = start, labelContent = { text((if (w.exerciseActive) "Visa pass" else "Starta pass").layoutString) })
                },
                onClick = open,
            )
            // Headroom av 100 som en båge längs kanten, från klockan sju till fem.
            val arc = circularProgressIndicator(
                staticProgress = (score ?: 0).coerceIn(0, 100) / 100f,
                startAngleDegrees = -140f, endAngleDegrees = 140f,
                modifier = LayoutModifier.contentDescription("Headroom ${score ?: "okänt"} av 100"),
                size = expand(),
            )
            Box.Builder()
                .setWidth(expand()).setHeight(expand())
                .setModifiers(ModifiersBuilders.Modifiers.Builder()
                    .setSemantics(ModifiersBuilders.Semantics.Builder().setContentDescription(desc).build()).build())
                .addContent(Box.Builder().setWidth(expand()).setHeight(expand())
                    .setModifiers(ModifiersBuilders.Modifiers.Builder()
                        .setPadding(ModifiersBuilders.Padding.Builder().setAll(dp(3f)).build()).build())
                    .addContent(arc).build())
                .addContent(layout)
                .build()
        }
}
