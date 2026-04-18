$ws = New-Object -ComObject WScript.Shell
$desktop = [System.Environment]::GetFolderPath('Desktop')
$shortcut = $ws.CreateShortcut("$desktop\HUBERT.lnk")
$shortcut.TargetPath = "C:\Users\Jake\AppData\Local\Programs\Python\Python313\pythonw.exe"
$shortcut.Arguments = '"C:\Users\Jake\Jarvis\main.py"'
$shortcut.WorkingDirectory = "C:\Users\Jake\Jarvis"
$shortcut.Description = "H.U.B.E.R.T. AI Assistant"
$shortcut.Save()
Write-Host "Shortcut created at $desktop\HUBERT.lnk"
