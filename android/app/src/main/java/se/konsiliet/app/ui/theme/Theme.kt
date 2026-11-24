package se.konsiliet.app.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.Immutable
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.ExperimentalTextApi
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.Font
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontVariation
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp
import se.konsiliet.app.R

/**
 * Färger som tokens. Lugn, mättnadsfattig palett: varmt papper och bläck i ljust läge,
 * grafit i mörkt. En enda accent (djup blågrön). Röd och bärnsten är reserverade för larm.
 */
@Immutable
data class Tokens(
    val bg: Color,
    val surface: Color,
    val ink: Color,
    val ink2: Color,
    val ink3: Color,
    val rule: Color,
    val grid: Color,
    val accent: Color,
    val trace: Color,
    val akut: Color,
    val avvikelse: Color,
    val ok: Color,
    val sleepDeep: Color,
    val sleepLight: Color,
    val sleepRem: Color,
    val sleepAwake: Color,
)

val LightTokens = Tokens(
    bg = Color(0xFFF4F4F1),
    surface = Color(0xFFFFFFFF),
    ink = Color(0xFF16191C),
    ink2 = Color(0xFF50575D),
    ink3 = Color(0xFF8A9096),
    rule = Color(0xFFDCDDD8),
    grid = Color(0xFFE9EAE6),
    accent = Color(0xFF1F5A69),
    trace = Color(0xFF1F5A69),
    akut = Color(0xFFB42318),
    avvikelse = Color(0xFFA15C07),
    ok = Color(0xFF2E6B47),
    sleepDeep = Color(0xFF1F3F5B),
    sleepLight = Color(0xFF6F93AE),
    sleepRem = Color(0xFF3F7F86),
    sleepAwake = Color(0xFFC9A66B),
)

val DarkTokens = Tokens(
    bg = Color(0xFF0F1113),
    surface = Color(0xFF16191C),
    ink = Color(0xFFE6E7E4),
    ink2 = Color(0xFFA2A8AD),
    ink3 = Color(0xFF6C7379),
    rule = Color(0xFF2A2F33),
    grid = Color(0xFF1F2427),
    accent = Color(0xFF7FB6C3),
    trace = Color(0xFF8CC3CF),
    akut = Color(0xFFF0645A),
    avvikelse = Color(0xFFE0A458),
    ok = Color(0xFF7DBB93),
    sleepDeep = Color(0xFF4C79A3),
    sleepLight = Color(0xFF8FAFC8),
    sleepRem = Color(0xFF5FA3AA),
    sleepAwake = Color(0xFFD8B77E),
)

val LocalTokens = staticCompositionLocalOf { LightTokens }

@OptIn(ExperimentalTextApi::class)
private fun inter(w: Int) = Font(R.font.inter_variable, FontWeight(w), variationSettings = FontVariation.Settings(FontVariation.weight(w)))

@OptIn(ExperimentalTextApi::class)
val Inter = FontFamily(inter(400), inter(500), inter(600), inter(700))

/** Siffror med tabulär bredd, så att kolumner och uppdaterade värden inte hoppar i sidled. */
const val TNUM = "tnum, cv11"

object Type {
    val display = TextStyle(fontFamily = Inter, fontWeight = FontWeight(500), fontSize = 52.sp, lineHeight = 56.sp,
        letterSpacing = (-1.2).sp, fontFeatureSettings = TNUM)
    val value = TextStyle(fontFamily = Inter, fontWeight = FontWeight(500), fontSize = 22.sp, lineHeight = 26.sp,
        letterSpacing = (-0.3).sp, fontFeatureSettings = TNUM)
    val title = TextStyle(fontFamily = Inter, fontWeight = FontWeight(600), fontSize = 20.sp, lineHeight = 26.sp, letterSpacing = (-0.2).sp)
    val heading = TextStyle(fontFamily = Inter, fontWeight = FontWeight(600), fontSize = 15.sp, lineHeight = 20.sp)
    val body = TextStyle(fontFamily = Inter, fontWeight = FontWeight(400), fontSize = 15.sp, lineHeight = 22.sp)
    val label = TextStyle(fontFamily = Inter, fontWeight = FontWeight(500), fontSize = 13.sp, lineHeight = 18.sp)
    val small = TextStyle(fontFamily = Inter, fontWeight = FontWeight(400), fontSize = 12.sp, lineHeight = 16.sp, fontFeatureSettings = TNUM)
    val axis = TextStyle(fontFamily = Inter, fontWeight = FontWeight(400), fontSize = 10.sp, lineHeight = 12.sp, fontFeatureSettings = TNUM)
}

@Composable
fun KonsilietTheme(content: @Composable () -> Unit) {
    val dark = isSystemInDarkTheme()
    val t = if (dark) DarkTokens else LightTokens
    val scheme = (if (dark) darkColorScheme() else lightColorScheme()).copy(
        primary = t.accent, onPrimary = t.surface, secondary = t.ink2, background = t.bg, onBackground = t.ink,
        surface = t.surface, onSurface = t.ink, onSurfaceVariant = t.ink2, surfaceVariant = t.grid,
        outline = t.rule, outlineVariant = t.rule, error = t.akut, surfaceContainer = t.surface,
        surfaceContainerHigh = t.surface, surfaceContainerHighest = t.grid, surfaceContainerLow = t.surface,
        primaryContainer = t.grid, onPrimaryContainer = t.ink,
    )
    val base = Typography()
    val typo = Typography(
        bodyLarge = Type.body, bodyMedium = Type.body.copy(fontSize = 14.sp), bodySmall = Type.small,
        titleLarge = Type.title, titleMedium = Type.heading, titleSmall = Type.label,
        labelLarge = Type.label, labelMedium = Type.label.copy(fontSize = 12.sp), labelSmall = Type.small,
        headlineSmall = base.headlineSmall.copy(fontFamily = Inter),
    )
    CompositionLocalProvider(LocalTokens provides t) {
        MaterialTheme(colorScheme = scheme, typography = typo, content = content)
    }
}
