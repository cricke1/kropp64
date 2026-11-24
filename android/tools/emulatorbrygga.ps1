# Testbrygga klockemulator -> mobilemulator via adb (ersätter Bluetooth när parkoppling saknas).
# Samma batchformat och samma kvittensregel som MessageClient-vägen.
$adb = "C:\Users\crick\Android\Sdk\platform-tools\adb.exe"
$total = 0
for ($i = 0; $i -lt 50; $i++) {
  & $adb -s emulator-5556 shell am broadcast -a se.konsiliet.debug.EXPORT -n se.konsiliet/se.konsiliet.wear.debug.DebugBridge | Out-Null
  Start-Sleep -Milliseconds 800
  $range = (& $adb -s emulator-5556 shell run-as se.konsiliet cat files/batch.range) -join ""
  if (-not $range.Trim()) { break }
  & $adb -s emulator-5556 shell "run-as se.konsiliet cat files/batch.json > /data/local/tmp/batch.json"
  & $adb -s emulator-5556 pull /data/local/tmp/batch.json C:\Users\crick\_k_batch.json | Out-Null
  & $adb -s emulator-5554 push C:\Users\crick\_k_batch.json /data/local/tmp/inject.json | Out-Null
  & $adb -s emulator-5554 shell "chmod 644 /data/local/tmp/inject.json; run-as se.konsiliet cp /data/local/tmp/inject.json files/inject.json; run-as se.konsiliet rm -f files/ack.json"
  & $adb -s emulator-5554 shell am broadcast -a se.konsiliet.debug.INJECT -n se.konsiliet/se.konsiliet.app.debug.DebugBridge | Out-Null
  Start-Sleep -Milliseconds 1500
  $ack = (& $adb -s emulator-5554 shell run-as se.konsiliet cat files/ack.json) -join ""
  "batch $range -> $ack"
  if ($ack -notmatch '"ok":true') { "ingen kvittens, klockan behåller raderna"; break }
  & $adb -s emulator-5556 shell am broadcast -a se.konsiliet.debug.ACK -n se.konsiliet/se.konsiliet.wear.debug.DebugBridge | Out-Null
  Start-Sleep -Milliseconds 500
}
