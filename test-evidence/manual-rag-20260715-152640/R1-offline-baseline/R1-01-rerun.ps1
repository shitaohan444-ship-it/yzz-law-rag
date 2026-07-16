$ErrorActionPreference = "Continue"

$KbDir = "D:\law-rag-project\law-rag-kb"
$R1Dir = "D:\law-rag-project\test-evidence\manual-rag-20260715-152640\R1-offline-baseline"
$EvidenceFile = Join-Path $R1Dir "R1-01-test-config-audit-rerun.txt"

$Lines = @()

function Add-Line {
    param([string]$Text)
    $script:Lines += $Text
}

Set-Location $KbDir

Add-Line "===== R1-01 离线测试配置审计复测 ====="
Add-Line "测试时间：$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz')"
Add-Line ""

Add-Line "===== 1. pytest 配置文件 ====="

foreach ($Name in @(
    "pytest.ini",
    "pyproject.toml",
    "setup.cfg",
    "tox.ini"
)) {
    $Path = Join-Path $KbDir $Name

    if (Test-Path $Path) {
        Add-Line "[FOUND] $Name"
        Add-Line "----- $Name -----"

        foreach ($ContentLine in Get-Content $Path) {
            Add-Line $ContentLine
        }

        Add-Line "----- end $Name -----"
    }
    else {
        Add-Line "[NOT FOUND] $Name"
    }
}

Add-Line ""
Add-Line "===== 2. 测试文件数量 ====="

$TestFiles = @(
    Get-ChildItem `
        -Path (Join-Path $KbDir "tests") `
        -File `
        -Recurse `
        -Filter "*.py" `
        -ErrorAction SilentlyContinue
)

Add-Line "Python 测试文件数量：$($TestFiles.Count)"

foreach ($File in $TestFiles | Sort-Object FullName) {
    Add-Line $File.FullName.Substring($KbDir.Length + 1)
}

Add-Line ""
Add-Line "===== 3. 云端调用相关代码命中 ====="

$CloudPattern = 'qwen3\.7|qwen3-vl|qwen.*plus|dashscope|api\.dashscope|AsyncOpenAI|OpenAI\s*\(|httpx\.|requests\.|aiohttp|DASHSCOPE_API_KEY|OPENAI_API_KEY|LLM_API_KEY|VL_API_KEY'

$CloudMatches = @(
    $TestFiles |
    Select-String `
        -Pattern $CloudPattern `
        -CaseSensitive:$false `
        -ErrorAction SilentlyContinue
)

Add-Line "云端相关命中数量：$($CloudMatches.Count)"

foreach ($Match in $CloudMatches) {
    $Relative = $Match.Path.Substring($KbDir.Length + 1)
    $Text = $Match.Line.Trim()

    if ($Text.Length -gt 300) {
        $Text = $Text.Substring(0, 300) + "..."
    }

    Add-Line "${Relative}:$($Match.LineNumber): $Text"
}

Add-Line ""
Add-Line "===== 4. Mock / Stub / 隔离代码命中 ====="

$IsolationPattern = 'monkeypatch|unittest\.mock|MagicMock|AsyncMock|\bmock\b|\bpatch\b|stub|fake|dependency_overrides|TestClient'

$IsolationMatches = @(
    $TestFiles |
    Select-String `
        -Pattern $IsolationPattern `
        -CaseSensitive:$false `
        -ErrorAction SilentlyContinue
)

Add-Line "隔离机制命中数量：$($IsolationMatches.Count)"

foreach ($Match in $IsolationMatches | Select-Object -First 100) {
    $Relative = $Match.Path.Substring($KbDir.Length + 1)
    $Text = $Match.Line.Trim()

    if ($Text.Length -gt 300) {
        $Text = $Text.Substring(0, 300) + "..."
    }

    Add-Line "${Relative}:$($Match.LineNumber): $Text"
}

Add-Line ""
Add-Line "===== 5. 跳过和外部测试标记 ====="

$MarkerPattern = 'pytest\.mark\.|skipif|pytest\.skip|xfail|integration|online|external|network|slow'

$MarkerMatches = @(
    $TestFiles |
    Select-String `
        -Pattern $MarkerPattern `
        -CaseSensitive:$false `
        -ErrorAction SilentlyContinue
)

Add-Line "标记命中数量：$($MarkerMatches.Count)"

foreach ($Match in $MarkerMatches) {
    $Relative = $Match.Path.Substring($KbDir.Length + 1)
    $Text = $Match.Line.Trim()

    if ($Text.Length -gt 300) {
        $Text = $Text.Substring(0, 300) + "..."
    }

    Add-Line "${Relative}:$($Match.LineNumber): $Text"
}

Add-Line ""
Add-Line "===== 6. pytest 只收集，不执行 ====="

$PythonExe = Join-Path $KbDir ".venv\Scripts\python.exe"

if (-not (Test-Path $PythonExe)) {
    $CollectExit = 127
    $CollectOutput = @("[FAIL] 未找到虚拟环境 Python")
}
else {
    $CollectOutput = @(
        & $PythonExe `
            -m pytest `
            --collect-only `
            -q `
            2>&1
    )

    $CollectExit = $LASTEXITCODE
}

Add-Line "pytest collect exit code：$CollectExit"

foreach ($OutputLine in $CollectOutput) {
    Add-Line ([string]$OutputLine)
}

Add-Line ""
Add-Line "===== R1-01 摘要 ====="
Add-Line "云端相关命中：$($CloudMatches.Count)"
Add-Line "隔离机制命中：$($IsolationMatches.Count)"
Add-Line "外部或跳过标记命中：$($MarkerMatches.Count)"
Add-Line "pytest collect exit code：$CollectExit"

$Lines |
    Set-Content `
        -Path $EvidenceFile `
        -Encoding UTF8

Write-Host "===== R1-01 复测摘要 ====="
Write-Host "云端相关命中：$($CloudMatches.Count)"
Write-Host "隔离机制命中：$($IsolationMatches.Count)"
Write-Host "外部或跳过标记命中：$($MarkerMatches.Count)"
Write-Host "pytest collect exit code：$CollectExit"
Write-Host ""
Write-Host "pytest 收集结果尾部："

$CollectOutput |
    Select-Object -Last 25

Write-Host ""
Write-Host "证据文件：$EvidenceFile"
Write-Host "尚未执行任何测试用例。"
