$ErrorActionPreference = "Continue"
$ProgressPreference = "SilentlyContinue"

$Root = "D:\law-rag-project"
$EvidenceDir = Join-Path $Root "test-evidence\phase-02-infrastructure"
$LogFile = Join-Path $EvidenceDir "01-infrastructure-full.log"
$SummaryFile = Join-Path $EvidenceDir "01-infrastructure-summary.csv"

Set-Location $Root
Remove-Item $LogFile -Force -ErrorAction SilentlyContinue

$Results = @()

function Write-Log {
    param([string]$Text)

    $Text | Tee-Object -FilePath $LogFile -Append
}

function Add-Result {
    param(
        [string]$Area,
        [string]$Item,
        [ValidateSet("PASS", "WARN", "FAIL")]
        [string]$Status,
        [string]$Detail
    )

    $script:Results += [PSCustomObject]@{
        Area   = $Area
        Item   = $Item
        Status = $Status
        Detail = $Detail
    }

    Write-Log "[$Status] [$Area] $Item：$Detail"
}

function Find-Service {
    param(
        [string[]]$Services,
        [string[]]$Patterns
    )

    foreach ($Pattern in $Patterns) {
        foreach ($Service in $Services) {
            if ($Service -match $Pattern) {
                return $Service
            }
        }
    }

    return $null
}

function Test-ComposeService {
    param(
        [string]$LogicalName,
        [string]$ServiceName
    )

    if ([string]::IsNullOrWhiteSpace($ServiceName)) {
        Add-Result `
            -Area "容器" `
            -Item $LogicalName `
            -Status "FAIL" `
            -Detail "未在 docker-compose.yml 中识别到对应服务"

        return
    }

    $ContainerIdOutput = docker compose ps --all -q $ServiceName 2>&1
    $ContainerIdExit = $LASTEXITCODE
    $ContainerId = ($ContainerIdOutput | Out-String).Trim()

    if ($ContainerIdExit -ne 0 -or [string]::IsNullOrWhiteSpace($ContainerId)) {
        Add-Result `
            -Area "容器" `
            -Item "$LogicalName / $ServiceName" `
            -Status "FAIL" `
            -Detail "没有找到对应容器"

        return
    }

    $InspectOutput = docker inspect `
        --format '{{.State.Status}}|{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}|{{.RestartCount}}|{{.State.ExitCode}}' `
        $ContainerId 2>&1

    $InspectExit = $LASTEXITCODE
    $InspectText = ($InspectOutput | Out-String).Trim()

    if ($InspectExit -ne 0) {
        Add-Result `
            -Area "容器" `
            -Item "$LogicalName / $ServiceName" `
            -Status "FAIL" `
            -Detail "docker inspect 失败：$InspectText"

        return
    }

    $Parts = $InspectText -split '\|'

    $State = if ($Parts.Count -ge 1) { $Parts[0] } else { "unknown" }
    $Health = if ($Parts.Count -ge 2) { $Parts[1] } else { "unknown" }
    $RestartCount = if ($Parts.Count -ge 3) { $Parts[2] } else { "unknown" }
    $ExitCode = if ($Parts.Count -ge 4) { $Parts[3] } else { "unknown" }

    if ($State -eq "running" -and $Health -in @("healthy", "none")) {
        Add-Result `
            -Area "容器" `
            -Item "$LogicalName / $ServiceName" `
            -Status "PASS" `
            -Detail "state=$State，health=$Health，restart=$RestartCount"
    }
    elseif ($State -eq "running" -and $Health -eq "starting") {
        Add-Result `
            -Area "容器" `
            -Item "$LogicalName / $ServiceName" `
            -Status "WARN" `
            -Detail "容器正在运行，但健康检查仍为 starting"
    }
    else {
        Add-Result `
            -Area "容器" `
            -Item "$LogicalName / $ServiceName" `
            -Status "FAIL" `
            -Detail "state=$State，health=$Health，restart=$RestartCount，exit=$ExitCode"
    }
}

function Test-HttpEndpoint {
    param(
        [string]$Area,
        [string]$Item,
        [string]$Uri,
        [string]$EvidenceName,
        [int]$TimeoutSeconds = 20
    )

    $EvidencePath = Join-Path $EvidenceDir $EvidenceName

    try {
        $Response = Invoke-WebRequest `
            -Uri $Uri `
            -Method Get `
            -UseBasicParsing `
            -TimeoutSec $TimeoutSeconds

        $Body = [string]$Response.Content

        $Body |
            Set-Content `
                -Path $EvidencePath `
                -Encoding UTF8

        if ($Response.StatusCode -eq 200) {
            $Preview = $Body.Replace("`r", " ").Replace("`n", " ")

            if ($Preview.Length -gt 180) {
                $Preview = $Preview.Substring(0, 180) + "..."
            }

            Add-Result `
                -Area $Area `
                -Item $Item `
                -Status "PASS" `
                -Detail "HTTP 200；响应：$Preview"
        }
        else {
            Add-Result `
                -Area $Area `
                -Item $Item `
                -Status "FAIL" `
                -Detail "HTTP $($Response.StatusCode)"
        }
    }
    catch {
        $StatusCode = $null

        if ($_.Exception.Response) {
            try {
                $StatusCode = [int]$_.Exception.Response.StatusCode
            }
            catch {
                $StatusCode = $null
            }
        }

        if ($null -ne $StatusCode) {
            Add-Result `
                -Area $Area `
                -Item $Item `
                -Status "FAIL" `
                -Detail "HTTP $StatusCode；$($_.Exception.Message)"
        }
        else {
            Add-Result `
                -Area $Area `
                -Item $Item `
                -Status "FAIL" `
                -Detail $_.Exception.Message
        }
    }
}

Write-Log "============================================================"
Write-Log "RAG 第二阶段：基础设施一次性只读检查"
Write-Log "测试时间：$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz')"
Write-Log "项目目录：$Root"
Write-Log "============================================================"

Write-Log ""
Write-Log "===== 1. Docker Compose 服务识别 ====="

$ServicesOutput = docker compose config --services 2>&1
$ServicesExit = $LASTEXITCODE

$Services = @(
    $ServicesOutput |
    ForEach-Object { "$_".Trim() } |
    Where-Object {
        -not [string]::IsNullOrWhiteSpace($_) -and
        $_ -match '^[A-Za-z0-9_.-]+$'
    }
)

if ($ServicesExit -eq 0 -and $Services.Count -gt 0) {
    Add-Result `
        -Area "Compose" `
        -Item "服务解析" `
        -Status "PASS" `
        -Detail "识别到 $($Services.Count) 个服务：$($Services -join ', ')"
}
else {
    Add-Result `
        -Area "Compose" `
        -Item "服务解析" `
        -Status "FAIL" `
        -Detail (($ServicesOutput | Out-String).Trim())
}

$PostgresService = Find-Service `
    -Services $Services `
    -Patterns @('^postgres$', 'postgres', '^db$')

$MinioService = Find-Service `
    -Services $Services `
    -Patterns @('^minio$', 'minio')

$EtcdService = Find-Service `
    -Services $Services `
    -Patterns @('^etcd$', 'etcd')

$MilvusService = Find-Service `
    -Services $Services `
    -Patterns @('^milvus$', 'milvus', 'standalone')

$RagService = Find-Service `
    -Services $Services `
    -Patterns @('^rag-api$', 'rag-api', '^rag$', 'knowledge')

$MigrationService = Find-Service `
    -Services $Services `
    -Patterns @('migrat', 'alembic')

$ComposePsOutput = docker compose ps --all 2>&1
$ComposePsExit = $LASTEXITCODE

$ComposePsOutput |
    Set-Content `
        -Path (Join-Path $EvidenceDir "docker-compose-ps-all.txt") `
        -Encoding UTF8

if ($ComposePsExit -eq 0) {
    Add-Result `
        -Area "Compose" `
        -Item "docker compose ps --all" `
        -Status "PASS" `
        -Detail "容器状态已保存到 docker-compose-ps-all.txt"
}
else {
    Add-Result `
        -Area "Compose" `
        -Item "docker compose ps --all" `
        -Status "FAIL" `
        -Detail (($ComposePsOutput | Out-String).Trim())
}

Write-Log ""
Write-Log "===== 2. 核心容器状态 ====="

Test-ComposeService "PostgreSQL" $PostgresService
Test-ComposeService "MinIO" $MinioService
Test-ComposeService "etcd" $EtcdService
Test-ComposeService "Milvus" $MilvusService
Test-ComposeService "RAG API" $RagService

if (-not [string]::IsNullOrWhiteSpace($MigrationService)) {
    $MigrationContainer = (
        docker compose ps --all -q $MigrationService 2>&1 |
        Out-String
    ).Trim()

    if ([string]::IsNullOrWhiteSpace($MigrationContainer)) {
        Add-Result `
            -Area "迁移" `
            -Item $MigrationService `
            -Status "WARN" `
            -Detail "识别到迁移服务，但没有找到历史容器"
    }
    else {
        $MigrationInspect = (
            docker inspect `
                --format '{{.State.Status}}|{{.State.ExitCode}}|{{.RestartCount}}' `
                $MigrationContainer 2>&1 |
            Out-String
        ).Trim()

        $MigrationParts = $MigrationInspect -split '\|'
        $MigrationState = $MigrationParts[0]
        $MigrationExitCode = if ($MigrationParts.Count -ge 2) {
            $MigrationParts[1]
        }
        else {
            "unknown"
        }

        if (
            $MigrationState -eq "running" -or
            ($MigrationState -eq "exited" -and $MigrationExitCode -eq "0")
        ) {
            Add-Result `
                -Area "迁移" `
                -Item $MigrationService `
                -Status "PASS" `
                -Detail "state=$MigrationState，exit=$MigrationExitCode"
        }
        else {
            Add-Result `
                -Area "迁移" `
                -Item $MigrationService `
                -Status "FAIL" `
                -Detail "state=$MigrationState，exit=$MigrationExitCode"
        }
    }
}
else {
    Add-Result `
        -Area "迁移" `
        -Item "Compose 迁移服务" `
        -Status "WARN" `
        -Detail "未识别到独立迁移服务；仍将通过本地 Alembic 检查版本"
}

Write-Log ""
Write-Log "===== 3. PostgreSQL ====="

if ([string]::IsNullOrWhiteSpace($PostgresService)) {
    Add-Result `
        -Area "PostgreSQL" `
        -Item "连接检查" `
        -Status "FAIL" `
        -Detail "未识别到 PostgreSQL Compose 服务"
}
else {
    $PgReadyOutput = docker compose exec -T $PostgresService `
        sh -lc 'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"' 2>&1

    $PgReadyExit = $LASTEXITCODE
    $PgReadyText = ($PgReadyOutput | Out-String).Trim()

    $PgReadyText |
        Set-Content `
            -Path (Join-Path $EvidenceDir "postgres-pg-isready.txt") `
            -Encoding UTF8

    if ($PgReadyExit -eq 0) {
        Add-Result `
            -Area "PostgreSQL" `
            -Item "pg_isready" `
            -Status "PASS" `
            -Detail $PgReadyText
    }
    else {
        Add-Result `
            -Area "PostgreSQL" `
            -Item "pg_isready" `
            -Status "FAIL" `
            -Detail $PgReadyText
    }

    $PgQueryOutput = docker compose exec -T $PostgresService `
        sh -lc 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -X -P pager=off -Atc "SHOW server_version; SELECT current_database(); SELECT current_user; SELECT 1;"' 2>&1

    $PgQueryExit = $LASTEXITCODE
    $PgQueryText = ($PgQueryOutput | Out-String).Trim()

    $PgQueryText |
        Set-Content `
            -Path (Join-Path $EvidenceDir "postgres-readonly-query.txt") `
            -Encoding UTF8

    if ($PgQueryExit -eq 0 -and $PgQueryText -match '(^|\r?\n)1(\r?\n|$)') {
        Add-Result `
            -Area "PostgreSQL" `
            -Item "只读 SQL" `
            -Status "PASS" `
            -Detail "数据库版本、数据库名、当前用户及 SELECT 1 查询成功"
    }
    else {
        Add-Result `
            -Area "PostgreSQL" `
            -Item "只读 SQL" `
            -Status "FAIL" `
            -Detail $PgQueryText
    }
}

Write-Log ""
Write-Log "===== 4. MinIO ====="

Test-HttpEndpoint `
    -Area "MinIO" `
    -Item "Live" `
    -Uri "http://127.0.0.1:9000/minio/health/live" `
    -EvidenceName "minio-live.txt"

Test-HttpEndpoint `
    -Area "MinIO" `
    -Item "Ready" `
    -Uri "http://127.0.0.1:9000/minio/health/ready" `
    -EvidenceName "minio-ready.txt"

Write-Log ""
Write-Log "===== 5. etcd ====="

if ([string]::IsNullOrWhiteSpace($EtcdService)) {
    Add-Result `
        -Area "etcd" `
        -Item "endpoint health" `
        -Status "FAIL" `
        -Detail "未识别到 etcd Compose 服务"
}
else {
    $EtcdOutput = docker compose exec -T $EtcdService `
        sh -lc 'ETCDCTL_API=3 etcdctl endpoint health' 2>&1

    $EtcdExit = $LASTEXITCODE
    $EtcdText = ($EtcdOutput | Out-String).Trim()

    $EtcdText |
        Set-Content `
            -Path (Join-Path $EvidenceDir "etcd-endpoint-health.txt") `
            -Encoding UTF8

    if ($EtcdExit -eq 0 -and $EtcdText -match 'healthy|successfully committed') {
        Add-Result `
            -Area "etcd" `
            -Item "endpoint health" `
            -Status "PASS" `
            -Detail $EtcdText
    }
    else {
        Add-Result `
            -Area "etcd" `
            -Item "endpoint health" `
            -Status "FAIL" `
            -Detail $EtcdText
    }
}

Write-Log ""
Write-Log "===== 6. Milvus ====="

Test-HttpEndpoint `
    -Area "Milvus" `
    -Item "HTTP healthz" `
    -Uri "http://127.0.0.1:9091/healthz" `
    -EvidenceName "milvus-healthz.txt"

$TcpClient = New-Object System.Net.Sockets.TcpClient

try {
    $AsyncResult = $TcpClient.BeginConnect(
        "127.0.0.1",
        19530,
        $null,
        $null
    )

    $ConnectedInTime = $AsyncResult.AsyncWaitHandle.WaitOne(
        3000,
        $false
    )

    if ($ConnectedInTime) {
        $TcpClient.EndConnect($AsyncResult)

        Add-Result `
            -Area "Milvus" `
            -Item "gRPC 19530" `
            -Status "PASS" `
            -Detail "TCP 连接成功"
    }
    else {
        Add-Result `
            -Area "Milvus" `
            -Item "gRPC 19530" `
            -Status "FAIL" `
            -Detail "3 秒内无法建立 TCP 连接"
    }
}
catch {
    Add-Result `
        -Area "Milvus" `
        -Item "gRPC 19530" `
        -Status "FAIL" `
        -Detail $_.Exception.Message
}
finally {
    $TcpClient.Close()
}

Write-Log ""
Write-Log "===== 7. RAG API ====="

Test-HttpEndpoint `
    -Area "RAG API" `
    -Item "GET /health" `
    -Uri "http://127.0.0.1:8000/health" `
    -EvidenceName "rag-health.json" `
    -TimeoutSeconds 30

Test-HttpEndpoint `
    -Area "RAG API" `
    -Item "GET /ready" `
    -Uri "http://127.0.0.1:8000/ready" `
    -EvidenceName "rag-ready.json" `
    -TimeoutSeconds 60

Write-Log ""
Write-Log "===== 8. Alembic current 与 heads ====="

$ServicePath = Join-Path $Root "law-rag-service"
$ServicePython = Join-Path $ServicePath ".venv\Scripts\python.exe"

if (-not (Test-Path $ServicePython)) {
    Add-Result `
        -Area "Alembic" `
        -Item "本地解释器" `
        -Status "FAIL" `
        -Detail "law-rag-service\.venv\Scripts\python.exe 不存在"
}
else {
    Push-Location $ServicePath

    try {
        $CurrentOutput = & $ServicePython -m alembic current 2>&1
        $CurrentExit = $LASTEXITCODE
        $CurrentText = ($CurrentOutput | Out-String).Trim()

        $CurrentText |
            Set-Content `
                -Path (Join-Path $EvidenceDir "alembic-current.txt") `
                -Encoding UTF8

        $HeadsOutput = & $ServicePython -m alembic heads 2>&1
        $HeadsExit = $LASTEXITCODE
        $HeadsText = ($HeadsOutput | Out-String).Trim()

        $HeadsText |
            Set-Content `
                -Path (Join-Path $EvidenceDir "alembic-heads.txt") `
                -Encoding UTF8

        if ($CurrentExit -eq 0) {
            Add-Result `
                -Area "Alembic" `
                -Item "current" `
                -Status "PASS" `
                -Detail $CurrentText
        }
        else {
            Add-Result `
                -Area "Alembic" `
                -Item "current" `
                -Status "FAIL" `
                -Detail $CurrentText
        }

        if ($HeadsExit -eq 0) {
            $HeadLines = @(
                $HeadsText -split "`r?`n" |
                Where-Object {
                    -not [string]::IsNullOrWhiteSpace($_)
                }
            )

            if ($HeadLines.Count -eq 1) {
                Add-Result `
                    -Area "Alembic" `
                    -Item "heads" `
                    -Status "PASS" `
                    -Detail $HeadsText
            }
            else {
                Add-Result `
                    -Area "Alembic" `
                    -Item "heads" `
                    -Status "FAIL" `
                    -Detail "检测到 $($HeadLines.Count) 个 head：$HeadsText"
            }
        }
        else {
            Add-Result `
                -Area "Alembic" `
                -Item "heads" `
                -Status "FAIL" `
                -Detail $HeadsText
        }

        if (
            $CurrentExit -eq 0 -and
            $HeadsExit -eq 0 -and
            $CurrentText -match '\(head\)'
        ) {
            Add-Result `
                -Area "Alembic" `
                -Item "current = head" `
                -Status "PASS" `
                -Detail "当前数据库迁移版本已经位于 head"
        }
        else {
            Add-Result `
                -Area "Alembic" `
                -Item "current = head" `
                -Status "FAIL" `
                -Detail "current 输出未显示 (head)，数据库可能未迁移到最新版本"
        }
    }
    finally {
        Pop-Location
    }
}

Write-Log ""
Write-Log "===== 9. 最终汇总 ====="

$Results |
    Export-Csv `
        -Path $SummaryFile `
        -NoTypeInformation `
        -Encoding UTF8

$PassCount = @(
    $Results |
    Where-Object Status -eq "PASS"
).Count

$WarnCount = @(
    $Results |
    Where-Object Status -eq "WARN"
).Count

$FailCount = @(
    $Results |
    Where-Object Status -eq "FAIL"
).Count

if ($FailCount -gt 0) {
    $Overall = "FAIL"
}
elseif ($WarnCount -gt 0) {
    $Overall = "PASS_WITH_WARNINGS"
}
else {
    $Overall = "PASS"
}

Write-Log ""
Write-Log "PASS：$PassCount"
Write-Log "WARN：$WarnCount"
Write-Log "FAIL：$FailCount"
Write-Log "第二阶段最终结果：$Overall"

Write-Host ""
Write-Host "================ 第二阶段汇总 ================"
Write-Host "PASS：$PassCount"
Write-Host "WARN：$WarnCount"
Write-Host "FAIL：$FailCount"
Write-Host "总体结果：$Overall"
Write-Host ""

$Issues = @(
    $Results |
    Where-Object Status -ne "PASS"
)

if ($Issues.Count -gt 0) {
    Write-Host "异常和警告："

    $Issues |
        Format-Table `
            Area,
            Item,
            Status,
            Detail `
            -Wrap `
            -AutoSize
}
else {
    Write-Host "未发现异常或警告。"
}

Write-Host ""
Write-Host "全部检查项："

$Results |
    Format-Table `
        Area,
        Item,
        Status,
        Detail `
        -Wrap `
        -AutoSize

Write-Host ""
Write-Host "证据目录：$EvidenceDir"
