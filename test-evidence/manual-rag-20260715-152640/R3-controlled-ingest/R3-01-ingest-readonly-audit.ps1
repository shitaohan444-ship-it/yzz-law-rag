$ErrorActionPreference = "Continue"

$Root = "D:\law-rag-project"
$KbDir = Join-Path $Root "law-rag-kb"
$TestFilesDir = Join-Path $Root "test_files"
$R3Dir = "D:\law-rag-project\test-evidence\manual-rag-20260715-152640\R3-controlled-ingest"
$EvidenceFile = Join-Path $R3Dir "R3-01-ingest-readonly-audit.txt"

$Output = @()

function Add-Line {
    param([string]$Text = "")
    $script:Output += $Text
}

function Add-FileContext {
    param(
        [string]$FilePath,
        [string]$DisplayName
    )

    Add-Line "============================================================"
    Add-Line "文件：$DisplayName"

    if (-not (Test-Path $FilePath)) {
        Add-Line "[NOT FOUND]"
        Add-Line
        return
    }

    $FileLines = Get-Content $FilePath

    Add-Line "总行数：$($FileLines.Count)"
    Add-Line

    $Patterns = @(
        'argparse',
        'add_argument',
        '--force',
        '\bforce\b',
        'requests\.',
        'httpx\.',
        'Invoke',
        '/ingest',
        '/documents',
        'INSERT',
        'UPDATE',
        'DELETE',
        'MinIO',
        'object_key',
        'attachment',
        'doc_id',
        'document_id',
        'batch',
        'pending',
        'success',
        'failed'
    )

    $Matches = @(
        Select-String `
            -Path $FilePath `
            -Pattern $Patterns `
            -CaseSensitive:$false `
            -ErrorAction SilentlyContinue
    )

    Add-Line "关键命中数量：$($Matches.Count)"
    Add-Line

    $ShownRanges = @{}

    foreach ($Match in $Matches) {
        $Start = [Math]::Max(1, $Match.LineNumber - 3)
        $End = [Math]::Min($FileLines.Count, $Match.LineNumber + 5)
        $RangeKey = "$Start-$End"

        if ($ShownRanges.ContainsKey($RangeKey)) {
            continue
        }

        $ShownRanges[$RangeKey] = $true

        Add-Line "----- 行 $Start 至 $End -----"

        for ($LineNumber = $Start; $LineNumber -le $End; $LineNumber++) {
            $Prefix = if ($LineNumber -eq $Match.LineNumber) {
                ">>>"
            }
            else {
                "   "
            }

            Add-Line (
                "{0} {1,5}: {2}" -f
                $Prefix,
                $LineNumber,
                $FileLines[$LineNumber - 1]
            )
        }

        Add-Line
    }
}

Set-Location $Root

Add-Line "===== R3-01 入库脚本与测试文件只读审计 ====="
Add-Line "测试时间：$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz')"
Add-Line

$SeedScript = Join-Path $KbDir "scripts\seed_test_doc.py"
$BatchScript = Join-Path $KbDir "scripts\batch_ingest.py"

Add-FileContext `
    -FilePath $SeedScript `
    -DisplayName "law-rag-kb\scripts\seed_test_doc.py"

Add-FileContext `
    -FilePath $BatchScript `
    -DisplayName "law-rag-kb\scripts\batch_ingest.py"

Add-Line "============================================================"
Add-Line "API 入库路由相关代码"
Add-Line

$ApiFiles = @(
    Get-ChildItem `
        -Path (Join-Path $KbDir "app") `
        -File `
        -Recurse `
        -Filter "*.py" `
        -ErrorAction SilentlyContinue
)

$RouteMatches = @(
    $ApiFiles |
    Select-String `
        -Pattern '@.*(post|put).*ingest|documents.*ingest|def .*ingest|async def .*ingest' `
        -CaseSensitive:$false `
        -ErrorAction SilentlyContinue
)

Add-Line "路由命中数量：$($RouteMatches.Count)"

foreach ($Match in $RouteMatches) {
    $RelativePath = $Match.Path.Substring($KbDir.Length + 1)
    $Lines = Get-Content $Match.Path
    $Start = [Math]::Max(1, $Match.LineNumber - 5)
    $End = [Math]::Min($Lines.Count, $Match.LineNumber + 15)

    Add-Line
    Add-Line "----- $RelativePath，行 $Start 至 $End -----"

    for ($LineNumber = $Start; $LineNumber -le $End; $LineNumber++) {
        $Prefix = if ($LineNumber -eq $Match.LineNumber) {
            ">>>"
        }
        else {
            "   "
        }

        Add-Line (
            "{0} {1,5}: {2}" -f
            $Prefix,
            $LineNumber,
            $Lines[$LineNumber - 1]
        )
    }
}

Add-Line
Add-Line "============================================================"
Add-Line "TXT / Markdown 候选测试文件"
Add-Line

if (-not (Test-Path $TestFilesDir)) {
    Add-Line "[FAIL] test_files 目录不存在"
}
else {
    $Candidates = @(
        Get-ChildItem `
            -Path $TestFilesDir `
            -File `
            -Recurse `
            -ErrorAction SilentlyContinue |
        Where-Object {
            $_.Extension.ToLowerInvariant() -in @(
                ".txt",
                ".md",
                ".markdown"
            )
        } |
        Sort-Object Length, FullName
    )

    Add-Line "候选文件总数：$($Candidates.Count)"
    Add-Line

    foreach ($File in $Candidates | Select-Object -First 40) {
        $RelativePath = $File.FullName.Substring($Root.Length + 1)
        $Hash = Get-FileHash `
            -Path $File.FullName `
            -Algorithm SHA256

        Add-Line (
            "path={0}`tsize_bytes={1}`tsha256={2}" -f
            $RelativePath,
            $File.Length,
            $Hash.Hash
        )
    }
}

Add-Line
Add-Line "============================================================"
Add-Line "候选文件内容预览"
Add-Line

$PreviewCandidates = @(
    Get-ChildItem `
        -Path $TestFilesDir `
        -File `
        -Recurse `
        -ErrorAction SilentlyContinue |
    Where-Object {
        $_.Extension.ToLowerInvariant() -in @(
            ".txt",
            ".md",
            ".markdown"
        ) -and
        $_.Length -gt 0 -and
        $_.Length -le 200000
    } |
    Sort-Object Length, FullName |
    Select-Object -First 10
)

foreach ($File in $PreviewCandidates) {
    $RelativePath = $File.FullName.Substring($Root.Length + 1)

    Add-Line
    Add-Line "----- $RelativePath -----"
    Add-Line "size_bytes=$($File.Length)"

    $Preview = @(
        Get-Content `
            -Path $File.FullName `
            -TotalCount 25 `
            -ErrorAction SilentlyContinue
    )

    foreach ($Line in $Preview) {
        $SafeLine = [string]$Line

        if ($SafeLine.Length -gt 300) {
            $SafeLine = $SafeLine.Substring(0, 300) + "..."
        }

        Add-Line $SafeLine
    }
}

$Output |
    Set-Content `
        -Path $EvidenceFile `
        -Encoding UTF8

Write-Host "===== R3-01 控制台摘要 ====="
Write-Host ""

Write-Host "脚本是否存在："
Write-Host "seed_test_doc.py = $(Test-Path $SeedScript)"
Write-Host "batch_ingest.py = $(Test-Path $BatchScript)"
Write-Host "入库路由命中数量 = $($RouteMatches.Count)"
Write-Host ""

Write-Host "最小的 TXT / Markdown 候选："

$Candidates |
    Select-Object -First 10 |
    ForEach-Object {
        $RelativePath = $_.FullName.Substring($Root.Length + 1)

        Write-Host (
            "{0} bytes`t{1}" -f
            $_.Length,
            $RelativePath
        )
    }

Write-Host ""
Write-Host "证据文件：$EvidenceFile"
Write-Host "本步骤没有创建文档记录，也没有执行入库。"
