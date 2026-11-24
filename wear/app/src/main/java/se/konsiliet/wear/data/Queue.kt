package se.konsiliet.wear.data

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
 * Lokal kö på klockan. Varje mätpunkt ligger kvar här tills mobilen har kvitterat att den
 * sparat den i sin egen kö. Unikt index på (metric, ts) gör att samma punkt aldrig köas två gånger.
 */
@Entity(tableName = "pending", indices = [Index(value = ["metric", "ts"], unique = true)])
data class Pending(
    @PrimaryKey(autoGenerate = true) val id: Long = 0,
    val metric: String,
    /** Unix-sekunder UTC, med decimaler. */
    val ts: Double,
    val value: Double,
)

@Dao
interface PendingDao {
    @Insert(onConflict = OnConflictStrategy.IGNORE)
    suspend fun insert(rows: List<Pending>): List<Long>

    /** Äldsta först. Id är strikt växande, så ett intervall [första, sista] är exakt det som skickades. */
    @Query("SELECT * FROM pending ORDER BY id LIMIT :n")
    suspend fun oldest(n: Int): List<Pending>

    @Query("DELETE FROM pending WHERE id BETWEEN :from AND :to")
    suspend fun deleteRange(from: Long, to: Long): Int

    @Query("SELECT COUNT(*) FROM pending")
    suspend fun count(): Int

    @Query("SELECT COUNT(*) FROM pending")
    fun countFlow(): Flow<Int>

    /** Skydd mot att klockans lagring fylls om mobilen är borta i veckor. */
    @Query("DELETE FROM pending WHERE ts < :before")
    suspend fun pruneOlderThan(before: Double): Int
}

@Database(entities = [Pending::class], version = 1, exportSchema = true)
abstract class QueueDb : RoomDatabase() {
    abstract fun pending(): PendingDao

    companion object {
        @Volatile private var instance: QueueDb? = null

        fun get(ctx: Context): QueueDb = instance ?: synchronized(this) {
            instance ?: Room.databaseBuilder(ctx.applicationContext, QueueDb::class.java, "queue.db")
                .build().also { instance = it }
        }
    }
}
