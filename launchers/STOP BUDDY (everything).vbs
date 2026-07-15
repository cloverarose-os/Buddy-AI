' ==========================================================
'  STOP BUDDY (everything).vbs
'  Double-click: shuts down the whole stack - pet, brain, watchdog,
'  Ollama. Use this to free the GPU completely.
' ==========================================================
Set s = CreateObject("WScript.Shell")
s.Run "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File ""G:\Buddy AI\Launchers\BuddyStack.ps1"" -Mode Stop", 0, False
