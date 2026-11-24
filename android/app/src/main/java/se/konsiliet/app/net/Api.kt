package se.konsiliet.app.net

import java.io.IOException
import java.util.concurrent.TimeUnit
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONArray
import org.json.JSONObject
import se.konsiliet.app.data.Prefs

/** HTTP-fel med statuskod, så att uppladdningen kan skilja på "försök igen" och "fel i datat". */
class HttpError(val code: Int, msg: String) : IOException("HTTP $code: $msg")

object Api {
    private val JSON = "application/json; charset=utf-8".toMediaType()

    val http: OkHttpClient = OkHttpClient.Builder()
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(60, TimeUnit.SECONDS)
        .writeTimeout(60, TimeUnit.SECONDS)
        .retryOnConnectionFailure(true)
        // Håller WebSocket vid liv genom NAT och Cloudflare, och upptäcker döda anslutningar.
        .pingInterval(25, TimeUnit.SECONDS)
        .build()

    fun base(): String = Prefs.config.value.serverUrl.trimEnd('/')

    fun request(path: String): Request.Builder {
        // Ingen inbyggd adress: utan inställd server görs inga anrop alls (kön ligger kvar).
        if (base().isBlank()) throw IOException("Ingen serveradress angiven")
        val b = Request.Builder().url(base() + path)
        val token = Prefs.config.value.deviceToken
        if (token.isNotEmpty()) b.header("X-Device-Token", token)
        return b
    }

    private suspend fun call(req: Request): String = withContext(Dispatchers.IO) {
        http.newCall(req).execute().use { r ->
            val body = r.body?.string().orEmpty()
            if (!r.isSuccessful) throw HttpError(r.code, body.take(300))
            body
        }
    }

    suspend fun postJson(path: String, body: JSONObject): JSONObject =
        JSONObject(call(request(path).post(body.toString().toRequestBody(JSON)).build()))

    suspend fun getObject(path: String): JSONObject = JSONObject(call(request(path).get().build()))
    suspend fun getArray(path: String): JSONArray = JSONArray(call(request(path).get().build()))

    suspend fun health(): Boolean = runCatching { getObject("/api/health").optBoolean("ok") }.getOrDefault(false)

    /** Testar en adress innan den sparas (första start). */
    suspend fun healthAt(base: String, token: String): Boolean = runCatching {
        val b = Request.Builder().url(base.trimEnd('/') + "/api/health")
        if (token.isNotBlank()) b.header("X-Device-Token", token.trim())
        JSONObject(call(b.get().build())).optBoolean("ok")
    }.getOrDefault(false)

    fun wsUrl(): String {
        val token = Prefs.config.value.deviceToken
        val q = if (token.isNotEmpty()) "?token=" + java.net.URLEncoder.encode(token, "UTF-8") else ""
        return base().replaceFirst("https://", "wss://").replaceFirst("http://", "ws://") + "/ws" + q
    }
}
