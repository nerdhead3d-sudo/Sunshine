' Avvia il pet senza aprire nessuna finestra di console.
' Doppio click su questo file per partire; per chiuderlo usa l'icona
' nella system tray ("Esci") o il tasto Esc con il pet in primo piano.

Set fso = CreateObject("Scripting.FileSystemObject")
baseDir = fso.GetParentFolderName(WScript.ScriptFullName)
pythonw = baseDir & "\venv\Scripts\pythonw.exe"
mainScript = baseDir & "\main.py"

Set shell = CreateObject("WScript.Shell")
shell.CurrentDirectory = baseDir
shell.Run """" & pythonw & """ """ & mainScript & """", 0, False
