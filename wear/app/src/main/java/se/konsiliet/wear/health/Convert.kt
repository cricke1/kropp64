package se.konsiliet.wear.health

import android.os.SystemClock
import androidx.health.services.client.data.DataPointContainer
import androidx.health.services.client.data.DataType
import androidx.health.services.client.data.HeartRateAccuracy
import androidx.health.services.client.data.UserActivityState
import java.time.Instant
import se.konsiliet.wear.data.Pending

/**
 * Översätter Health Services datapunkter till serverns mätvärdesnamn (se server/src/konsiliet/db.py).
 * Okända typer som klockan ändå erbjuder passivt skickas med prefixet hs_ i stället för att kastas,
 * så att servern kan börja använda dem utan ny klockversion.
 */
object Convert {

    fun metricName(type: DataType<*, *>): String = when (type) {
        DataType.HEART_RATE_BPM -> "hr"
        DataType.STEPS -> "steps"
        DataType.STEPS_DAILY -> "steps_daily"
        DataType.CALORIES -> "calories"
        DataType.CALORIES_DAILY -> "calories_daily"
        DataType.FLOORS -> "floors"
        DataType.FLOORS_DAILY -> "floors_daily"
        DataType.DISTANCE -> "distance"
        DataType.DISTANCE_DAILY -> "distance_daily"
        DataType.ELEVATION_GAIN -> "elevation_gain"
        else -> "hs_" + type.name.lowercase().replace(Regex("[^a-z0-9]+"), "_").trim('_')
    }

    /** Tidpunkten då klockan startade, för att räkna om "tid sedan boot" till väggklocka. */
    fun bootInstant(): Instant =
        Instant.ofEpochMilli(System.currentTimeMillis() - SystemClock.elapsedRealtime())

    private fun Instant.toSeconds(): Double = epochSecond + nano / 1e9

    fun fromContainer(c: DataPointContainer): List<Pending> {
        val boot = bootInstant()
        val out = ArrayList<Pending>()
        for (p in c.sampleDataPoints) {
            val v = (p.value as? Number)?.toDouble() ?: continue
            if (p.dataType == DataType.HEART_RATE_BPM) {
                if (v <= 0) continue
                val status = (p.accuracy as? HeartRateAccuracy)?.sensorStatus
                // Utan hudkontakt eller med opålitlig sensor är värdet inte en mätning.
                if (status == HeartRateAccuracy.SensorStatus.NO_CONTACT ||
                    status == HeartRateAccuracy.SensorStatus.UNRELIABLE
                ) continue
            }
            out += Pending(metric = metricName(p.dataType), ts = p.getTimeInstant(boot).toSeconds(), value = v)
        }
        for (p in c.intervalDataPoints) {
            val v = (p.value as? Number)?.toDouble() ?: continue
            out += Pending(metric = metricName(p.dataType), ts = p.getEndInstant(boot).toSeconds(), value = v)
        }
        return out
    }

    /** 0 okänt, 1 vardag (passiv), 2 träning, 3 sover. */
    fun activityCode(s: UserActivityState): Double = when (s) {
        UserActivityState.USER_ACTIVITY_PASSIVE -> 1.0
        UserActivityState.USER_ACTIVITY_EXERCISE -> 2.0
        UserActivityState.USER_ACTIVITY_ASLEEP -> 3.0
        else -> 0.0
    }

    fun seconds(i: Instant): Double = i.toSeconds()
}
