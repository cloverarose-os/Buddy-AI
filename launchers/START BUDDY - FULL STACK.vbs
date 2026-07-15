' ==========================================================
'  START BUDDY - FULL STACK.vbs
'  Double-click: brings up the ENTIRE multimodal system, in order:
'      1. Ollama        (the LLM server, LAN-exposed for Home Assistant)
'      2. Brain         (buddy_ai.py :8766 - chat, tools, IMAGE GENERATION)
'      3. Watchdog      (GPU / gaming arbiter)
'      4. Buddy the pet (the desktop character)
'  Each one is health-checked before the next starts, and it KEEPS THEM
'  ALIVE - if anything dies it gets restarted automatically.
'  Safe to double-click twice - it will not start duplicates.
' ==========================================================
Set s = CreateObject("WScript.Shell")
s.Run "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File ""G:\Buddy AI\Launchers\BuddyStack.ps1"" -Mode Full -KeepAlive", 0, False
