$ErrorActionPreference = "Continue"

$KbDir = "D:\law-rag-project\law-rag-kb"
$R1Dir = "D:\law-rag-project\test-evidence\manual-rag-20260715-152640\R1-offline-baseline"

$PythonExe = Join-Path $KbDir ".venv\Scripts\python.exe"
$LogFile = Join-Path $R1Dir "R1-02-pytest-full.log"
$JUnitFile = Join-Path $R1Dir "R1-02-pytest-junit.xml"
$SummaryFile = Join-Path $R1Dir "R1-02-pytest-summary.txt"

Set-Location $KbDir

if (-not (Test-Path $PythonExe)) {
    Write-Host "[FAIL] 未找到 Python 虚拟环境：$PythonExe"
    exit 127
}

Remove-Item $LogFile -Force -ErrorAction SilentlyContinue
Remove-Item $JUnitFile -Force -ErrorAction SilentlyContinue
Remove-Item $SummaryFile -Force -ErrorAction SilentlyContinue

Write-Host "===== R1-02 Python 离线自动化测试 ====="
Write-Host "开始时间：$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz')"
Write-Host "预计收集测试：93"
Write-Host "云端调用：否"
Write-Host ""

$StartTime = Get-Date

$PytestOutput = @(
    & $PythonExe `
        -m pytest `
        -q `
        -ra `
        --durations=20 `
        --junitxml="$JUnitFile" `
        2>&1
)

$PytestExit = $LASTEXITCODE
$EndTime = Get-Date
$Elapsed = $EndTime - $StartTime

$PytestOutput |
    Tee-Object `
        -FilePath $LogFile

$SummaryLines = @(
    $PytestOutput |
    Where-Object {
        $_ -match 'passed|failed|error|skipped|xfailed|xpassed|warnings? in|seconds'
    } |
    Select-Object -Last 20
)

$Summary = @()

$Summary += "===== R1-02 pytest 测试摘要 ====="
$Summary += "开始时间：$($StartTime.ToString('yyyy-MM-dd HH:mm:ss zzz'))"
$Summary += "结束时间：$($EndTime.ToString('yyyy-MM-dd HH:mm:ss zzz'))"
$Summary += "墙钟耗时：$([Math]::Round($Elapsed.TotalSeconds, 2)) 秒"
$Summary += "pytest exit code：$PytestExit"
$Summary += ""
$Summary += "pytest 结果摘要："
$Summary += $SummaryLines
$Summary += ""

if ($PytestExit -eq 0) {
    $Summary += "R1-02 实际结果：PASS"
}
else {
    $Summary += "R1-02 实际结果：FAIL"
}

$Summary += ""
$Summary += "完整日志：$LogFile"
$Summary += "JUnit XML：$JUnitFile"

$Summary |
    Set-Content `
        -Path $SummaryFile `
        -Encoding UTF8

Write-Host ""
Write-Host "===== R1-02 最终摘要 ====="

$Summary

Write-Host ""
Write-Host "失败和错误定位："

$FailureLines = @(
    $PytestOutput |
    Select-String `
        -Pattern 'FAILED|ERROR|E   |AssertionError|Traceback' `
        -CaseSensitive:$false
)

if ($FailureLines.Count -eq 0) {
    Write-Host "未发现 FAILED 或 ERROR。"
}
else {
    $FailureLines |
        Select-Object -First 80
}

Write-Host ""
Write-Host "证据目录：$R1Dir"

exit $PytestExit
