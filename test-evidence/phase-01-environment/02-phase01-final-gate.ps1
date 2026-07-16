$ErrorActionPreference = "Continue"

$Root = "D:\law-rag-project"
$EvidenceFile = Join-Path $Root "test-evidence\phase-01-environment\02-phase01-final-gate.txt"

$Results = @()

function Add-Result {
    param(
        [string]$Item,
        [string]$Status,
        [string]$Detail
    )

    $script:Results += [PSCustomObject]@{
        Item   = $Item
        Status = $Status
        Detail = $Detail
    }
}

Set-Location $Root

# 1. 默认 Python
$PythonCommand = Get-Command python -ErrorAction SilentlyContinue

if ($null -eq $PythonCommand) {
    Add-Result "默认 Python" "FAIL" "未找到 python 命令"
}
else {
    $PythonVersion = (python --version 2>&1 | Out-String).Trim()

    if ($PythonVersion -match '^Python 3\.11\.') {
        Add-Result "默认 Python" "PASS" $PythonVersion
    }
    else {
        Add-Result "默认 Python" "WARN" "$PythonVersion；项目测试仍可使用 law-rag-kb\.venv"
    }
}

# 2. RAG 虚拟环境
$KbPython = Join-Path $Root "law-rag-kb\.venv\Scripts\python.exe"

if (-not (Test-Path $KbPython)) {
    Add-Result "RAG Python 虚拟环境" "FAIL" "解释器不存在"
}
else {
    $KbVersion = (& $KbPython --version 2>&1 | Out-String).Trim()

    if ($KbVersion -match '^Python 3\.11\.') {
        Add-Result "RAG Python 虚拟环境" "PASS" $KbVersion
    }
    else {
        Add-Result "RAG Python 虚拟环境" "FAIL" $KbVersion
    }
}

# 3. Node.js
$NodeCommand = Get-Command node -ErrorAction SilentlyContinue

if ($null -eq $NodeCommand) {
    Add-Result "Node.js" "FAIL" "未找到 node 命令"
}
else {
    $NodeVersion = (node --version 2>&1 | Out-String).Trim()

    if ($NodeVersion -match '^v22\.') {
        Add-Result "Node.js" "PASS" $NodeVersion
    }
    else {
        Add-Result "Node.js" "FAIL" "项目要求 22.x，实际为 $NodeVersion"
    }
}

# 4. pnpm
$PnpmCommand = Get-Command pnpm -ErrorAction SilentlyContinue

if ($null -eq $PnpmCommand) {
    Add-Result "pnpm" "FAIL" "未找到 pnpm 命令"
}
else {
    $PnpmVersion = (pnpm --version 2>&1 | Out-String).Trim()
    Add-Result "pnpm" "PASS" $PnpmVersion
}

# 5. Docker Engine
$DockerInfo = docker info --format "{{.ServerVersion}}" 2>&1
$DockerInfoExit = $LASTEXITCODE

if ($DockerInfoExit -eq 0) {
    Add-Result "Docker Engine" "PASS" "Server $(($DockerInfo | Out-String).Trim())"
}
else {
    Add-Result "Docker Engine" "FAIL" "Docker daemon 不可连接"
}

# 6. Compose 配置解析：权威环境变量检查
$ComposeOutput = docker compose --env-file ".env" config --quiet 2>&1
$ComposeExit = $LASTEXITCODE
$ComposeText = ($ComposeOutput | Out-String).Trim()

if ($ComposeExit -eq 0) {
    Add-Result "Docker Compose 配置解析" "PASS" "当前 .env 可完整解析 docker-compose.yml"
}
else {
    if ([string]::IsNullOrWhiteSpace($ComposeText)) {
        $ComposeText = "配置解析失败，但未返回错误文本"
    }

    Add-Result "Docker Compose 配置解析" "FAIL" $ComposeText
}

# 7. 对比 .env.example，只输出变量名，不输出值
function Read-EnvKeys {
    param([string]$Path)

    if (-not (Test-Path $Path)) {
        return @()
    }

    return @(
        Get-Content $Path |
        ForEach-Object {
            if ($_ -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=') {
                $Matches[1]
            }
        } |
        Where-Object { $_ } |
        Sort-Object -Unique
    )
}

$EnvKeys = Read-EnvKeys (Join-Path $Root ".env")
$ExampleKeys = Read-EnvKeys (Join-Path $Root ".env.example")
$MissingExampleKeys = @($ExampleKeys | Where-Object { $_ -notin $EnvKeys })

if ($MissingExampleKeys.Count -eq 0) {
    Add-Result ".env.example 键覆盖" "PASS" "全部示例键均已声明"
}
elseif ($ComposeExit -eq 0) {
    Add-Result ".env.example 键覆盖" "WARN" (
        "以下键未声明，但 Compose 可使用默认值完成解析：" +
        ($MissingExampleKeys -join ", ")
    )
}
else {
    Add-Result ".env.example 键覆盖" "FAIL" (
        "以下键未声明，且 Compose 配置解析失败：" +
        ($MissingExampleKeys -join ", ")
    )
}

$FailCount = @($Results | Where-Object Status -eq "FAIL").Count
$WarnCount = @($Results | Where-Object Status -eq "WARN").Count
$PassCount = @($Results | Where-Object Status -eq "PASS").Count

if ($FailCount -gt 0) {
    $Overall = "FAIL"
}
elseif ($WarnCount -gt 0) {
    $Overall = "PASS_WITH_WARNINGS"
}
else {
    $Overall = "PASS"
}

$Output = @()

$Output += "===== 第一阶段最终校验 ====="
$Output += "测试时间：$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz')"
$Output += ""

foreach ($Result in $Results) {
    $Output += "[$($Result.Status)] $($Result.Item)：$($Result.Detail)"
}

$Output += ""
$Output += "PASS：$PassCount"
$Output += "WARN：$WarnCount"
$Output += "FAIL：$FailCount"
$Output += "第一阶段最终结果：$Overall"

$Output |
    Set-Content -Path $EvidenceFile -Encoding UTF8

$Output
