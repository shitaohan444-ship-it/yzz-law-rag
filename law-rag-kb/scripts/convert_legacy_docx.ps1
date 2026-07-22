<#
.SYNOPSIS
  把语料库里"伪装成 .docx"的旧格式文件批量转换为真正的 OOXML .docx。

.DESCRIPTION
  平台上传校验（knowledge-documents.service.ts validateKnowledgeFile）只接受真 docx
  （PK 头 + [Content_Types].xml + word/）。扫描发现语料中大量文件实为：
    - OLE 复合文档（Word 97-2003 .doc，魔数 D0CF11E0A1B11AE1）
    - RTF（{\rtf 开头）
    - Word 2003 XML（<?xml 开头的 WordprocessingML）
  本脚本用本机 Word COM（Word.Application）把它们另存为真 .docx：
    1. 魔数识别，真 docx 直接跳过（幂等，可反复运行）；
    2. Word 打开时强制禁用宏（AutomationSecurity=ForceDisable）；
    3. 转换产物先写临时文件，用 ZipFile 校验确为合法 docx 后才替换原文件；
    4. 原文件移动到 $BackupRoot（保留目录结构），失败文件原地不动；
    5. 全过程写 CSV 日志。

.PARAMETER Root
  语料根目录。

.PARAMETER BackupRoot
  旧格式原件的备份根目录（转换成功后原件移到这里，可按相对路径找回）。

.PARAMETER DryRun
  只扫描统计，不做任何转换/移动。

.EXAMPLE
  powershell -File convert_legacy_docx.ps1 -DryRun
  powershell -File convert_legacy_docx.ps1
  powershell -File convert_legacy_docx.ps1 -Root D:\corpus -BackupRoot D:\corpus_backup

.NOTES
  依赖本机安装的 Microsoft Word（Word.Application COM）。单个损坏文件可能让 Word
  卡住，脚本无单文件超时——若长时间无输出，Ctrl+C 后重跑即可（已转换的会跳过）。
#>
[CmdletBinding()]
param(
  [string]$Root = "C:\Users\17962\Desktop\法律法规",
  [string]$BackupRoot = "C:\Users\17962\Desktop\法律法规_旧格式备份",
  [switch]$DryRun
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.IO.Compression.FileSystem

$wdFormatXMLDocument = 12          # .docx（无宏）
$wdAlertsNone = 0
$msoAutomationSecurityForceDisable = 3

# ---------- 格式识别 ----------
function Get-LegacyKind([string]$Path) {
  $fs = [System.IO.File]::OpenRead($Path)
  try {
    $buf = New-Object byte[] 8
    $n = $fs.Read($buf, 0, 8)
  } finally { $fs.Dispose() }
  if ($n -ge 4 -and $buf[0] -eq 0x50 -and $buf[1] -eq 0x4B -and $buf[2] -eq 0x03 -and $buf[3] -eq 0x04) { return $null } # 真 docx (PK)
  if ($n -ge 8 -and $buf[0] -eq 0xD0 -and $buf[1] -eq 0xCF -and $buf[2] -eq 0x11 -and $buf[3] -eq 0xE0 `
            -and $buf[4] -eq 0xA1 -and $buf[5] -eq 0xB1 -and $buf[6] -eq 0x1A -and $buf[7] -eq 0xE1) { return 'ole-doc' }
  if ($n -ge 5 -and $buf[0] -eq 0x7B -and $buf[1] -eq 0x5C -and $buf[2] -eq 0x72 -and $buf[3] -eq 0x74 -and $buf[4] -eq 0x66) { return 'rtf' }       # {\rtf
  if ($n -ge 5 -and $buf[0] -eq 0x3C -and $buf[1] -eq 0x3F -and $buf[2] -eq 0x78 -and $buf[3] -eq 0x6D -and $buf[4] -eq 0x6C) { return 'wordml-xml' } # <?xml
  return 'unknown'
}

# ---------- 产物校验：合法 ZIP 且含 docx 必需部件 ----------
function Test-RealDocx([string]$Path) {
  try {
    $zip = [System.IO.Compression.ZipFile]::OpenRead($Path)
    try {
      $names = @($zip.Entries | ForEach-Object { $_.FullName })
      return ($names -contains '[Content_Types].xml') -and ($names -contains 'word/document.xml')
    } finally { $zip.Dispose() }
  } catch { return $false }
}

# ---------- Word 实例（复用；崩溃后重建）----------
$script:WordApp = $null
function Get-WordApp {
  if ($null -eq $script:WordApp) {
    Write-Host '启动 Word（后台、禁宏、禁弹窗）...'
    $script:WordApp = New-Object -ComObject Word.Application
    $script:WordApp.Visible = $false
    $script:WordApp.DisplayAlerts = $wdAlertsNone
    $script:WordApp.AutomationSecurity = $msoAutomationSecurityForceDisable
  }
  return $script:WordApp
}
function Reset-WordApp {
  if ($null -ne $script:WordApp) {
    try { $script:WordApp.Quit() } catch {}
    $script:WordApp = $null
  }
}

# ---------- 单文件转换（Word 崩溃时重建实例重试一次）----------
function Convert-ToDocx([string]$Source, [string]$TempTarget) {
  foreach ($attempt in 1..2) {
    $doc = $null
    try {
      $word = Get-WordApp
      # Open(FileName, ConfirmConversions, ReadOnly, AddToRecentFiles)
      $doc = $word.Documents.Open($Source, $false, $true, $false)
      $doc.SaveAs2($TempTarget, $wdFormatXMLDocument)
      $doc.Close($false); $doc = $null
      return $true
    } catch {
      if ($null -ne $doc) { try { $doc.Close($false) } catch {} }
      if ($attempt -eq 1) { Reset-WordApp; continue }
      throw
    }
  }
}

# ---------- 主流程 ----------
$rootFull = [System.IO.Path]::GetFullPath($Root)
$files = Get-ChildItem -LiteralPath $rootFull -Recurse -File -Filter *.docx
$total = $files.Count
Write-Host "扫描 $rootFull ，共 $total 个 .docx"

$results = New-Object System.Collections.Generic.List[object]
$counts = @{ ok = 0; convert = 0; failed = 0; unknown = 0 }
$i = 0

foreach ($f in $files) {
  $i++
  $kind = Get-LegacyKind $f.FullName
  if ($null -eq $kind) { $counts.ok++; continue }
  if ($kind -eq 'unknown') {
    $counts.unknown++
    $results.Add([pscustomobject]@{ Path = $f.FullName; Kind = 'unknown'; Status = 'skipped-unknown'; Error = '' })
    Write-Host "[$i/$total] $($f.Name) => 未知格式，跳过"
    continue
  }
  if ($DryRun) {
    $counts.convert++
    $results.Add([pscustomobject]@{ Path = $f.FullName; Kind = $kind; Status = 'dry-run'; Error = '' })
    if ($i % 200 -eq 0) { Write-Host "[$i/$total] ..." }
    continue
  }

  Write-Host "[$i/$total] $($f.Name) => $kind，转换中..."
  $tmp = Join-Path $f.DirectoryName ($f.BaseName + '.__converting.docx')
  # Word 会拒绝打开"扩展名与内容不符"的文件，先把原件复制成真实格式对应的
  # 扩展名（.doc/.rtf/.xml）再打开。
  $stageExt = @{ 'ole-doc' = '.doc'; 'rtf' = '.rtf'; 'wordml-xml' = '.xml' }[$kind]
  $stage = Join-Path $env:TEMP ('legacy_convert_' + [guid]::NewGuid().ToString('N') + $stageExt)
  try {
    if (Test-Path -LiteralPath $tmp) { Remove-Item -LiteralPath $tmp -Force }
    Copy-Item -LiteralPath $f.FullName -Destination $stage
    [void](Convert-ToDocx $stage $tmp)
    if (-not (Test-RealDocx $tmp)) { throw '产物不是合法 docx' }

    # 备份原件（保留相对路径），再落位转换产物
    $rel = $f.FullName.Substring($rootFull.Length).TrimStart('\')
    $backupPath = Join-Path $BackupRoot $rel
    New-Item -ItemType Directory -Force -Path (Split-Path $backupPath -Parent) | Out-Null
    Move-Item -LiteralPath $f.FullName -Destination $backupPath
    Move-Item -LiteralPath $tmp -Destination $f.FullName

    $counts.convert++
    $results.Add([pscustomobject]@{ Path = $f.FullName; Kind = $kind; Status = 'converted'; Error = '' })
  } catch {
    if (Test-Path -LiteralPath $tmp) { Remove-Item -LiteralPath $tmp -Force -ErrorAction SilentlyContinue }
    $counts.failed++
    $results.Add([pscustomobject]@{ Path = $f.FullName; Kind = $kind; Status = 'failed'; Error = $_.Exception.Message })
    Write-Warning "[$i/$total] $($f.Name) 转换失败：$($_.Exception.Message)"
  } finally {
    if (Test-Path -LiteralPath $stage) { Remove-Item -LiteralPath $stage -Force -ErrorAction SilentlyContinue }
  }
}

Reset-WordApp

$logPath = Join-Path $rootFull '_convert_legacy_log.csv'
$results | Export-Csv -LiteralPath $logPath -NoTypeInformation -Encoding UTF8
Write-Host ''
Write-Host "完成：真docx跳过 $($counts.ok)；转换成功 $($counts.convert)；失败 $($counts.failed)；未知格式 $($counts.unknown)"
Write-Host "日志：$logPath"
if (-not $DryRun -and $counts.convert -gt 0) { Write-Host "原件备份：$BackupRoot" }
if ($DryRun) { Write-Host '（DryRun 未做任何改动）' }
