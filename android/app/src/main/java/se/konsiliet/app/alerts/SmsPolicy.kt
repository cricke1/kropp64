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

    /**
     * Ny kedja om ingen väntar, annars samma kedja med samma frist och larmet tillagt.
     * Fristen räknas från larmets egen tid (ts), inte från när mobilen tog emot det, så att ett
     * larm som kom fram först efter ett avbrott inte får längre frist.
     */
    fun add(chain: Chain?, a: Alert, delayMs: Long): Chain {
        val item = Item(a.id, a.title, a.body)
        if (chain == null) return Chain(a.id, (a.ts * 1000).toLong() + delayMs, listOf(item))
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

/**
 * Avgör om appen ska agera (notis, vibration, sms-kedja) på en händelse från /ws.
 *
 *  - Varje händelse har ett unikt id från servern. Id:n som redan hanterats sparas (de senaste [KEEP])
 *    och hanteras aldrig igen, oavsett om de kommer live eller som omskickad historik.
 *  - Live-händelser hanteras.
 *  - Omskickad historik (replay=true) hanteras bara om det är alert.raise som är yngre än 5 minuter
 *    räknat på händelsens egen tid. Det täcker ett kort avbrott i anslutningen utan att gamla larm
 *    väcker kedjan igen. Allt annat i historiken visas bara i listorna.
 */
object EventGate {
    const val REPLAY_MAX_AGE_S = 5 * 60.0
    const val KEEP = 500

    fun shouldAct(kind: String, replay: Boolean, id: Long, ts: Double, nowS: Double, handled: Collection<Long>): Boolean {
        if (id in handled) return false
        if (!replay) return true
        return kind == "alert.raise" && nowS - ts <= REPLAY_MAX_AGE_S
    }

    fun remember(handled: List<Long>, id: Long): List<Long> =
        if (id in handled) handled else (handled + id).takeLast(KEEP)
}
