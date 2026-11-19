$ErrorActionPreference = 'Stop'

$requestedVersion = $null
$explicitBlender = $null
$cliArgs = [System.Collections.Generic.List[string]]::new()
$valueFlags = @('--blender', '--blender-version', '--jobs-dir', '--transactions-dir', '--timeout')
$index = 0
while ($index -lt $args.Count -and ([string]$args[$index]).StartsWith('--', [StringComparison]::Ordinal) -and $args[$index] -cne '--') {
    $argument = [string]$args[$index++]
    $parts = $argument.Split('=', 2)
    $option = $parts[0]
    if ($option -cnotin $valueFlags) {
        $cliArgs.Add($argument)
        continue
    }
    if ($parts.Length -eq 2) {
        $value = $parts[1]
    } else {
        if ($index -ge $args.Count -or ([string]$args[$index]).StartsWith('--', [StringComparison]::Ordinal)) { throw "$option needs a value." }
        $value = [string]$args[$index++]
    }
    switch -CaseSensitive ($option) {
        '--blender-version' {
            if ($requestedVersion) { throw 'Specify --blender-version once.' }
            if ($value -cnotin @('5.2.1', '5.3.0')) { throw 'Supported --blender-version values are 5.2.1 and 5.3.0.' }
            $requestedVersion = $value
        }
        '--blender' {
            if (!$value -or $explicitBlender) { throw 'Specify one Blender executable after --blender.' }
            $explicitBlender = $value
        }
        default { $cliArgs.Add("$option=$value") }
    }
}
if ($requestedVersion -and $explicitBlender) { throw 'Select either --blender-version or --blender.' }

if ($explicitBlender) {
    $blender = $explicitBlender
} else {
    $version = if ($requestedVersion) { $requestedVersion } else { '5.3.0' }
    $releases = $env:BLENDERCTL_BLENDER_ROOT
    if (!$releases) { $releases = Join-Path $PSScriptRoot 'runtime\blender\releases' }
    elseif (![System.IO.Path]::IsPathFullyQualified($releases)) { throw 'BLENDERCTL_BLENDER_ROOT must be an absolute path.' }
    $blender = Join-Path $releases "$version\blender-$version-windows-x64\blender.exe"
}
if (!(Test-Path -LiteralPath $blender -PathType Leaf)) {
    throw "Blender executable missing at $blender. Set BLENDERCTL_BLENDER_ROOT or pass --blender with the executable path."
}
$blender = (Resolve-Path -LiteralPath $blender).Path
$product = (Get-Item -LiteralPath $blender).VersionInfo.ProductVersionRaw
if (!$explicitBlender -and $product.ToString(3) -cne $version) { throw "Expected Blender $version at $blender. The executable reports $product." }
$python = Join-Path (Split-Path -Parent $blender) ($product.ToString(2) + '\python\bin\python.exe')
if (!(Test-Path -LiteralPath $python -PathType Leaf)) { throw "Bundled Blender Python missing at $python." }

$entry = Join-Path $PSScriptRoot 'tools\blenderctl\cli.py'
$cliArgs.Insert(0, "--blender=$blender")
for (; $index -lt $args.Count; $index++) { $cliArgs.Add([string]$args[$index]) }
& $python -B $entry @cliArgs
exit $LASTEXITCODE
