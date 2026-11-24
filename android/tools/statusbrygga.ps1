# Testbrygga mobilemulator -> klockemulator via adb (ersätter Data Layer när parkoppling saknas).
# Mobilen hämtar sammanfattningen och lägger den i Data Layer som vanligt, och skriver samma JSON
# till files/status.json. Klockan lämnar den till samma kod som tar emot /konsiliet/status.
# Med -Meddelande flyttas också senaste meddelandet till klockan (påminnelse, akut larm).
param([switch]$Meddelande)
$adb = "C:\Users\crick\Android\Sdk\platform-tools\adb.exe"
& $adb -s emulator-5554 shell am broadcast -a se.konsiliet.debug.EXPORT_STATUS -n se.konsiliet/se.konsiliet.app.debug.DebugBridge | Out-Null
Start-Sleep -Milliseconds 1500
$files = @("status.json")
if ($Meddelande) { $files += "message.json" }
foreach ($f in $files) {
  & $adb -s emulator-5554 shell "run-as se.konsiliet cat files/$f > /data/local/tmp/$f"
  & $adb -s emulator-5554 pull /data/local/tmp/$f C:\Users\crick\_k_$f | Out-Null
  & $adb -s emulator-5556 push C:\Users\crick\_k_$f /data/local/tmp/$f | Out-Null
  & $adb -s emulator-5556 shell "chmod 644 /data/local/tmp/$f; run-as se.konsiliet cp /data/local/tmp/$f files/$f"
}
"status: " + (Get-Content C:\Users\crick\_k_status.json -Raw)
& $adb -s emulator-5556 shell am broadcast -a se.konsiliet.debug.STATUS -n se.konsiliet/se.konsiliet.wear.debug.DebugBridge | Out-Null
if ($Meddelande) {
  Start-Sleep -Milliseconds 500
  & $adb -s emulator-5556 shell am broadcast -a se.konsiliet.debug.MESSAGE -n se.konsiliet/se.konsiliet.wear.debug.DebugBridge | Out-Null
}
