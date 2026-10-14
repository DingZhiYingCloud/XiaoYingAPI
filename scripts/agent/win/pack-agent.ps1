# =============================================================================
# pack-agent.ps1 —— 把「开发版」明文 ai-agent.ps1 打包成「生产版」（加密）
#
# 用法：
#   .\pack-agent.ps1                                        # 内嵌口令（旧模式）
#   .\pack-agent.ps1 -Online -Brain https://大脑域名/ai-brain   # ★ 在线取口令（推荐）
#   .\pack-agent.ps1 -Key 'pass' -Out dist\ai-agent.ps1
#
# 与 Linux 版工具同思路：正文 AES-256-CBC + PBKDF2-SHA256 加密；--Online 时**文件里不存密钥**，
# 运行时凭「注册口令」向大脑 POST /agent/key 换取；密文加 HMAC-SHA256 完整性校验；密文切 4 段藏进随机变量。
# 边界（说到做到）：--Online 能挡住“拷走文件”，但本机拿到权限的人仍可从运行中的进程取到明文。
# =============================================================================
param(
    [string]$Source = 'ai-agent.ps1',
    [string]$Out = '',
    [string]$Key = '',
    [int]$Iter = 600000,
    [switch]$Online,
    [string]$Brain = ''
)
$ErrorActionPreference = 'Stop'
$Here = $PSScriptRoot

if (-not [IO.Path]::IsPathRooted($Source)) { $Source = Join-Path $Here $Source }
if (-not (Test-Path $Source)) { Write-Host ("找不到源文件：" + $Source) -ForegroundColor Red; exit 1 }
if (-not $Out) { $Out = Join-Path $Here 'dist\ai-agent.ps1' }
elseif (-not [IO.Path]::IsPathRooted($Out)) { $Out = Join-Path $Here $Out }
[void](New-Item -ItemType Directory -Force -Path (Split-Path $Out -Parent))

# ---------- 口令 ----------
$KeyFile = Join-Path $Here 'pack.key'
if ($Online) {
    if (-not $Brain) { Write-Host '-Online 必须给 -Brain https://域名/路径' -ForegroundColor Red; exit 1 }
    if (-not $Key) {
        $bc = Join-Path $HOME '.ai-brain\brain.conf'
        if (Test-Path $bc) {
            foreach ($l in [IO.File]::ReadAllLines($bc)) { if ($l -match '^\s*PACK_KEY\s*=\s*(.*)$') { $Key = $Matches[1].Trim() } }
        }
    }
    if (-not $Key) { Write-Host '读不到大脑的 PACK_KEY：请先 brain init，或用 -Key 指定' -ForegroundColor Red; exit 1 }
} elseif (-not $Key) {
    if (Test-Path $KeyFile) { $Key = ([IO.File]::ReadAllText($KeyFile)).Trim() }
    else {
        $bytes = New-Object byte[] 36
        ([System.Security.Cryptography.RandomNumberGenerator]::Create()).GetBytes($bytes)
        $Key = [Convert]::ToBase64String($bytes)
        [IO.File]::WriteAllText($KeyFile, $Key, (New-Object Text.UTF8Encoding($false)))
        Write-Host ("已生成打包口令 -> " + $KeyFile + "（请保管好）")
    }
}

# ---------- 读源（UTF-8，可带 BOM）→ 加密 ----------
$src = [IO.File]::ReadAllText($Source, [Text.Encoding]::UTF8)
$pt = [Text.Encoding]::UTF8.GetBytes($src)

$rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
$salt = New-Object byte[] 16; $rng.GetBytes($salt)
$iv = New-Object byte[] 16; $rng.GetBytes($iv)
$kdf = New-Object System.Security.Cryptography.Rfc2898DeriveBytes($Key, $salt, $Iter, [System.Security.Cryptography.HashAlgorithmName]::SHA256)
$k = $kdf.GetBytes(32)
$aes = [System.Security.Cryptography.Aes]::Create()
$aes.Mode = 'CBC'; $aes.Padding = 'PKCS7'; $aes.Key = $k; $aes.IV = $iv
$enc = $aes.CreateEncryptor()
$ct = $enc.TransformFinalBlock($pt, 0, $pt.Length)
$hm = New-Object System.Security.Cryptography.HMACSHA256
$hm.Key = $k
$mac = -join ($hm.ComputeHash($ct) | ForEach-Object { $_.ToString('x2') })

$blob = [Convert]::ToBase64String(($salt + $iv + $ct))
$q = [int][Math]::Ceiling($blob.Length / 4.0)
$b1 = $blob.Substring(0, $q)
$b2 = $blob.Substring($q, [Math]::Min($q, $blob.Length - $q))
$start3 = [Math]::Min($q * 2, $blob.Length)
$b3 = $blob.Substring($start3, [Math]::Min($q, $blob.Length - $start3))
$b4 = $blob.Substring([Math]::Min($q * 3, $blob.Length))

# 随机变量名
function RN { return ('_' + (-join (1..4 | ForEach-Object { '{0:x2}' -f (Get-Random -Maximum 256) }))) }
$v1 = RN; $v2 = RN; $v3 = RN; $v4 = RN

# ---------- 口令获取块 ----------
if ($Online) {
    $getkey = @'
$gh = $env:AI_AGENT_HOME
if (-not $gh) {
    $pd = Join-Path $env:ProgramData '.ai-agent'
    $adm = (New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    if ((Test-Path (Join-Path $pd 'agent.conf')) -or $adm) { $gh = $pd } else { $gh = Join-Path $env:LOCALAPPDATA '.ai-agent' }
}
$cf = Join-Path $gh 'agent.conf'
$br = $env:AI_AGENT_BRAIN
if (-not $br -and (Test-Path $cf)) { foreach ($l in [IO.File]::ReadAllLines($cf)) { if ($l -match '^\s*BRAIN_URL\s*=\s*(.*)$') { $br = $Matches[1].Trim() } } }
if (-not $br) { $br = '@BRAIN@' }
# 取口令：优先命令行 --secret（让 `setup --secret …` 能零交互；loader 先于内层脚本跑，看不到内层参数）
$asec = ''
for ($i = 0; $i -lt ($args.Count - 1); $i++) { if ("$($args[$i])" -eq '--secret') { $asec = "$($args[$i + 1])" } }
$sec = $asec
if (-not $sec) { $sec = $env:AI_AGENT_PACK_SECRET }
if (-not $sec -and (Test-Path $cf)) { foreach ($l in [IO.File]::ReadAllLines($cf)) { if ($l -match '^\s*PACK_SECRET\s*=\s*(.*)$') { $sec = $Matches[1].Trim() } } }
if (-not $sec) {
    if ([Console]::IsInputRedirected) { [Console]::Error.WriteLine('fresh start: pass --secret <enroll-secret> or set env AI_AGENT_PACK_SECRET'); exit 1 }
    $sec = Read-Host 'first start: enrollment secret (used to fetch the key)'
}
if (-not $sec) { [Console]::Error.WriteLine('need enrollment secret'); exit 1 }
$K = ''; $KOLD = ''
for ($i = 0; $i -lt 3; $i++) {
    try {
        $body = [Text.Encoding]::UTF8.GetBytes('secret=' + [uri]::EscapeDataString($sec))
        $req = [System.Net.HttpWebRequest]::Create($br + '/agent/key')
        $req.Method = 'POST'; $req.ContentType = 'application/x-www-form-urlencoded'
        $req.UserAgent = 'Mozilla/5.0'; $req.Timeout = 10000; $req.ContentLength = $body.Length
        $st = $req.GetRequestStream(); $st.Write($body, 0, $body.Length); $st.Close()
        $resp = $req.GetResponse(); $sr = New-Object IO.StreamReader($resp.GetResponseStream())
        $js = $sr.ReadToEnd(); $sr.Close(); $resp.Close()
        $o = $js | ConvertFrom-Json
        $K = $o.key; $KOLD = $o.old
    } catch {}
    if ($K) { break }
    Start-Sleep -Seconds 3
}
if (-not $K) { [Console]::Error.WriteLine('cannot fetch key'); exit 1 }
try {
    if (-not (Test-Path $cf)) { New-Item -ItemType Directory -Force -Path $gh | Out-Null }
    if (-not (Test-Path $cf) -or -not (Select-String -Path $cf -Pattern '^PACK_SECRET=' -Quiet -ErrorAction SilentlyContinue)) {
        [IO.File]::AppendAllText($cf, ('PACK_SECRET=' + $sec + "`r`n"), (New-Object Text.UTF8Encoding($false)))
    }
} catch {}
'@
    $getkey = $getkey.Replace('@BRAIN@', $Brain.TrimEnd('/'))
} else {
    function R13 ($s) {
        $o = ''
        foreach ($c in $s.ToCharArray()) {
            $n = [int]$c
            if ($n -ge 65 -and $n -le 90) { $o += [char](((($n - 65) + 13) % 26) + 65) }
            elseif ($n -ge 97 -and $n -le 122) { $o += [char](((($n - 97) + 13) % 26) + 97) }
            else { $o += $c }
        }
        return $o
    }
    $ka = [int][Math]::Ceiling($Key.Length / 3.0)
    $p1 = $Key.Substring(0, [Math]::Min($ka, $Key.Length))
    $p2 = if ($Key.Length -gt $ka) { $Key.Substring($ka, [Math]::Min($ka, $Key.Length - $ka)) } else { '' }
    $p3 = if ($Key.Length -gt ($ka * 2)) { $Key.Substring($ka * 2) } else { '' }
    $k1 = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($p1))
    $k2 = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes((R13 $p2)))
    $k3 = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes((R13 $p3)))
    $getkey = @"
function _r13(`$s){ `$o=''; foreach(`$c in `$s.ToCharArray()){ `$n=[int]`$c; if(`$n -ge 65 -and `$n -le 90){ `$o += [char](((`$n-65+13)%26)+65) } elseif(`$n -ge 97 -and `$n -le 122){ `$o += [char](((`$n-97+13)%26)+97) } else { `$o += `$c } }; `$o }
`$p1 = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('$k1'))
`$p2 = _r13 ([Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('$k2')))
`$p3 = _r13 ([Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('$k3')))
`$K = `$p1 + `$p2 + `$p3
`$KOLD = ''
"@
}

# ---------- 生成 loader ----------
$loader = @'
# ---- runtime (do not edit) ----
$ErrorActionPreference = 'Stop'
try { [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.SecurityProtocolType]'Tls12, Tls13' } catch {}
try { [Console]::OutputEncoding = New-Object Text.UTF8Encoding($false) } catch {}
$self = $PSCommandPath
if (-not $self) { $self = $MyInvocation.MyCommand.Path }
if ($self) { $env:AI_AGENT_SELF = $self }

@GETKEY@

$@V1@ = '@B1@'
$@V2@ = '@B2@'
$@V3@ = '@B3@'
$@V4@ = '@B4@'
$b = $@V1@ + $@V2@ + $@V3@ + $@V4@
$raw = [Convert]::FromBase64String($b)
$salt = New-Object byte[] 16; [Array]::Copy($raw, 0, $salt, 0, 16)
$iv = New-Object byte[] 16; [Array]::Copy($raw, 16, $iv, 0, 16)
$ct = New-Object byte[] ($raw.Length - 32); [Array]::Copy($raw, 32, $ct, 0, $ct.Length)
function _dk($k){ (New-Object System.Security.Cryptography.Rfc2898DeriveBytes($k, $salt, @ITER@, [System.Security.Cryptography.HashAlgorithmName]::SHA256)).GetBytes(32) }
function _mac($k){ $h = New-Object System.Security.Cryptography.HMACSHA256; $h.Key = $k; return (-join ($h.ComputeHash($ct) | ForEach-Object { $_.ToString('x2') })) }
$K2 = _dk $K
if ((_mac $K2) -ne '@MAC@' -and $KOLD) { $K2 = _dk $KOLD }
if ((_mac $K2) -ne '@MAC@') { [Console]::Error.WriteLine('package error'); exit 1 }
$a = [System.Security.Cryptography.Aes]::Create()
$a.Mode = 'CBC'; $a.Padding = 'PKCS7'; $a.Key = $K2; $a.IV = $iv
$dec = $a.CreateDecryptor()
try { $pt = $dec.TransformFinalBlock($ct, 0, $ct.Length) } catch { [Console]::Error.WriteLine('package error'); exit 1 }
$text = [Text.Encoding]::UTF8.GetString($pt)
if (-not $text) { [Console]::Error.WriteLine('package error'); exit 1 }
$sb = [ScriptBlock]::Create($text)
& $sb @args
'@

$loader = $loader.Replace('@GETKEY@', $getkey.Trim("`r", "`n"))
$loader = $loader.Replace('@ITER@', "$Iter")
$loader = $loader.Replace('@MAC@', $mac)
$loader = $loader.Replace('@V1@', $v1).Replace('@V2@', $v2).Replace('@V3@', $v3).Replace('@V4@', $v4)
$loader = $loader.Replace('@B1@', $b1).Replace('@B2@', $b2).Replace('@B3@', $b3).Replace('@B4@', $b4)

[IO.File]::WriteAllText($Out, $loader, (New-Object Text.UTF8Encoding($true)))
Write-Host ("已生成加密生产版：" + $Out + "（" + (Get-Item $Out).Length + " 字节；模式 " + $(if ($Online) { '在线取密钥' } else { '内嵌口令' }) + "）")
