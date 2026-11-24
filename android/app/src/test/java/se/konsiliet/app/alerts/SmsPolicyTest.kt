package se.konsiliet.app.alerts

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import se.konsiliet.app.alerts.SmsPolicy.Alert

class SmsPolicyTest {
    private val now = 1_800_000_000.0
    private val nowMs = (now * 1000).toLong()
    private val fem = 5 * 60_000L

    private fun vakt(id: Long, ts: Double = now, title: String = "Mycket hög puls i vila") =
        Alert(id, ts, "akut", title, "Medianpuls 150.", rule = "hr_rest_acute", consultId = null)

    @Test fun vaktensAkutlarmStartarSms() = assertTrue(SmsPolicy.triggersSms(vakt(1), now))

    @Test fun konsilietsLarmStartarAldrigSms() {
        val k = Alert(2, now, "akut", "Konsiliet har en bedömning", "...", rule = null, consultId = "abc")
        assertFalse(SmsPolicy.triggersSms(k, now))
        // Även om både rule och consult_id skulle finnas räcker consult_id för att stoppa.
        assertFalse(SmsPolicy.triggersSms(k.copy(rule = "x"), now))
    }

    @Test fun larmUtanRegelStartarInteSms() =
        assertFalse(SmsPolicy.triggersSms(vakt(3).copy(rule = null), now))

    @Test fun avvikelseStartarInteSms() =
        assertFalse(SmsPolicy.triggersSms(vakt(4).copy(level = "avvikelse"), now))

    @Test fun iEfterhandStartarInteSms() =
        assertFalse(SmsPolicy.triggersSms(vakt(5, title = "Mycket hög puls i vila (upptäckt i efterhand)"), now))

    @Test fun gamlaLarmVidAteranslutningIgnoreras() {
        assertTrue(SmsPolicy.tooOld(vakt(6, ts = now - 31 * 60), now))
        assertFalse(SmsPolicy.triggersSms(vakt(6, ts = now - 31 * 60), now))
        assertTrue(SmsPolicy.triggersSms(vakt(7, ts = now - 29 * 60), now))
    }

    @Test fun senareLarmFlyttarAldrigFristen() {
        val c1 = SmsPolicy.add(null, vakt(10), nowMs, fem)
        assertEquals(nowMs + fem, c1.due)
        // Fyra minuter senare kommer ett nytt akutlarm.
        val c2 = SmsPolicy.add(c1, vakt(11, title = "Lågt syremättnad"), nowMs + 4 * 60_000L, fem)
        assertEquals(c1.due, c2.due)
        assertEquals(10L, c2.firstId)
        assertEquals(listOf(10L, 11L), c2.items.map { it.id })
        val msg = SmsPolicy.message(c2, 5)
        assertTrue(msg.contains("Mycket hög puls i vila"))
        assertTrue(msg.contains("Lågt syremättnad"))
        assertTrue(msg.contains("2 larm"))
    }

    @Test fun sammaLarmTvaGangerLaggsInteTillIgen() {
        val c1 = SmsPolicy.add(null, vakt(20), nowMs, fem)
        assertEquals(c1, SmsPolicy.add(c1, vakt(20), nowMs + 1000, fem))
    }
}
