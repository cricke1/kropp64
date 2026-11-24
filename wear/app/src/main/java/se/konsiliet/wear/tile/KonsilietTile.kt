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
 * kostar inget nätverk. Uppdateras när ny status kommer (Surfaces.update), högst var femte minut
 * för pulsen, när den visas och är äldre än senaste statusen, och annars var femte minut.
 */
class KonsilietTile : TileService() {
    companion object { @Volatile private var lastRendered = 0L }

    override fun onTileRequest(requestParams: RequestBuilders.TileRequest): ListenableFuture<TileBuilders.Tile> {
        lastRendered = System.currentTimeMillis()
        val layout = TileLayout.build(PhoneStatus.snapshot.value, WatchState.status.value, System.currentTimeMillis(),
            packageName)
        return Futures.immediateFuture(
            TileBuilders.Tile.Builder()
                .setResourcesVersion(RES_VERSION)
                .setFreshnessIntervalMillis(5 * 60_000L)
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
        val newest = maxOf(PhoneStatus.snapshot.value.receivedAt, WatchState.status.value.lastHrAt)
        if (newest > lastRendered || System.currentTimeMillis() - lastRendered > 5 * 60_000L) {
            getUpdater(this).requestUpdate(KonsilietTile::class.java)
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
            .addContent(gap(6f))
            .addContent(text(if (hrFresh) "Klockfrekvens %.0f BPM".format(w.lastHr) else "Klockfrekvens --", 14f, INK))
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
                    .setContentDescription("Kropp64. Headroom ${score ?: "okänt"} av 100. $cText. $sText.").build())
                .build())
            // Ringen visar poängen av 100, med start klockan tolv.
            .addContent(ring(360f, TRACK))
        if (score != null && score > 0) box.addContent(ring(360f * score.coerceIn(0, 100) / 100f, ACCENT))
        return box.addContent(center).build()
    }
}
