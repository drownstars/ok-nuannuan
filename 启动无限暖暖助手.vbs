Set fs = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")
root = fs.GetParentFolderName(WScript.ScriptFullName)
pythonw = root & "\.venv\Scripts\pythonw.exe"
If Not fs.FileExists(pythonw) Then
  MsgBox "Please run bootstrap.ps1 first.", 16, "NuanNuan Assistant"
  WScript.Quit 1
End If
shell.CurrentDirectory = root
shell.Run Chr(34) & pythonw & Chr(34) & " " & Chr(34) & root & "\start_gui.py" & Chr(34), 0, False
