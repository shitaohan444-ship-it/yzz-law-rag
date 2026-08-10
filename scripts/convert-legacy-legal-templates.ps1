param(
    [string]$WorkspaceRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path,
    [string]$SofficePath = 'soffice',
    [int]$TimeoutSeconds = 120
)

$ErrorActionPreference = 'Stop'
$originalRoot = Join-Path $WorkspaceRoot '要素式模板'
$normalizedRoot = Join-Path $WorkspaceRoot 'law-rag-kb\templates\legal_documents\normalized'
$reportPath = Join-Path $WorkspaceRoot 'artifacts\legal-drafting\legacy-conversion-report.json'
$relativePaths = @(
    '答辩状\要素式银行信用卡纠纷答辩状.docx',
    '起诉状\要素式银行信用卡纠纷起诉状.docx'
)

if (-not (Get-Command $SofficePath -ErrorAction SilentlyContinue)) {
    throw '未找到 soffice。请在装有 LibreOffice 的受控主机或 document-renderer 镜像中运行。'
}

New-Item -ItemType Directory -Force -Path $normalizedRoot | Out-Null
$workRoot = Join-Path $normalizedRoot ('.legacy-conversion-work-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $workRoot | Out-Null
$results = @()
try {
    foreach ($relativePath in $relativePaths) {
        $source = Join-Path $originalRoot $relativePath
        $target = Join-Path $normalizedRoot $relativePath
        $sourceHashBefore = (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash.ToLowerInvariant()
        $signature = [IO.File]::ReadAllBytes($source)[0..7]
        $signatureHex = ($signature | ForEach-Object { $_.ToString('X2') }) -join ''
        if ($signatureHex -notlike 'D0CF11E0*') {
            throw "源文件不是 OLE DOC：$source"
        }

        $jobRoot = Join-Path $workRoot ([guid]::NewGuid().ToString('N'))
        New-Item -ItemType Directory -Path $jobRoot | Out-Null
        $staging = Join-Path $jobRoot (([IO.Path]::GetFileNameWithoutExtension($relativePath)) + '.doc')
        Copy-Item -LiteralPath $source -Destination $staging
        $process = Start-Process -FilePath $SofficePath -WindowStyle Hidden -PassThru -ArgumentList @(
            '--headless', '--nologo', '--nodefault', '--nofirststartwizard',
            '--convert-to', 'docx', '--outdir', $jobRoot, $staging
        )
        if (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
            $process.Kill()
            throw "LibreOffice 转换超时：$relativePath"
        }
        if ($process.ExitCode -ne 0) {
            throw "LibreOffice 转换失败，退出码 $($process.ExitCode)：$relativePath"
        }
        $converted = Join-Path $jobRoot (([IO.Path]::GetFileNameWithoutExtension($staging)) + '.docx')
        if (-not (Test-Path -LiteralPath $converted)) {
            throw "转换结果不存在：$relativePath"
        }
        $targetSignature = [IO.File]::ReadAllBytes($converted)[0..1]
        $targetSignatureHex = ($targetSignature | ForEach-Object { $_.ToString('X2') }) -join ''
        if ($targetSignatureHex -ne '504B') {
            throw "转换结果不是 OOXML：$relativePath"
        }
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $target) | Out-Null
        Move-Item -LiteralPath $converted -Destination $target -Force
        $sourceHashAfter = (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($sourceHashBefore -ne $sourceHashAfter) {
            throw "原件 hash 在转换后发生变化：$source"
        }
        $results += [ordered]@{
            relative_path = $relativePath.Replace('\', '/')
            original_sha256 = $sourceHashBefore
            converted_sha256 = (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash.ToLowerInvariant()
            converted_size = (Get-Item -LiteralPath $target).Length
            source_format = 'ole_doc'
            converted_format = 'ooxml'
            converter = 'LibreOffice headless'
        }
    }
}
finally {
    $resolvedNormalized = (Resolve-Path -LiteralPath $normalizedRoot).Path
    $resolvedWork = (Resolve-Path -LiteralPath $workRoot -ErrorAction SilentlyContinue).Path
    if ($resolvedWork -and $resolvedWork.StartsWith($resolvedNormalized + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
        Remove-Item -LiteralPath $resolvedWork -Recurse -Force
    }
}

New-Item -ItemType Directory -Force -Path (Split-Path -Parent $reportPath) | Out-Null
[ordered]@{
    generated_at = (Get-Date).ToUniversalTime().ToString('o')
    original_files_modified = $false
    conversions = $results
} | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $reportPath -Encoding utf8

Write-Host "已生成 $($results.Count) 份 OOXML normalized 副本；原件 hash 未变化。"
