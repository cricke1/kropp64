package se.konsiliet.wear.tile

import androidx.wear.protolayout.ActionBuilders
import androidx.wear.protolayout.ColorBuilders.argb
import androidx.wear.protolayout.DimensionBuilders.degrees
import androidx.wear.protolayout.DimensionBuilders.dp
import androidx.wear.protolayout.DimensionBuilders.expand
import androidx.wear.protolayout.DimensionBuilders.sp
import androidx.wear.protolayout.LayoutElementBuilders
import androidx.wear.protolayout.LayoutElementBuilders.Arc
import androidx.wear.protolayout.LayoutElementBuilders.ArcLine
import androidx.wear.protolayout.LayoutElementBuilders.Box
import androidx.wear.protolayout.LayoutElementBuilders.Column
import androidx.wear.protolayout.LayoutElementBuilders.FontStyle
import androidx.wear.protolayout.LayoutElementBuilders.LayoutElement
import androidx.wear.protolayout.LayoutElementBuilders.Spacer
import androidx.wear.protolayout.LayoutElementBuilders.Text
import androidx.wear.protolayout.ModifiersBuilders
import androidx.wear.protolayout.ResourceBuilders
import androidx.wear.protolayout.TimelineBuilders
import androidx.wear.protolayout.TypeBuilders
import androidx.wear.protolayout.expression.DynamicBuilders.DynamicFloat
import androidx.wear.protolayout.expression.DynamicBuilders.DynamicString
import androidx.wear.protolayout.expression.PlatformHealthSources
import androidx.wear.tiles.RequestBuilders
import androidx.wear.tiles.TileBuilders
import androidx.wear.tiles.TileService
import com.google.common.util.concurrent.Futures
import com.google.common.util.concurrent.ListenableFuture
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import se.konsiliet.wear.data.PhoneStatus
import se.konsiliet.wear.data.Snapshot
import se.konsiliet.wear.data.Status
import se.konsiliet.wear.data.Urgency
import se.konsiliet.wear.data.WatchState

private const val RES_VERSION = "1"

/** Samma färger som klockappen. Röd och bärnsten bara för brådska och gammal data. */
private const val INK = 0xFFE8ECEA.toInt()
private const val DIM = 0xFF8E9894.toInt()
private const val TRACK = 0xFF2A3134.toInt()
private const val ACCENT = 0xFF8FC1CC.toInt()
private const val WARN = 0xFFE0A458.toInt()
private const val AKUT = 0xFFF0645A.toInt()

/**
 * Ruta "Kropp64": headroom (återhämtningspoängen, ring och siffra), klockfrekvens (puls), supporttrådens läge och när
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
        val layout = TileLayout.build(PhoneStatus.snapshot.value, WatchState.status.value, System.currentTimeMillis(),
            packageName)
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
        Futures.immediateFuture(ResourceBuilders.Resources.Builder().setVersion(RES_VERSION).build())
}

object TileLayout {
    private val hm = SimpleDateFormat("HH:mm", Locale("sv", "SE"))

    private fun text(s: String, size: Float, color: Int, weight: Int = LayoutElementBuilders.FONT_WEIGHT_NORMAL): LayoutElement =
        Text.Builder().setText(s).setMaxLines(1)
            .setFontStyle(FontStyle.Builder().setSize(sp(size)).setColor(argb(color)).setWeight(weight).build())
            .build()

    /**
     * Klockfrekvensen som dynamiskt värde (PlatformHealthSources.heartRateBpm): rendraren uppdaterar
     * siffran själv från klockans pulssensor, utan att rutan hämtas om. Det statiska värdet (senaste
     * pulsen klockappen sett) visas om plattformen inte kan ge puls.
     */
    private fun heartRate(fallback: String): LayoutElement {
        val bpm = PlatformHealthSources.heartRateBpm()
            .format(DynamicFloat.FloatFormatter.Builder().setMaxFractionDigits(0).setGroupingUsed(false).build())
        val dyn = DynamicString.constant("Klockfrekvens ").concat(bpm).concat(DynamicString.constant(" BPM"))
        return Text.Builder()
            .setText(TypeBuilders.StringProp.Builder(fallback).setDynamicValue(dyn).build())
            .setLayoutConstraintsForDynamicText(TypeBuilders.StringLayoutConstraint.Builder("Klockfrekvens 000 BPM").build())
            .setMaxLines(1)
            .setFontStyle(FontStyle.Builder().setSize(sp(14f)).setColor(argb(INK)).build())
            .build()
    }

    private fun gap(h: Float): LayoutElement = Spacer.Builder().setHeight(dp(h)).build()

    private fun ring(lengthDeg: Float, color: Int): LayoutElement =
        Arc.Builder()
            .setAnchorAngle(degrees(0f))
            .setAnchorType(LayoutElementBuilders.ARC_ANCHOR_START)
            .addContent(ArcLine.Builder().setLength(degrees(lengthDeg)).setThickness(dp(5f)).setColor(argb(color)).build())
            .build()

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

    fun build(p: Snapshot, w: Status, now: Long, pkg: String): LayoutElement {
        val score = p.score
        val hrFresh = w.lastHr != null && now - w.lastHrAt < 30 * 60_000L
        val (cText, cColor) = consultLine(p)
        val (sText, sColor) = syncLine(p, now)

        val center = Column.Builder()
            .setHorizontalAlignment(LayoutElementBuilders.HORIZONTAL_ALIGN_CENTER)
            .addContent(text("Headroom", 12f, DIM))
            .addContent(text(score?.toString() ?: "--", 40f, if (score == null) DIM else INK, LayoutElementBuilders.FONT_WEIGHT_MEDIUM))
            .addContent(text(if (score == null) (p.scoreNote ?: "ingen poäng") else "av 100", 11f, DIM))
            .addContent(gap(4f))
            // Dagens svar: träna, ta det lugnt eller vila.
            .addContent(text(p.idag?.rubrik ?: "", 13f, if (p.idag?.beslut == "vila") WARN else ACCENT, LayoutElementBuilders.FONT_WEIGHT_MEDIUM))
            .addContent(gap(4f))
            .addContent(heartRate(if (hrFresh) "Klockfrekvens %.0f BPM".format(w.lastHr) else "Klockfrekvens --"))
            .addContent(gap(4f))
            .addContent(text(cText, 12f, cColor, LayoutElementBuilders.FONT_WEIGHT_MEDIUM))
            .addContent(gap(2f))
            .addContent(text(sText, 11f, sColor))
            .build()

        val open = ModifiersBuilders.Clickable.Builder()
            .setId("oppna")
            .setOnClick(ActionBuilders.LaunchAction.Builder()
                .setAndroidActivity(ActionBuilders.AndroidActivity.Builder()
                    .setPackageName(pkg)
                    .setClassName("se.konsiliet.wear.ui.MainActivity")
                    .build())
                .build())
            .build()

        val box = Box.Builder()
            .setWidth(expand()).setHeight(expand())
            .setHorizontalAlignment(LayoutElementBuilders.HORIZONTAL_ALIGN_CENTER)
            .setVerticalAlignment(LayoutElementBuilders.VERTICAL_ALIGN_CENTER)
            .setModifiers(ModifiersBuilders.Modifiers.Builder().setClickable(open)
                .setSemantics(ModifiersBuilders.Semantics.Builder()
                    .setContentDescription("Kropp64. Headroom ${score ?: "okänt"} av 100. ${p.idag?.let { it.rubrik + ": " + it.plan + "." } ?: ""} $cText. $sText.").build())
                .build())
            // Ringen visar poängen av 100, med start klockan tolv.
            .addContent(ring(360f, TRACK))
        if (score != null && score > 0) box.addContent(ring(360f * score.coerceIn(0, 100) / 100f, ACCENT))
        return box.addContent(center).build()
    }
}
