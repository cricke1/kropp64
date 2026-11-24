package se.konsiliet.app.alerts

/**
 * Reglerna för sms-kedjan, utan Android-beroenden så att de går att enhetstesta.
 *
 *  - Bara vaktens regler får starta sms: alert.raise med nivå "akut" och fältet `rule`.
 *    Konsiliets bedömningar (har `consult_id`) ger notis men aldrig sms: en språkmodell ska aldrig
 *    kunna skicka sms till anhöriga.
 *  - Larm "upptäckt i efterhand" ger aldrig sms (servern sätter dem till avvikelse, men vi kontrollerar ändå).
 *  - Larm äldre än 30 minuter ignoreras helt. Servern skickar om historiken vid varje WebSocket-anslutning.
 *  - Fristen sätts av det FÖRSTA olösta akutlarmet och flyttas aldrig fram. Senare larm läggs till i
 *    samma sms-text.
 */
object SmsPolicy {
    const val MAX_ALERT_AGE_S = 30 * 60.0

    data class Alert(
        val id: Long,
        val ts: Double,
        val level: String,
        val title: String,
        val body: String,
        val rule: String?,
        val consultId: String?,
    )

    data class Item(val id: Long, val title: String, val body: String)

    /** En väntande sms-kedja. `firstId` äger alarmet, `due` ändras aldrig efter att kedjan skapats. */
    data class Chain(val firstId: Long, val due: Long, val items: List<Item>) {
        fun contains(id: Long) = items.any { it.id == id }
    }

    fun tooOld(a: Alert, nowS: Double): Boolean = nowS - a.ts > MAX_ALERT_AGE_S

    fun triggersSms(a: Alert, nowS: Double): Boolean =
        a.level == "akut" &&
            !a.rule.isNullOrBlank() &&
            a.consultId.isNullOrBlank() &&
            !a.title.contains("i efterhand") &&
            !tooOld(a, nowS)

    /** Ny kedja om ingen väntar, annars samma kedja med samma frist och larmet tillagt. */
    fun add(chain: Chain?, a: Alert, nowMs: Long, delayMs: Long): Chain {
        val item = Item(a.id, a.title, a.body)
        if (chain == null) return Chain(a.id, nowMs + delayMs, listOf(item))
        if (chain.contains(a.id)) return chain
        return chain.copy(items = chain.items + item)
    }

    fun message(chain: Chain, delayMin: Int): String {
        val parts = chain.items.joinToString(" ") { "${it.title}. ${it.body}".trim() }
        val extra = if (chain.items.size > 1) " (${chain.items.size} larm)" else ""
        return "Konsiliet (automatiskt larm$extra): $parts Larmet bekräftades inte i mobilen inom $delayMin min. " +
            "Ring och hör hur det är."
    }
}
