' ==========================================================
'  START BUDDY (PET).vbs
'  Double-click: opens the desktop pet.
'  Safe to double-click twice - it will NOT open a second Buddy.
' ==========================================================
Set s = CreateObject("WScript.Shell")
s.Run "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File ""G:\Buddy AI\Launchers\BuddyStack.ps1"" -Mode Pet", 0, False
