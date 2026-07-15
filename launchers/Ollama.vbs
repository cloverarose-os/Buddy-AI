Set s = CreateObject("WScript.Shell")
s.Environment("PROCESS")("OLLAMA_HOST") = "0.0.0.0"
s.Environment("PROCESS")("OLLAMA_MODELS") = "G:\Ollama\models"
' %LOCALAPPDATA% expands to C:\Users\<you>\AppData\Local, so no username is
' baked in and this runs on any machine.
ollamaExe = s.ExpandEnvironmentStrings("%LOCALAPPDATA%\Programs\Ollama\ollama.exe")
s.Run """" & ollamaExe & """ serve", 0, False
