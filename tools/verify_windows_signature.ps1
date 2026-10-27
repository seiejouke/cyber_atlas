param(
    [Parameter(Mandatory = $true)][string]$LiteralPath,
    [Parameter(Mandatory = $true)][ValidatePattern('^[0-9A-Fa-f]{64}$')][string]$CertificateSha256,
    [Parameter(Mandatory = $true)][string]$SignTool
)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
try {
    $signature = Get-AuthenticodeSignature -LiteralPath $LiteralPath
    if ($signature.Status -ne 'Valid' -or $signature.SignatureType -ne 'Authenticode') {
        throw 'A valid embedded Authenticode signature is required.'
    }
    if ($null -eq $signature.TimeStamperCertificate) {
        throw 'A trusted timestamp is required.'
    }
    $hasher = [System.Security.Cryptography.SHA256]::Create()
    try {
        $actual = ([BitConverter]::ToString($hasher.ComputeHash($signature.SignerCertificate.RawData))).Replace('-', '')
    } finally { $hasher.Dispose() }
    if ($actual -ne $CertificateSha256.ToUpperInvariant()) {
        throw 'The signing certificate does not match the configured SHA-256 fingerprint.'
    }
    # /tw warns about a missing timestamp; any warning/error is a failure here.
    $verification = & $SignTool verify /pa /all /tw /v $LiteralPath 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "SignTool verification failed (exit $LASTEXITCODE): $verification"
    }
    @{
        valid = $true
        certificate_sha256 = $actual.ToLowerInvariant()
        subject = $signature.SignerCertificate.Subject
        timestamp_subject = $signature.TimeStamperCertificate.Subject
    } | ConvertTo-Json -Compress
} catch {
    [Console]::Error.WriteLine($_.Exception.Message)
    exit 1
}
