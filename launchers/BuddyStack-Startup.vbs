' ==========================================================
'  BuddyStack-Startup.vbs   (runs at login)
'
'  Replaces the FOUR old startup files (Ollama.vbs, LaunchBuddyAI.vbs,
'  ClaudeWatchdog.vbs, ClaudeBuddy.vbs), which all fired at the SAME
'  INSTANT with no ordering, no health checks and no keep-alive. On a
'  cold boot the Brain could start before Ollama was serving; and when
'  the Brain later died, nothing restarted it - which silently broke
'  Buddy's chat AND Home Assistant's Assist ("Oops, an error occurred").
'
'  This one brings the stack up IN ORDER, waits for each piece to
'  actually answer, and then KEEPS IT ALIVE.
'  (Originals preserved in G:\Buddy AI\_retired\old-startup-vbs-20260713)
' ==========================================================
Set s = CreateObject("WScript.Shell")
s.Run "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File ""G:\Buddy AI\Launchers\BuddyStack.ps1"" -Mode Full -KeepAlive", 0, False
