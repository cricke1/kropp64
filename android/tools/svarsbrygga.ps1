# Testbrygga klockemulator -> mobilemulator för svar på knuffar (ersätter MessageClient /konsiliet/svar).
# Klockans SvarReceiver skriver svaret till files/svar.json; mobilen lämnar det till samma kod som
# WatchListenerService.onMessageReceived, som skickar det till servern.
$adb = "C:\Users\crick\Android\Sdk\platform-tools\adb.exe"
& $adb -s emulator-5556 shell "run-as se.konsiliet cat files/svar.json > /data/local/tmp/svar.json"
& $adb -s emulator-5556 pull /data/local/tmp/svar.json C:\Users\crick\_k_svar.json | Out-Null
& $adb -s emulator-5554 push C:\Users\crick\_k_svar.json /data/local/tmp/svar.json | Out-Null
& $adb -s emulator-5554 shell "chmod 644 /data/local/tmp/svar.json; run-as se.konsiliet cp /data/local/tmp/svar.json files/svar.json"
"svar: " + (Get-Content C:\Users\crick\_k_svar.json -Raw)
& $adb -s emulator-5554 shell am broadcast -a se.konsiliet.debug.SVAR -n se.konsiliet/se.konsiliet.app.debug.DebugBridge | Out-Null
