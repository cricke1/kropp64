package se.konsiliet.app.link

import android.content.Context
import android.util.Log
import com.google.android.gms.wearable.PutDataMapRequest
import com.google.android.gms.wearable.Wearable
import kotlinx.coroutines.tasks.await
import kotlinx.coroutines.withTimeoutOrNull
import se.konsiliet.app.data.Prefs

/**
 * Mobil till klocka: sammanfattningen (återhämtning, konsiliets läge) som ett dataobjekt på
 * `/konsiliet/status` med DataClient.
 *
 * Varför DataClient och inte MessageClient: ett dataobjekt är ett tillstånd, inte en händelse.
 * Data Layer sparar det på båda sidor och synkar det när klockan kommer tillbaka inom räckhåll,
 * så en ändring medan klockan var frånkopplad kommer fram ändå, och bara det senaste läget skickas.
 * putDataItem lyckas även utan anslutning (objektet köas lokalt). Klockan ignorerar äldre underlag
 * än det den redan har (fältet synkad), så en sen leverans skriver aldrig över nyare data.
 */
object WatchSync {
    const val PATH = "/konsiliet/status"
    private const val TAG = "KonsilietWatchSync"

    suspend fun push(ctx: Context, json: String) {
        // Sparas också för debugbryggan, som flyttar exakt detta till klockemulatorn med adb.
        Prefs.putString("watchStatus", json)
        val r = runCatching {
            val req = PutDataMapRequest.create(PATH).apply { dataMap.putString("status", json) }
                .asPutDataRequest()
                .setUrgent()
            withTimeoutOrNull(10_000) { Wearable.getDataClient(ctx).putDataItem(req).await() }
        }
        r.onFailure { Log.d(TAG, "kunde inte lägga status i Data Layer: ${it.message}") }
            .onSuccess { Log.d(TAG, if (it == null) "Data Layer svarade inte inom 10 s" else "status lagd: ${it.uri}") }
    }
}
