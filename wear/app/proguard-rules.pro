# Kropp64 på klockan. De flesta bibliotek (Room, WorkManager, Health Services, Play Services Wearable,
# tiles, komplikationer, coroutines) har egna consumer-regler. Här ligger bara det som läses via
# reflektion eller över processgränser och som vi inte vill riskera.

# Komponenter i manifestet behålls av AAPT. Room: databasens _Impl hittas via namnet.
-keep class * extends androidx.room.RoomDatabase { <init>(); }
-keep class se.konsiliet.wear.data.Pending { *; }

# WorkManager skapar arbetare via klassnamnet som sparats i sin databas.
-keep class * extends androidx.work.ListenableWorker { <init>(android.content.Context, androidx.work.WorkerParameters); }

# Tile-uppdateringen binder direkt till hemskärmens AIDL-tjänst (Surfaces.requestTile).
-keep class androidx.wear.tiles.TileUpdateRequesterService** { *; }
-keep class androidx.wear.tiles.TileUpdateRequestData { *; }

# Protobuf-lite i ProtoLayout och Health Services läser fältnamn via reflektion.
-keepclassmembers class * extends androidx.wear.protolayout.protobuf.GeneratedMessageLite { <fields>; }
-keepclassmembers class * extends androidx.health.services.client.proto.** { <fields>; }
-keep class androidx.health.services.client.proto.** { *; }

# Enum-namn används i loggar och debugbryggan (Pattern.valueOf).
-keepclassmembers enum se.konsiliet.wear.** { public static **[] values(); public static ** valueOf(java.lang.String); }

# Kraschrapporter med radnummer.
-keepattributes SourceFile,LineNumberTable
-renamesourcefileattribute SourceFile
