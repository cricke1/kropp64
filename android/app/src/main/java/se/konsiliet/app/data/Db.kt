package se.konsiliet.app.data

import android.content.Context
import androidx.room.Dao
import androidx.room.Database
import androidx.room.Entity
import androidx.room.Index
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.PrimaryKey
import androidx.room.Query
import androidx.room.Room
import androidx.room.RoomDatabase
import kotlinx.coroutines.flow.Flow

/**
 * Mobilens kö och lokala spegel. En rad lämnar aldrig tabellen förrän servern svarat 2xx,
 * och även då ligger den kvar markerad som uppladdad i sju dygn så att appen kan visa
 * dagens värden utan nät. Unikt index på (metric, ts, source) ger avduplicering.
 */
@Entity(
    tableName = "sample",
    indices = [
        Index(value = ["metric", "ts", "source"], unique = true),
        Index(value = ["state", "source", "id"]),
        Index(value = ["metric", "ts"]),
    ],
)
data class SampleRow(
    @PrimaryKey(autoGenerate = true) val id: Long = 0,
    val metric: String,
    val ts: Double,
    val value: Double,
    val source: String,
    /** 0 väntar, 1 uppladdad, 2 avvisad av servern (sparas för felsökning, skickas inte igen). */
    val state: Int = 0,
)

@Entity(tableName = "sleep")
data class SleepRow(
    @PrimaryKey val id: String,
    val start: Double,
    val end: Double,
    /** JSON-lista med {start, end, stage}. */
    val stages: String,
    val source: String,
    val state: Int = 0,
)

/** Cache av serverns händelser (från /ws och /api/events). Id är serverns id. */
@Entity(tableName = "event", indices = [Index("ts"), Index("kind")])
data class EventRow(
    @PrimaryKey val id: Long,
    val ts: Double,
    val kind: String,
    val payload: String,
)

data class MetricPoint(val ts: Double, val value: Double)
data class Latest(val ts: Double, val value: Double, val source: String)

@Dao
interface SampleDao {
    @Insert(onConflict = OnConflictStrategy.IGNORE)
    suspend fun insert(rows: List<SampleRow>): List<Long>

    /** Nästa batch: äldsta väntande raderna från en och samma källa (servern tar en källa per batch). */
    @Query(
        """SELECT * FROM sample WHERE state = 0 AND source =
           (SELECT source FROM sample WHERE state = 0 ORDER BY id LIMIT 1)
           ORDER BY id LIMIT :n"""
    )
    suspend fun nextBatch(n: Int): List<SampleRow>

    @Query("UPDATE sample SET state = :state WHERE state = 0 AND source = :source AND id BETWEEN :from AND :to")
    suspend fun mark(source: String, from: Long, to: Long, state: Int): Int

    @Query("UPDATE sample SET state = 2 WHERE id = :id")
    suspend fun reject(id: Long)

    @Query("SELECT COUNT(*) FROM sample WHERE state = 0")
    fun pendingFlow(): Flow<Int>

    @Query("SELECT COUNT(*) FROM sample WHERE state = 0")
    suspend fun pending(): Int

    @Query("SELECT COUNT(*) FROM sample WHERE state = 2")
    fun rejectedFlow(): Flow<Int>

    @Query("DELETE FROM sample WHERE state != 0 AND ts < :before")
    suspend fun prune(before: Double): Int

    @Query("SELECT ts, value FROM sample WHERE metric = :metric AND ts >= :from ORDER BY ts")
    fun series(metric: String, from: Double): Flow<List<MetricPoint>>

    @Query("SELECT ts, value, source FROM sample WHERE metric = :metric ORDER BY ts DESC LIMIT 1")
    fun latest(metric: String): Flow<Latest?>

    @Query("SELECT COALESCE(SUM(value), 0) FROM sample WHERE metric = :metric AND source = :source AND ts >= :from")
    fun sumSince(metric: String, source: String, from: Double): Flow<Double>

    @Query("SELECT DISTINCT source FROM sample WHERE metric = :metric AND ts >= :from")
    fun sourcesSince(metric: String, from: Double): Flow<List<String>>
}

@Dao
interface SleepDao {
    /** REPLACE: Health Connect kan uppdatera ett pass i efterhand (t.ex. när faser räknats om). */
    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsert(rows: List<SleepRow>)

    @Query("SELECT * FROM sleep WHERE state = 0 ORDER BY start LIMIT :n")
    suspend fun pending(n: Int): List<SleepRow>

    @Query("UPDATE sleep SET state = :state WHERE id = :id")
    suspend fun mark(id: String, state: Int)

    @Query("SELECT COUNT(*) FROM sleep WHERE state = 0")
    fun pendingFlow(): Flow<Int>

    @Query("SELECT * FROM sleep WHERE `end` >= :from ORDER BY start DESC LIMIT 1")
    fun lastSince(from: Double): Flow<SleepRow?>
}

@Dao
interface EventDao {
    @Insert(onConflict = OnConflictStrategy.IGNORE)
    suspend fun insert(rows: List<EventRow>): List<Long>

    @Query("SELECT * FROM event ORDER BY id DESC LIMIT :n")
    fun recent(n: Int): Flow<List<EventRow>>

    @Query("SELECT * FROM event WHERE payload LIKE '%' || :consultId || '%' ORDER BY id")
    fun forConsult(consultId: String): Flow<List<EventRow>>

    @Query("SELECT MAX(id) FROM event")
    suspend fun maxId(): Long?
}

@Database(entities = [SampleRow::class, SleepRow::class, EventRow::class], version = 1, exportSchema = true)
abstract class KonsilietDb : RoomDatabase() {
    abstract fun samples(): SampleDao
    abstract fun sleep(): SleepDao
    abstract fun events(): EventDao

    companion object {
        @Volatile private var instance: KonsilietDb? = null

        fun get(ctx: Context): KonsilietDb = instance ?: synchronized(this) {
            instance ?: Room.databaseBuilder(ctx.applicationContext, KonsilietDb::class.java, "konsiliet.db")
                .build().also { instance = it }
        }
    }
}
