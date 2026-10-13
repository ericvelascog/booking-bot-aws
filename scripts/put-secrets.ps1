<#
Sube las variables de app/.env a SSM Parameter Store, cifradas (SecureString),
con el nombre /booking-bot/<VARIABLE>.

Los valores van directos a AWS, sin pasar por Terraform: así nunca quedan
escritos en el estado de Terraform. Volver a ejecutarlo actualiza los valores.

Uso, desde la raíz del repo y con la sesión de `aws login` activa:
    powershell -ExecutionPolicy Bypass -File .\scripts\put-secrets.ps1
#>
param(
    [string]$EnvFile = "app/.env",
    [string]$Prefix = "/booking-bot",
    [string]$Region = "eu-west-1"
)

$ErrorActionPreference = "Stop"
$tmp = New-TemporaryFile

try {
    foreach ($line in Get-Content $EnvFile -Encoding UTF8) {
        if ($line -match '^\s*(#|$)') { continue }

        $key, $value = $line -split '=', 2
        $key = $key.Trim()
        if (-not $value -or -not $value.Trim()) {
            Write-Host "  (vacia, no se sube)  $key"
            continue
        }

        # El valor viaja en un archivo temporal: si fuera como argumento,
        # PowerShell 5.1 estropearía las comillas del JSON de Google
        [IO.File]::WriteAllText($tmp.FullName, $value.Trim())
        aws ssm put-parameter --region $Region --name "$Prefix/$key" `
            --type SecureString --value "file://$($tmp.FullName)" --overwrite | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "No se pudo subir $key" }

        Write-Host "  subida:  $Prefix/$key"
    }
}
finally {
    Remove-Item $tmp -ErrorAction SilentlyContinue
}
