# Install a per-user desktop shortcut without administrator privileges.
param(
    [string]$Distribution = 'Ubuntu',
    [string]$ProjectPath = '/home/milton/Gemelo_digital_cali'
)
$ErrorActionPreference = 'Stop'
if ($Distribution -notmatch '^[\w.-]+$' -or $ProjectPath -notmatch '^/[\w/.-]+$') {
    throw 'Usa un nombre de distribucion y una ruta de proyecto sin espacios ni caracteres especiales.'
}
$desktop = [Environment]::GetFolderPath('Desktop')
$shortcutPath = Join-Path $desktop 'Gemelo digital Cali.lnk'
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = Join-Path $env:WINDIR 'System32\wsl.exe'
$shortcut.Arguments = "-d $Distribution --exec bash $ProjectPath/scripts/start_panel.sh"
$shortcut.WorkingDirectory = $env:USERPROFILE
$shortcut.Description = 'Inicia WSL y Docker, abre el panel y mantiene la aplicacion disponible.'
$shortcut.IconLocation = (Join-Path $env:WINDIR 'System32\shell32.dll') + ',17'
$shortcut.WindowStyle = 1
$shortcut.Save()
Write-Output "Acceso directo creado: $shortcutPath"
