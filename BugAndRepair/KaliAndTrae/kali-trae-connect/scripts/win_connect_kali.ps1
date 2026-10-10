<#
.SYNOPSIS
  在 Trae 所在机器上一键配置到 Kali 的 SSH（写别名 + 装公钥 + 免密验证）。

.DESCRIPTION
  步骤：① 确认 22 端口可达 → ② 生成/复用 ed25519 密钥 → ③ 把 Host 块写进 ~/.ssh/config
  （幂等，替换同名块）→ ④ 把公钥追加到 Kali 的 authorized_keys（只需输一次 Kali 密码）
  → ⑤ 免密验证。

  别名一律小写：Trae Remote SSH 对含大写字母的主机名有连接超时 bug。

.PARAMETER Target
  Kali 的 IP。桥接模式下填 Kali 的局域网 IP；NAT 模式下填「宿主机 IP」并用 -Port 指到转发端口。
.PARAMETER User
  Kali 的登录用户名（安装系统时创建的普通账号，不是 root）。
.PARAMETER Port
  SSH 端口，默认 22。
.PARAMETER Alias
  ssh 别名，默认 kali（全小写）。
.PARAMETER DryRun
  只预览将做什么，不写任何文件、不装公钥。

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File win_connect_kali.ps1 -Target 192.168.1.240 -User xiaoying
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File win_connect_kali.ps1 -Target 192.168.1.240 -User xiaoying -DryRun
#>
[CmdletBinding()]
param(
  [Parameter(Mandatory = $true)][string]$Target,
  [Parameter(Mandatory = $true)][string]$User,
  [int]$Port = 22,
  [string]$Alias = 'kali',
  [switch]$DryRun
)

$ErrorActionPreference = 'Stop'

function Info($m) { Write-Host $m }
function Fail($m) { Write-Host $m -ForegroundColor Red; exit 1 }

if ($Alias -cne $Alias.ToLower()) {
  Info "提示：别名含大写（$Alias），Trae 对含大写主机名有超时 bug，已自动改为 $($Alias.ToLower())"
  $Alias = $Alias.ToLower()
}

$sshDir = Join-Path $env:USERPROFILE '.ssh'
$config = Join-Path $sshDir 'config'
$key    = Join-Path $sshDir 'id_ed25519'
$pub    = "$key.pub"

if (-not (Test-Path $sshDir)) {
  if ($DryRun) { Info "[DryRun] 将创建目录 $sshDir" }
  else { New-Item -ItemType Directory -Force -Path $sshDir | Out-Null }
}

# ① 端口可达性
Info "==> 检查 $Target`:$Port 是否可达 ..."
if (-not (Test-NetConnection -ComputerName $Target -Port $Port -InformationLevel Quiet)) {
  Fail @"
无法连接 $Target`:$Port，请依次排查：
  - 虚拟机网络模式：NAT / 仅主机 无法被本机直连 —— 改成「桥接」，或在虚拟机软件里做端口转发（宿主端口 → Kali:22）
  - Kali 上 SSH 是否已开（在 Kali 执行）： sudo systemctl enable --now ssh
  - 防火墙，或路由器「AP 隔离」拦住了跨设备访问
"@
}
Info "    可达。"

# ② 密钥（复用优先；没有才生成无口令密钥）
if (-not (Test-Path $key)) {
  Info "==> 未找到 $key，生成一把无口令 ed25519 密钥 ..."
  if ($DryRun) { Info "[DryRun] 将执行： ssh-keygen -t ed25519 -q -N <empty> -f $key" }
  else {
    # PowerShell 5.1 会丢弃 -N "" 的空参数，必须写成 -N '""'（实测）
    ssh-keygen -t ed25519 -q -N '""' -f $key
    if (-not (Test-Path $key)) { Fail "ssh-keygen 失败，请手动执行： ssh-keygen -t ed25519 -f `"$key`"" }
    Info "    已生成 $key"
  }
} else {
  Info "==> 复用已有密钥 $key"
}

# ③ 写入 ~/.ssh/config（替换同名 Host 块，幂等）
$block = @(
  "Host $Alias",
  "  HostName $Target",
  "  User $User",
  "  Port $Port",
  "  ServerAliveInterval 30",
  "  ServerAliveCountMax 3"
)
if ($DryRun) {
  Info "==> [DryRun] 将把以下内容写入 $config"
  $block | ForEach-Object { Info "      $_" }
} else {
  if (Test-Path $config) {
    Copy-Item $config "$config.bak-$(Get-Date -Format yyyyMMddHHmmss)" -Force
    $lines = Get-Content $config
  } else { $lines = @() }
  $out = New-Object System.Collections.Generic.List[string]
  $skip = $false
  foreach ($l in $lines) {
    if ($l -match ('^Host\s+' + [regex]::Escape($Alias) + '\s*$')) { $skip = $true; continue }
    if ($skip -and $l -match '^Host\s+') { $skip = $false }
    if (-not $skip) { $out.Add($l) }
  }
  $out.Add('')
  $block | ForEach-Object { $out.Add($_) }
  [IO.File]::WriteAllText($config, ($out -join "`r`n") + "`r`n")   # 无 BOM
  Info "==> 已写入 $config （Host $Alias）"
}

# ④ 安装公钥（免密登录）
ssh -o BatchMode=yes -o ConnectTimeout=8 -p $Port "$User@$Target" 'echo ok' 2>$null | Out-Null
if ($LASTEXITCODE -eq 0) {
  Info "==> 免密登录已可用，跳过公钥安装"
} elseif ($DryRun) {
  Info "==> [DryRun] 将把 $pub 装到 $User@$Target 的 ~/.ssh/authorized_keys（会提示输一次 Kali 密码）"
} else {
  Info "==> 安装公钥到 Kali（接下来会提示输入一次 Kali 密码）..."
  $remote = 'mkdir -p ~/.ssh && chmod 700 ~/.ssh && cat >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys'
  Get-Content $pub -Raw | ssh -p $Port -o StrictHostKeyChecking=accept-new "$User@$Target" $remote
}

if ($DryRun) { Info "`n[DryRun] 已完成预览，未做任何修改。"; exit 0 }

# ⑤ 免密验证
Info "==> 免密验证 ..."
ssh -o BatchMode=yes -o ConnectTimeout=8 $Alias 'echo "主机: $(hostname)  用户: $(whoami)"; sudo -n true 2>/dev/null && echo "sudo: 免密可用" || echo "sudo: 需要密码"'
if ($LASTEXITCODE -ne 0) { Fail "免密登录验证失败，请检查上面的输出（或重跑本脚本）。" }

Info @"

✅ 配置完成。下一步在 Trae 里：
   1) Ctrl+Shift+P → Remote-SSH: Connect to Host → 选 $Alias
   2) 首次连接选远端平台 Linux；Trae 会下载约 300MB 服务端并解压（约 1~2 分钟，不是卡死）
   3) 之后 AI 的终端 / 文件操作直接在 Kali 里；也可让 AI 执行： ssh $Alias "命令"

   让 AI 免密跑 root 命令（可选）：见 SKILL.md 第 4 步。
"@
