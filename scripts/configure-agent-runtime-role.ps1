param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[A-Za-z_][A-Za-z0-9_]{0,62}$')]
    [string]$AgentUser,

    [Parameter(Mandatory = $true)]
    [ValidateLength(16, 256)]
    [string]$AgentPassword,

    [string]$PostgresContainer = 'law-rag-postgres',
    [string]$Database = 'law_rag',
    [string]$AdminUser = 'law_rag_user',

    [Parameter(Mandatory = $true)]
    [string]$AdminPassword
)

$ErrorActionPreference = 'Stop'

$sql = @'
SELECT format('CREATE ROLE %I LOGIN PASSWORD %L', :'agent_user', :'agent_password')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'agent_user')
\gexec
SELECT format('ALTER ROLE %I LOGIN PASSWORD %L', :'agent_user', :'agent_password')
\gexec
SELECT format('GRANT CONNECT ON DATABASE %I TO %I', current_database(), :'agent_user')
\gexec
SELECT format('GRANT USAGE, CREATE ON SCHEMA agent_runtime TO %I', :'agent_user')
\gexec
SELECT format('REVOKE ALL ON SCHEMA oa FROM %I', :'agent_user')
\gexec
SELECT format('REVOKE ALL ON ALL TABLES IN SCHEMA oa FROM %I', :'agent_user')
\gexec
SELECT format('REVOKE ALL ON ALL SEQUENCES IN SCHEMA oa FROM %I', :'agent_user')
\gexec
'@

$running = docker inspect --format '{{.State.Running}}' $PostgresContainer 2>$null
if ($LASTEXITCODE -ne 0 -or $running -ne 'true') {
    throw "PostgreSQL 容器 $PostgresContainer 未运行。"
}

$sql | docker exec -i `
    -e "PGPASSWORD=$AdminPassword" `
    $PostgresContainer `
    psql --set ON_ERROR_STOP=1 `
    --username $AdminUser `
    --dbname $Database `
    --variable "agent_user=$AgentUser" `
    --variable "agent_password=$AgentPassword"

if ($LASTEXITCODE -ne 0) {
    throw 'agent_runtime 数据库角色配置失败。'
}

Write-Host "agent_runtime 独立角色 $AgentUser 已配置；该角色未获得 oa schema 权限。"
