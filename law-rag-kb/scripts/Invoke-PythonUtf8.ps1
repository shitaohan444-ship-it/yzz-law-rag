[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, ValueFromPipeline = $true, Position = 0)]
    [AllowEmptyString()]
    [string]$Code,

    [Parameter(Mandatory = $false)]
    [string]$PythonExe = (Join-Path $PSScriptRoot '..\.venv\Scripts\python.exe')
)

begin {
    $codeParts = New-Object 'System.Collections.Generic.List[string]'
}

process {
    $codeParts.Add($Code)
}

end {
    $resolvedPython = $null
    if (Test-Path -LiteralPath $PythonExe -PathType Leaf) {
        $resolvedPython = (Resolve-Path -LiteralPath $PythonExe).Path
    }
    else {
        $command = Get-Command $PythonExe -ErrorAction SilentlyContinue
        if ($null -ne $command) {
            $resolvedPython = $command.Source
        }
    }

    if ([string]::IsNullOrWhiteSpace($resolvedPython)) {
        throw "Python executable not found: $PythonExe"
    }

    $scriptText = $codeParts -join [Environment]::NewLine
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)

    $previousOutputEncoding = $global:OutputEncoding
    $previousConsoleOutputEncoding = [Console]::OutputEncoding
    $previousPythonIoEncoding = $env:PYTHONIOENCODING
    $hadPythonIoEncoding = Test-Path Env:PYTHONIOENCODING

    try {
        # Windows PowerShell 5.1 uses $OutputEncoding when piping .NET strings to
        # native processes. Its legacy default can replace non-ASCII text with '?'.
        $global:OutputEncoding = $utf8NoBom
        [Console]::OutputEncoding = $utf8NoBom
        $env:PYTHONIOENCODING = 'utf-8'

        $scriptText | & $resolvedPython -
        $pythonExitCode = $LASTEXITCODE
    }
    finally {
        $global:OutputEncoding = $previousOutputEncoding
        [Console]::OutputEncoding = $previousConsoleOutputEncoding
        if ($hadPythonIoEncoding) {
            $env:PYTHONIOENCODING = $previousPythonIoEncoding
        }
        else {
            Remove-Item Env:PYTHONIOENCODING -ErrorAction SilentlyContinue
        }
    }

    if ($pythonExitCode -ne 0) {
        exit $pythonExitCode
    }
}
