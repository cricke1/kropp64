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

/** Systemets typsnitt (Roboto, eller tillverkarens), som i andra Android-appar. */
val Inter: FontFamily = FontFamily.Default

/** Siffror med tabulär bredd, så att kolumner och uppdaterade värden inte hoppar i sidled. */
const val TNUM = "tnum, cv11"

object Type {
    val display = TextStyle(fontFamily = Inter, fontWeight = FontWeight(500), fontSize = 52.sp, lineHeight = 56.sp,
        letterSpacing = (-1.2).sp, fontFeatureSettings = TNUM)
    val value = TextStyle(fontFamily = Inter, fontWeight = FontWeight(500), fontSize = 22.sp, lineHeight = 26.sp,
        letterSpacing = (-0.3).sp, fontFeatureSettings = TNUM)
    val title = TextStyle(fontFamily = Inter, fontWeight = FontWeight(400), fontSize = 28.sp, lineHeight = 36.sp)
    val heading = TextStyle(fontFamily = Inter, fontWeight = FontWeight(500), fontSize = 16.sp, lineHeight = 24.sp, letterSpacing = 0.15.sp)
    val body = TextStyle(fontFamily = Inter, fontWeight = FontWeight(400), fontSize = 16.sp, lineHeight = 24.sp, letterSpacing = 0.5.sp)
    val label = TextStyle(fontFamily = Inter, fontWeight = FontWeight(500), fontSize = 13.sp, lineHeight = 18.sp)
    val small = TextStyle(fontFamily = Inter, fontWeight = FontWeight(400), fontSize = 12.sp, lineHeight = 16.sp, fontFeatureSettings = TNUM)
    val axis = TextStyle(fontFamily = Inter, fontWeight = FontWeight(400), fontSize = 10.sp, lineHeight = 12.sp, fontFeatureSettings = TNUM)
}

/**
 * Material You: färgerna kommer från bakgrundsbilden (Android 12+), annars Material-standard.
 * Appens egna tokens härleds ur samma färgschema, så att diagram och tabeller följer temat.
 * Röd, bärnsten och grön är fasta, eftersom de betyder larm, avvikelse och ok.
 */
@Composable
fun KonsilietTheme(content: @Composable () -> Unit) {
    val dark = isSystemInDarkTheme()
    val ctx = androidx.compose.ui.platform.LocalContext.current
    val scheme = when {
        android.os.Build.VERSION.SDK_INT >= 31 && dark -> androidx.compose.material3.dynamicDarkColorScheme(ctx)
        android.os.Build.VERSION.SDK_INT >= 31 -> androidx.compose.material3.dynamicLightColorScheme(ctx)
        dark -> darkColorScheme()
        else -> lightColorScheme()
    }
    val fast = if (dark) DarkTokens else LightTokens
    val t = fast.copy(
        bg = scheme.surface, surface = scheme.surfaceContainer, ink = scheme.onSurface, ink2 = scheme.onSurfaceVariant,
        ink3 = scheme.onSurfaceVariant.copy(alpha = 0.72f), rule = scheme.outlineVariant, grid = scheme.surfaceContainerHighest,
        accent = scheme.primary, trace = scheme.primary,
    )
    CompositionLocalProvider(LocalTokens provides t) {
        MaterialTheme(colorScheme = scheme.copy(error = fast.akut), typography = Typography(), content = content)
    }
}
