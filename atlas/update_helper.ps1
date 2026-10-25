param([Parameter(Mandatory = $true)][string]$Payload)
$ErrorActionPreference = 'Stop'
$data = Get-Content -LiteralPath $Payload -Raw -Encoding UTF8 | ConvertFrom-Json
$result = @{ passed = $false; restarted = $false }
$parentExited = $false
$env:PYINSTALLER_RESET_ENVIRONMENT = '1'
try {
    [System.IO.File]::WriteAllText($data.ready, 'ready')
    $parent = Get-Process -Id $data.parent_pid -ErrorAction SilentlyContinue
    if ($null -ne $parent) { $parent | Wait-Process -Timeout 120 }
    $parentExited = $true
    $others = @(Get-Process -Name CyberAtlas -ErrorAction SilentlyContinue | Where-Object { $_.Path -eq $data.executable })
    if ($others.Count -gt 0) { throw 'Close the other Cyber Atlas windows before updating.' }
    $hash = (Get-FileHash -LiteralPath $data.installer -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($hash -ne $data.sha256) { throw 'The update file changed after verification. Download it again.' }
    $installer = Start-Process -FilePath $data.installer -ArgumentList $data.installer_arguments -WindowStyle Hidden -Wait -PassThru
    $result.installer_exit_code = $installer.ExitCode
    if ($installer.ExitCode -eq 3010) { throw 'Windows needs to restart to finish the update. Your notes are saved.' }
    if ($installer.ExitCode -ne 0) { throw 'The update could not be installed. Try downloading the installer from GitHub Releases.' }
    $restarted = Start-Process -FilePath $data.executable -ArgumentList $data.restart_arguments -PassThru
    $result.restarted_pid = $restarted.Id
    $result.passed = $true
    $result.restarted = $true
} catch {
    $result.error = $_.Exception.Message
    $result | ConvertTo-Json | Set-Content -LiteralPath $data.result -Encoding UTF8
    if ($parentExited -and $result.installer_exit_code -ne 3010 -and (Test-Path -LiteralPath $data.executable)) {
        try { Start-Process -FilePath $data.executable -ArgumentList $data.restart_arguments; $result.restarted = $true } catch {}
    }
    Add-Type -AssemblyName PresentationFramework
    [System.Windows.MessageBox]::Show($result.error, 'Cyber Atlas update') | Out-Null
} finally {
    $result | ConvertTo-Json | Set-Content -LiteralPath $data.result -Encoding UTF8
}
