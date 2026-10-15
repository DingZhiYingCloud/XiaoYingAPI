# -*- coding: utf-8 -*-
"""管理类子命令：init / serve / status / pending / approve / deny / release / stop / pubkey。

这些命令要么直接读写本机数据（init/release），要么通过 api 调本机服务。
"""
from __future__ import annotations

import os
import re
import shutil
import signal
import sys
import time
from pathlib import Path

from . import VERSION  # noqa: F401  （保留：便于外部/调试时统一从这里取版本号）
from . import conf as C
from . import api as apicli
from . import registry, rendezvous, secure, ui
from .store import audit, get_meta, init, q, set_meta, x
from .util import new_id, now


# ==================== 初始化 ====================
def cmd_init(conf) -> int:
    C.ensure_home()
    changed = False
    if not conf['BRAIN_ADMIN_TOKEN']:
        conf['BRAIN_ADMIN_TOKEN'] = new_id(48)
        changed = True
    if not conf['ENROLL_SECRET']:
        conf['ENROLL_SECRET'] = new_id(48)
        changed = True
    if not conf.get('PACK_KEY'):
        conf['PACK_KEY'] = new_id(48)          # 【生产版】解密口令（只留在大脑上）
        changed = True
    if not conf.get('RDV_SEED'):
        conf['RDV_SEED'] = new_id(48)
        changed = True
    if changed:
        C.save(conf)
    init()
    set_meta('admin_token', conf['BRAIN_ADMIN_TOKEN'])

    if not C.SIGN_KEY.exists() and not secure.gen_signing_key():
        ui.err('生成签名密钥失败（需要 openssl）。')
        return 1
    C.PKG_DIR.mkdir(parents=True, exist_ok=True)

    ui.say(f'{ui.C_B}大脑已初始化{ui.C_0}（数据目录 {C.HOME}）')
    ui.say()
    ui.say('下面两样请记好：')
    ui.say(f'  注册口令   {ui.C_Y}{conf["ENROLL_SECRET"]}{ui.C_0}')
    ui.say('    → 部署子 agent 时用：ai-agent enroll 会提示你输入它（不写进脚本）')
    ui.say(f'  子 agent 公钥  {C.SIGN_PUB}')
    ui.say('    → 拷到每台子 agent（如 ~/.ai-agent/brain.pub），用于校验升级包签名')
    ui.say()
    if not conf['AI_API_KEY']:
        ui.warn(f'还没配置大脑自己用的模型 Key，请编辑：{C.CONF}')
        ui.dim('   AI_API_KEY=sk-xxxx')
    if not C.public_base(conf):
        ui.warn('还要设置大脑的对外地址（必须 https + 域名）：')
        ui.dim('   编辑 brain.conf：PUBLIC_URL=https://你的域名（如 https://brain.example.com）')
        ui.dim('   本机 CLI 与子 agent 都只认它，http:// 或 IP 一律拒绝。')
    ui.dim(f'提示词可放在 {C.PROMPTS_OVERRIDE}/ 自定义（不改程序）；默认用 '
           f'{C.builtin_prompts_dir()}/')
    ui.dim('会合（换服务器/域名也能被找回）：用 brain rendezvous 查看与切换')
    return 0


def cmd_serve(conf) -> int:
    if not conf['BRAIN_ADMIN_TOKEN']:
        ui.err('尚未初始化，请先执行：brain init')
        return 1
    init()
    set_meta('admin_token', conf['BRAIN_ADMIN_TOKEN'])
    if str(conf.get('BRAIN_BIND') or '') not in ('127.0.0.1', '::1'):
        ui.warn(f'注意：BRAIN_BIND={conf.get("BRAIN_BIND")} 会让大脑以**明文 HTTP** 对外暴露，不安全。')
        ui.dim('  建议改回 127.0.0.1，对外统一走 nginx + 域名 + HTTPS。')
    if not C.public_base(conf):
        ui.warn('还没配置 PUBLIC_URL（https://域名）—— 本机 CLI 与子 agent 都将无法使用。')
        ui.dim('  请在 brain.conf 里设置后重启。')
    from . import server
    return server.serve(conf)


# ==================== 状态 ====================
def cmd_status(conf) -> int:
    base = C.public_base(conf)
    if not base:
        ui.err('还没配置大脑对外地址，无法查询状态。')
        ui.dim('  请在 brain.conf 里设置：PUBLIC_URL=https://你的域名（必须 https + 域名）')
        return 1
    if not apicli.server_alive(conf):
        ui.warn(f'大脑服务不可达（{base}）。')
        ui.dim('  用 brain serve 启动；或检查域名解析 / nginx 反代 / 证书。')
        return 1
    ov, e = apicli.api(conf, 'GET', '/internal/overview')
    if e:
        ui.err('查询失败：', e)
        return 1
    ui.say(f'{ui.C_B}大脑 v{ov["version"]}{ui.C_0}  挡位 {C.mode(conf)}  '
           f'待批准 {ov["pending"]}  '
           f'任务(运行 {ov["tasks_running"]} / 排队 {ov["tasks_queued"]})')
    if not ov['agents']:
        ui.dim('（还没有子 agent 接入）')
        return 0
    ui.say(f'{"AGENT":<20}{"系统":<9}{"状态":<8}{"负载":<16}{"磁盘":<26}{"版本":<10}')
    for a in ov['agents']:
        oslabel = 'Windows' if (a.get('os') == 'win') else 'Linux'
        if a.get('blocked'):
            st, color = ('已自毁' if a.get('wipe_done') else '已拉黑'), ui.C_R
        else:
            st = '在线' if a['online'] else '离线'
            color = ui.C_G if a['online'] else ui.C_R
        load = str(a['load1'] or '-')[:14]
        disk = str(a['disk'] or '-')[:24]
        ui.say(f'{a["agent_id"]:<20}{oslabel:<9}{color}{st}{ui.C_0}      {load:<16}{disk:<26}'
               f'{a["version"] or ""}')
    return 0


# ==================== 待批准 / 批准 ====================
def cmd_pending(conf) -> int:
    r, e = apicli.api(conf, 'GET', '/internal/pending')
    if e:
        ui.err('查询失败：', e)
        return 1
    items = (r or {}).get('pending') or []
    if not items:
        ui.dim('（没有待批准的机器）')
        return 0
    for p in items:
        ui.say(f'{p["id"]}  {p["agent_id"]}  {p.get("host") or ""}')
    return 0


def cmd_decide(conf, enroll_id: str, allow: bool) -> int:
    r, e = apicli.api(conf, 'POST', '/internal/decide',
                      {'enroll_id': enroll_id, 'allow': allow})
    if e or (r or {}).get('error'):
        ui.err('操作失败：', e or (r or {}).get('error'))
        return 1
    ui.good(f'{enroll_id} → {(r or {}).get("status")}')
    return 0


# ==================== 发布升级包 ====================
def cmd_release(conf, args) -> int:
    """brain release <文件> --version 1.1.0 [--notes "说明"] [--os linux|win]"""
    if not args:
        ui.err('用法：brain release <文件> --version 1.1.0 [--notes "说明"] [--os linux|win]')
        return 1
    src = Path(args[0])
    ver = notes = ''
    osname = 'linux'
    for i, a in enumerate(args):
        if a == '--version' and i + 1 < len(args):
            ver = args[i + 1]
        elif a == '--notes' and i + 1 < len(args):
            notes = args[i + 1]
        elif a == '--os' and i + 1 < len(args):
            osname = args[i + 1].strip().lower()
    if osname not in ('linux', 'win'):
        ui.err('--os 只能是 linux 或 win')
        return 1
    if not src.exists():
        ui.err('文件不存在：', src)
        return 1
    # 护栏：别把「开发版」（明文）发出去 —— 那会让所有子 agent 从加密变明文。
    # 两个平台的明文开发版都含 SYS_TASK 的赋值（Linux `SYS_TASK='…'`、Windows `$SYS_TASK = @'…`）；
    # 加密生产版正文是 base64 密文（base64 不含下划线）且 loader 里没有这个标识 → 不会误伤。
    try:
        head = src.read_text(encoding='utf-8', errors='replace')[:200000]
    except OSError:
        head = ''
    if re.search(r'\$?SYS_TASK\s*=', head) and '--force' not in args:
        ui.err('这个文件看起来是【开发版（明文）】：直接发布会让全网子 agent 变成明文。')
        ui.dim('  先打包成生产版：Linux 用 bash tools/pack-agent.sh …；Windows 用 win/pack-agent.ps1 …')
        ui.dim('  确实要发明文，就在命令后面加 --force。')
        return 1
    if not re.match(r'^[\w.\-]{1,32}$', ver or ''):
        ui.err('必须用 --version 指定版本号（字母数字._-）')
        return 1
    init()
    if not C.SIGN_KEY.exists():
        ui.err('还没生成签名密钥，请先执行：brain init')
        return 1
    C.PKG_DIR.mkdir(parents=True, exist_ok=True)
    dst = C.PKG_DIR / f'ai-agent-{osname}-{ver}'
    try:
        shutil.copyfile(src, dst)
        digest = secure.sha256_file(dst)
        sig_b64 = secure.b64(secure.sign_file(dst))
    except (OSError, RuntimeError) as e:
        ui.err(f'✗ 发布失败：{type(e).__name__}: {e}')
        ui.dim('  常见原因：文件读不了/写不进去，或 openssl 不可用（签名需要它）。')
        return 1
    x('INSERT INTO releases(os,version,filename,sha256,sig,notes,created_at) VALUES(?,?,?,?,?,?,?)'
      ' ON CONFLICT(os,version) DO UPDATE SET filename=excluded.filename, sha256=excluded.sha256,'
      ' sig=excluded.sig, notes=excluded.notes, created_at=excluded.created_at',
      (osname, ver, dst.name, digest, sig_b64, notes, now()))
    audit('brain', 'release', '', f'{osname} {ver} {digest[:12]}')
    # 防呆：新发的包若与上一版**字节完全相同**，几乎一定是"忘了重新打包"（release 只是登记你给的文件，
    # 不会替你打包）。发出去后机器会反复"升级"、版本号却永远不动 —— 这个坑真踩过一次。
    prev = q('SELECT version, sha256 FROM releases WHERE os=? AND version<>?'
             ' ORDER BY created_at DESC LIMIT 1', (osname, ver), one=True)
    if prev and prev['sha256'] == digest:
        ui.warn(f'⚠ 注意：这个包与已发布的 {osname} {prev["version"]} **字节完全相同**（sha256 一样）。')
        ui.dim('   多半是忘了重新打包：先改源码里的 VERSION，再打包（Windows：win/pack-agent.ps1 -Online …），')
        ui.dim('   然后拿**新产物**来 release。否则机器下载到的正文里版本号不变，会一直"升不上去"。')
    ui.good(f'已发布子 agent 版本 {ver}（{osname}）')
    ui.say(f'  sha256 : {digest}')
    ui.say(f'  包路径 : {dst}')
    ui.dim('子 agent 最多 10 分钟内自动升级；也可在任意一台执行对应命令立刻升。')
    return 0


# ==================== 拉黑（不可恢复：先三层确认） ====================
def cmd_block(conf, args) -> int:
    """brain block <agent_id> [--reason "原因"] —— 拉黑并命令它自毁（须人工再三确认）"""
    if not args:
        ui.err('用法：brain block <agent_id> [--reason "原因"]')
        return 1
    aid = args[0]
    reason = ''
    for i, a in enumerate(args):
        if a == '--reason' and i + 1 < len(args):
            reason = args[i + 1]
    r, e = apicli.api(conf, 'GET', '/internal/agents')
    if e:
        ui.err('查询失败：', e)
        return 1
    hit = [a for a in (r or {}).get('agents') or [] if a['agent_id'] == aid]
    if not hit:
        ui.err(f'没有这台子 agent：{aid}')
        return 1
    a = hit[0]
    ui.say()
    ui.warn('⚠ 拉黑 = 不可恢复的两件事：')
    ui.say('   1) 立刻拒绝它以后的一切请求（心跳 / 领任务 / 升级 全断）')
    ui.say('   2) 命令它把**本机关于自己的一切全部删除**：')
    ui.say('      程序文件、配置、本机令牌、缓存、日志、开机自启 —— 一点不留')
    ui.say(f'   这台现在：{"在线" if a.get("online") else "离线"}，版本 {a.get("version") or "-"}')
    if a.get('blocked'):
        ui.dim('   （它之前已被拉黑过，这次会重新下发自毁指令）')
    ui.say()
    if not sys.stdin.isatty():
        ui.err('拉黑必须在终端里人工操作（不接受管道 / 脚本输入）。')
        return 1

    # 第 1 层
    if not ui.confirm(f'第 1 步：确定要拉黑 {aid} 吗？', force=True):
        ui.dim('已取消（什么都没做）。')
        return 0
    # 第 2 层：原样输入它的名字
    try:
        t = input(f'  第 2 步：原样输入它的名字以确认 —— {ui.C_Y}{aid}{ui.C_0}\n  > ').strip()
    except (EOFError, UnicodeDecodeError):
        ui.err('已取消（什么都没做）。')
        return 1
    if t != aid:
        ui.err('输入不一致，已取消（什么都没做）。')
        return 1
    # 第 3 层：一字不差的确认口令
    phrase = '我确认拉黑并让它自毁'
    try:
        t = input(f'  第 3 步：一字不差地输入 —— {ui.C_Y}{phrase}{ui.C_0}\n  > ').strip()
    except (EOFError, UnicodeDecodeError):
        ui.err('已取消（什么都没做）。')
        return 1
    if t != phrase:
        ui.err('口令不一致，已取消（什么都没做）。')
        return 1

    r2, e2 = apicli.api(conf, 'POST', '/internal/block', {'agent_id': aid, 'reason': reason})
    if e2 or (r2 or {}).get('error'):
        ui.err('拉黑失败：', e2 or (r2 or {}).get('error'))
        return 1
    ui.good(f'已拉黑 {aid}：以后它的请求一律拒绝。')
    if a.get('online'):
        ui.say('  自毁指令已就位：它下次来领任务时就会把自己清干净。')
    else:
        ui.warn('  它现在不在线：自毁指令要等它下次联网（领任务）才会执行。')
        ui.dim('  若它一直不上线，需要你手动去那台机器清理（停服务 + 删程序 + 删 ~/.ai-agent）。')
    return 0


# ==================== 解黑（给误拉黑留的出口） ====================
def cmd_unblock(conf, args) -> int:
    """brain unblock <agent_id> —— 解除拉黑（被拉黑后它无法再注册/连接）"""
    if not args:
        ui.err('用法：brain unblock <agent_id>')
        return 1
    aid = args[0]
    if not sys.stdin.isatty():
        ui.err('解黑请在终端里人工操作。')
        return 1
    if not ui.confirm(f'解除对 {aid} 的拉黑吗？（它仍需重新部署才能接回来）', force=True):
        ui.dim('已取消。')
        return 0
    r, e = apicli.api(conf, 'POST', '/internal/unblock', {'agent_id': aid})
    if e or (r or {}).get('error'):
        ui.err('解黑失败：', e or (r or {}).get('error'))
        return 1
    ui.good(f'已解除拉黑：{aid}（要接回来，请在那台机器上重新部署，见第 4 节）')
    return 0


# ==================== 生产版解密口令（查看 / 轮换） ====================
def _mask_key(s: str) -> str:
    if not s:
        return '（未设置）'
    return s[:6] + '…' + s[-4:] if len(s) > 12 else s


def cmd_packkey(conf, args) -> int:
    """brain pack-key [rotate|drop-old] —— 查看/轮换「生产版解密口令」(PACK_KEY)

    轮换要点：直接用一把新口令换掉旧的，会让"还没升级的子 agent"（老密文按旧口令加密）
    下次启动时解不开 —— 整片失联。所以这里走**双口令过渡**：旧口令暂留，打包/下发新版本
    后子 agent 逐台升级；等全部升完再 drop-old。打包脚本会"先按新口令、不匹配退旧口令"。
    """
    sub = (args[0] if args else '').strip()
    cur = conf.get('PACK_KEY') or ''
    old = conf.get('PACK_KEY_OLD') or ''

    if sub == 'rotate':
        if not cur:
            ui.err('还没有 PACK_KEY，请先 brain init')
            return 1
        if not sys.stdin.isatty():
            ui.err('轮换口令请在终端里人工操作。')
            return 1
        ui.warn('⚠ 轮换口令期间会有"新旧两把同时可用"的过渡期（这是为了不让老文件失联）。')
        if not ui.confirm('确定轮换生产版解密口令吗？', force=True):
            ui.dim('已取消（什么都没做）。')
            return 0
        C.set_key('PACK_KEY_OLD', cur)
        new = new_id(48)
        C.set_key('PACK_KEY', new)
        ui.good('已生成新的解密口令（旧的暂留作过渡）。')
        ui.say('接下来按顺序做：')
        ui.say('  1) 重新打包（会用新口令）：bash tools/pack-agent.sh <ai-agent> '
               '--online --brain https://你的大脑域名')
        ui.say('  2) 发布新版本：brain release <打好的包> --version <新版本>')
        ui.dim('  3) 等所有子 agent 都升级上来后，执行：brain pack-key drop-old')
        return 0

    if sub == 'drop-old':
        if not old:
            ui.dim('（当前没有过渡旧口令，无需清理）')
            return 0
        if not sys.stdin.isatty():
            ui.err('请在终端里人工操作。')
            return 1
        ui.warn('⚠ 废除旧口令后，"还没升级的子 agent"将无法启动（需要它先升级）。')
        if not ui.confirm('确定废除旧口令吗？', force=True):
            ui.dim('已取消。')
            return 0
        C.set_key('PACK_KEY_OLD', '')
        ui.good('已废除过渡旧口令（现在只认新口令）。')
        return 0

    ui.say(f'{ui.C_B}生产版解密口令（PACK_KEY）{ui.C_0}')
    ui.say(f'  当前口令   : {_mask_key(cur)}')
    ui.say(f'  过渡旧口令 : {_mask_key(old)}'
           + ('（轮换过渡期；等全部升级后 drop-old）' if old else ''))
    ui.dim('  brain pack-key rotate      轮换口令（新旧并行 → 重打包+发布 → 全部升级后 drop-old）')
    ui.dim('  brain pack-key drop-old    废除过渡旧口令（仅在全部子 agent 都升级之后）')
    return 0


# ==================== 通知（测试） ====================
def cmd_notify_test(conf) -> int:
    """brain test-mail —— 用当前配置发一封测试邮件，验证通知通道是否通"""
    from . import notify
    if not notify.enabled(conf):
        ui.err('还没配置通知。请在 brain.conf 里填这三项：')
        ui.say('   PUSH_APP_ID=...        （推送服务接入项目的 APPID）')
        ui.say('   PUSH_APP_SECRET=...    （推送服务的 APPSECRET）')
        ui.say('   PUSH_TO=you@example.com（收件人，多个用逗号分隔）')
        ui.dim('   （PUSH_BASE 默认 https://www.xiaoyingapi.com）')
        return 1
    ui.say(f'正在给 {conf["PUSH_TO"]} 发测试邮件…')
    ok, msg = notify.send(conf, '[ai-brain] 测试通知',
                          '这是一封测试邮件：收到它，说明大脑的通知通道（邮件报警）已经配好了。')
    if ok:
        ui.good('已发出：', msg)
        ui.dim('  没收到先看垃圾箱；再不行看 ~/.ai-brain/brain.log 里的 notify 记录')
        return 0
    ui.err('发送失败：', msg)
    ui.dim('  检查 app_id / app_secret 是否正确；以及大脑那台能不能访问 PUSH_BASE（要能出网）')
    return 1


# ==================== 停止 ====================
def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, ValueError):
        return False
    except PermissionError:
        return True


def _stop_pid(pid: int) -> str:
    """停掉一个 pid：先 SIGTERM，5 秒不退再 SIGKILL。

    返回 'term'（正常停掉）/ 'kill'（强制停掉）/ 'fail'（没停掉）。
    """
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        return 'term' if not _alive(pid) else 'fail'
    for _ in range(50):                              # 最多等 5 秒
        if not _alive(pid):
            return 'term'
        time.sleep(0.1)
    try:
        os.kill(pid, signal.SIGKILL)                 # 还不退就强杀，否则会一直占着端口
    except OSError:
        return 'term' if not _alive(pid) else 'fail'
    for _ in range(20):                              # 最多再等 2 秒
        if not _alive(pid):
            return 'kill'
        time.sleep(0.1)
    return 'fail'


def _pids_on_port(port: int) -> list:
    """找出正在监听 TCP 端口 port 的进程 pid（纯读 /proc，不依赖 ss/lsof）。"""
    inodes = set()
    for path in ('/proc/net/tcp', '/proc/net/tcp6'):
        try:
            rows = Path(path).read_text().splitlines()[1:]
        except OSError:
            continue
        for row in rows:
            f = row.split()
            if len(f) < 10 or f[3] != '0A':          # 0A = LISTEN
                continue
            try:
                if int(f[1].rsplit(':', 1)[1], 16) == port:
                    inodes.add(f[9])                 # 第 10 列是 socket inode
            except (ValueError, IndexError):
                continue
    if not inodes:
        return []
    links = {f'socket:[{i}]' for i in inodes}
    pids = []
    try:
        procs = list(Path('/proc').iterdir())
    except OSError:
        return []
    for pdir in procs:
        if not pdir.name.isdigit():
            continue
        try:
            for fd in (pdir / 'fd').iterdir():
                try:
                    if os.readlink(fd) in links:
                        pids.append(int(pdir.name))
                        break
                except OSError:
                    continue
        except OSError:
            continue
    return pids


def _is_brain_serve(pid: int) -> bool:
    """判断这个 pid 是不是 `... brain serve`，避免误杀机器上别的服务。"""
    try:
        raw = Path(f'/proc/{pid}/cmdline').read_bytes()
    except OSError:
        return False
    parts = [p for p in raw.decode('utf-8', 'replace').split('\0') if p]
    return 'serve' in parts and any(p.endswith('brain') for p in parts)


def cmd_stop(conf) -> int:
    """停止大脑服务。

    除了按 brain.pid 停，还会检查配置端口是否仍被**别的** `brain serve` 占用并一并
    终止——避免"旧进程占着端口，导致下次启动没生效"。
    """
    try:
        port = int(conf['BRAIN_PORT'])
    except (KeyError, ValueError):
        port = 0

    killed, pid = 0, None

    # 1) 按 brain.pid 精确停
    if C.PID_FILE.exists():
        try:
            pid = int(C.PID_FILE.read_text().strip())
        except (ValueError, OSError):
            pid = None
    if pid and _alive(pid):
        r = _stop_pid(pid)
        if r == 'fail':
            ui.warn(f'pid {pid} 停不掉（可能卡在长连接），请强制：kill -9 {pid}')
        else:
            ui.good(f'已停止（pid {pid}{"，强制" if r == "kill" else ""}）')
            killed += 1
    elif pid:
        ui.dim(f'pid 文件里的进程 {pid} 已不在运行。')
    try:
        C.PID_FILE.unlink()
    except OSError:
        pass

    # 2) 兜底：配置端口是否还被旧的 brain serve 占着
    if port:
        for sp in _pids_on_port(port):
            if sp == pid:
                continue
            if not _is_brain_serve(sp):
                ui.warn(f'端口 {port} 被非 brain 进程占用（pid {sp}），未动它。')
                continue
            r = _stop_pid(sp)
            if r == 'fail':
                ui.warn(f'端口 {port} 被 pid {sp} 占用且停不掉，请强制：kill -9 {sp}')
            else:
                ui.good(f'端口 {port} 被旧进程占用，已一并停止'
                        f'（pid {sp}{"，强制" if r == "kill" else ""}）')
                killed += 1

    if not killed and not pid:
        ui.warn(f'没找到在跑的大脑服务（pid 文件：{C.PID_FILE}）。')
        ui.warn("可手动：ps -eo pid,args | grep 'brain serve'")
        return 1
    return 0


# ==================== 会合（换服务器/域名也能被找回） ====================
def cmd_rendezvous(conf, args) -> int:
    seed = conf.get('RDV_SEED') or ''
    pat = conf.get('RDV_PATTERN') or rendezvous.DEFAULT_PATTERN
    try:
        idx = int(str(conf.get('RDV_INDEX') or '1'))
    except ValueError:
        idx = 1
    sub = (args[0] if args else '').strip()

    if sub == 'rotate':
        conf['RDV_SEED'] = new_id(48)
        C.set_key('RDV_SEED', conf['RDV_SEED'])
        ui.good('已轮换会合主密钥（RDV_SEED）。')
        ui.dim('  子 agent 下次注册/心跳会自动收到新种子并更新；旧种子算出的域名作废。')
        return 0

    if sub in ('next', 'set') and not seed:
        ui.err('还没初始化会合密钥（RDV_SEED 为空），先执行：brain init')
        return 1

    if sub == 'set':
        if len(args) < 2 or not str(args[1]).isdigit():
            ui.err('用法：brain rendezvous set <期号，如 2>')
            return 1
        conf['RDV_INDEX'] = str(args[1])
        C.set_key('RDV_INDEX', conf['RDV_INDEX'])
        ui.good(f'当前期号已设为 {args[1]}。')
        ui.say(f'  本期域名：{rendezvous.derive(seed, pat, int(args[1]))}')
        return 0

    if sub == 'next':
        n = idx + 1
        d = rendezvous.derive(seed, pat, n)
        ui.say(f'下一期（第 {n} 期）域名：{ui.C_B}{d}{ui.C_0}')
        ui.dim(f'  → 去注册它、DNS 指到本机、配好证书，然后执行：brain rendezvous set {n}')
        if '--check' in args:
            reg, why = rendezvous.looks_registered(d)
            state = {True: '已被注册', False: '还没人注册（可以买）', None: '查询失败（未知）'}[reg]
            ui.say(f'  注册状态：{state}（依据 {why}）')
        return 0

    W = 22
    cur = rendezvous.derive(seed, pat, idx) if seed else '（先 brain init）'
    bid = rendezvous.brain_id(seed) if seed else '—'
    ui.say(f'{ui.C_B}会合（rendezvous）{ui.C_0}')
    ui.say(f'{ui.pad("主密钥 RDV_SEED", W)}: {"已设置" if seed else "未设置（先 brain init）"}')
    ui.say(f'{ui.pad("域名模板", W)}: {pat}')
    ui.say(f'{ui.pad("当前期号", W)}: {idx}')
    ui.say(f'{ui.pad("当前后台域名", W)}: {cur}')
    ui.say(f'{ui.pad("brain_id", W)}: {bid}')
    ui.dim('  brain rendezvous next [--check]   看下一期域名（换后台时用；--check 顺带查能不能注册）')
    ui.dim('  brain rendezvous set <期号>       把当前期号设成你实际部署的那一期')
    ui.dim('  brain rendezvous rotate           轮换主密钥（子 agent 会自动更新）')
    return 0


# ==================== 公钥 ====================
def cmd_pubkey(conf) -> int:
    txt = secure.pubkey_text()
    if not txt:
        ui.err('还没生成签名密钥，请先执行：brain init')
        return 1
    ui.say(txt)
    return 0


# ==================== 文件文档控制台 ====================
ROOT_TITLE = {
    'program': '程序目录（部署时上传的）',
    'brain_home': '大脑数据目录',
    'agent_home': '子 agent 数据目录',
}


def cmd_files(conf) -> int:
    """把每个文件"是什么、何时生成、能不能删、怎么看"全部列出来（不调模型，秒出）。"""
    r = registry.roots()
    ui.say(f'{ui.C_B}ai-brain 文件总览{ui.C_0}')
    ui.say(f'  程序目录     : {r["program"]}')
    ui.say(f'  大脑数据目录 : {r["brain_home"]}')
    ah = r['agent_home']
    ui.say(f'  子agent数据  : {ah}' + ('' if ah.exists() else f'  {ui.C_DIM}（本机未安装子 agent）{ui.C_0}'))
    ui.say()

    cur_root, idx, n_exist = None, 0, 0
    for e in registry.gather(conf):
        if e['root'] != cur_root:
            cur_root = e['root']
            ui.say(f'{ui.C_B}── {ROOT_TITLE.get(cur_root, cur_root)}：{e["base"]} ──{ui.C_0}')
        idx += 1
        mark = f'{ui.C_G}✔{ui.C_0}' if e['exists'] else f'{ui.C_DIM}–{ui.C_0}'
        n_exist += 1 if e['exists'] else 0
        extra = '  '.join(x for x in (e['size'] or e['count'], e['mtime']) if x)
        ui.say(f'{mark} {idx:>2}. {ui.C_B}{e["path"]}{ui.C_0}  [{e["kind"]}]'
               + (f'  {ui.C_DIM}{extra}{ui.C_0}' if extra else ''))
        ui.dim(f'      位置    : {e["full"]}')
        ui.say(f'      何时产生: {e["when"]}')
        ui.say(f'      干什么用: {e["what"]}')
        ui.say(f'      能不能删: {e["dele"]}')
        ui.dim(f'      怎么看  : {e["peek"]}')
        if e['secret']:
            ui.warn('      ⚠ 内含敏感信息：别外传，也别贴到聊天记录里')
        ui.say()

    ui.say(f'{ui.C_DIM}（共 {idx} 项，其中 {n_exist} 项已存在；'
           f'带 ✔ 的是现在真实存在的）{ui.C_0}')
    ui.say(f'{ui.C_DIM}想看配置里"设了什么"（密钥打码）：brain status；'
           f'文件统计：{registry.db_summary()}{ui.C_0}')
    ui.dim('想让 AI 用大白话再讲一遍、或回答"删了会怎样"：brain explain "问题"')
    return 0


# ==================== 版本 ====================
def shipped_agent_version(osname='linux') -> str:
    """程序目录里子 agent 自带版本号：Linux 读 ai-agent（VERSION='x'），
    Windows 读 win/ai-agent.ps1（$VERSION = 'x'）。"""
    if osname == 'win':
        f = C.script_dir() / 'win' / 'ai-agent.ps1'
        pat = r"\$VERSION\s*=\s*'([^']+)'"
    else:
        f = C.script_dir() / 'ai-agent'
        pat = r"^VERSION='([^']+)'"
    try:
        m = re.search(pat, f.read_text(encoding='utf-8', errors='replace'), re.M)
        return m.group(1) if m else '未知'
    except OSError:
        return '未知'


def latest_release(osname='linux'):
    """某个系统上已发布的最新子 agent 版本（没发布过就返回 None）。"""
    if not C.DBPATH.exists():
        return None
    try:
        return q('SELECT version, notes, created_at FROM releases WHERE os=? '
                 'ORDER BY created_at DESC LIMIT 1', (osname,), one=True)
    except Exception:                                # noqa: BLE001
        return None


def _rel_txt(rel) -> str:
    if not rel:
        return '（还没发布过）'
    t = time.strftime('%Y-%m-%d %H:%M', time.localtime(rel['created_at'] or 0))
    note = f'：{rel["notes"]}' if rel['notes'] else ''
    return f'{rel["version"]}（{t} 发布{note}）'


def _agent_rows():
    if not C.DBPATH.exists():
        return []
    try:
        return q('SELECT agent_id, version, os, last_seen FROM agents ORDER BY agent_id')
    except Exception:                                # noqa: BLE001
        return []


def cmd_version(conf) -> int:
    """看版本：大脑自己 / 自带子 agent（Linux/Win）/ 各系统已发布最新版 / 每台实际版本。"""
    W = 24
    ui.say(f'{ui.C_B}{ui.pad("大脑当前版本", W)}{ui.C_0}: {VERSION}')
    ui.say(f'{ui.pad("程序自带的 ai-agent", W)}: '
           f'Linux {shipped_agent_version("linux")} ｜ Windows {shipped_agent_version("win")}')
    rel_l = latest_release('linux')
    rel_w = latest_release('win')
    ui.say(f'{ui.C_B}{ui.pad("已发布的最新版", W)}{ui.C_0}:')
    ui.say(f'    Linux   : {_rel_txt(rel_l)}')
    ui.say(f'    Windows : {_rel_txt(rel_w)}')

    rows = _agent_rows()
    ui.say()
    if not rows:
        ui.dim(f'{ui.pad("各服务器", W)}: （还没有子 agent 接入）')
        return 0
    latest = {'linux': (rel_l or {}).get('version'), 'win': (rel_w or {}).get('version')}
    ui.say(f'{"服务器":<22}{"系统":<9}{"它上报的版本":<15}{"最后心跳":<12}状态')
    for r in rows:
        osname = (r.get('os') or 'linux')
        oslabel = 'Windows' if osname == 'win' else 'Linux'
        v = r['version'] or '未上报'
        want = latest.get(osname)
        if not want:
            st = '（该系统的版本还没发布过）'
        elif v == want:
            st = f'{ui.C_G}已是最新{ui.C_0}'
        else:
            st = f'{ui.C_Y}与最新发布不一致{ui.C_0}'
        ago = f'{int(now() - r["last_seen"])}s 前' if r['last_seen'] else '从未'
        ui.say(f'{r["agent_id"]:<22}{oslabel:<9}{v:<15}{ago:<12}{st}')
    ui.dim('（“不一致”＝它与该系统最新发布版不同：Linux 那台执行 ai-agent update；'
           'Windows 那台执行 ai-agent.ps1 update）')
    return 0


# ==================== 上传的文件（查看 / 下载 / 清理） ====================
def _hsize(n) -> str:
    """人类可读的大小：1234 → 1.2KB。"""
    n = float(n or 0)
    for u in ('B', 'KB', 'MB', 'GB'):
        if n < 1024 or u == 'GB':
            return f'{int(n)}{u}' if u == 'B' else f'{n:.1f}{u}'
        n /= 1024.0
    return f'{int(n)}B'


def _rm_uploads(rows):
    for r in rows:
        try:
            Path(r['path']).unlink()
        except OSError:
            pass
        x('DELETE FROM uploads WHERE id=?', (r['id'],))
        audit('brain', 'upload-rm', r['agent_id'], f'{r["name"]} ({r["id"][:8]})', r['task_id'] or '')


def cmd_uploads(conf, args) -> int:
    """brain uploads [--rm <id>] [--clean] —— 看子 agent 传上来的文件（在线链接 / 清理）。"""
    init()
    if '--clean' in args:
        rows = q('SELECT * FROM uploads')
        if not rows:
            ui.dim('（没有上传的文件）')
            return 0
        if not ui.confirm(f'确定删掉全部 {len(rows)} 个上传文件吗？（连磁盘文件一起删，不可恢复）', force=True):
            ui.dim('已取消。')
            return 0
        _rm_uploads(rows)
        ui.good(f'已删除 {len(rows)} 个上传文件。')
        return 0
    if '--rm' in args:
        i = args.index('--rm')
        fid = args[i + 1] if i + 1 < len(args) else ''
        row = q('SELECT * FROM uploads WHERE id=?', (fid,), one=True)
        if not row:
            ui.err(f'没有这个文件：{fid}（用 brain uploads 看 ID）')
            return 1
        _rm_uploads([row])
        ui.good(f'已删除：{row["name"]}（{row["id"][:8]}）')
        return 0

    rows = q('SELECT * FROM uploads ORDER BY created_at DESC LIMIT 500')
    if not rows:
        ui.dim('（还没有子 agent 上传过文件）')
        ui.dim('  子 agent 里执行：ai-agent upload <文件>（Windows：ai-agent.ps1 upload <文件>）')
        return 0
    base = C.public_base(conf)
    ui.say(f'{ui.C_B}{ui.pad("上传的文件", 24)}{ui.C_0}: 共 {len(rows)} 个（链接可在浏览器直接打开）')
    ui.say(f'{"ID":<10}{"来自":<20}{"文件名":<26}{"大小":>9}  {"时间":<12}链接')
    for r in rows:
        link = f'{base}/f/{r["id"]}' if base else '（未配 PUBLIC_URL；先用 brain get 取回）'
        ui.say(f'{r["id"][:8]:<10}{str(r["agent_id"])[:19]:<20}'
               f'{str(r["name"] or "")[:25]:<26}{_hsize(r["size"]):>9}  '
               f'{time.strftime("%m-%d %H:%M", time.localtime(r["created_at"] or 0)):<12}{link}')
    ui.dim('取回本机：brain get <ID>    删一个：brain uploads --rm <ID>    全清：brain uploads --clean')
    return 0


def cmd_get(conf, args) -> int:
    """brain get <id> [-o 输出文件] —— 把一个上传的文件取到本机（默认存当前目录）。"""
    init()
    if not args:
        ui.err('用法：brain get <id> [-o 输出文件]')
        return 1
    key = args[0]
    out = ''
    if '-o' in args:
        i = args.index('-o')
        out = args[i + 1] if i + 1 < len(args) else ''
    row = q('SELECT * FROM uploads WHERE id=?', (key,), one=True)
    if not row:                                  # 允许只写 ID 的前几位
        row = q('SELECT * FROM uploads WHERE id LIKE ? ORDER BY created_at DESC LIMIT 1',
                (key + '%',), one=True)
    if not row:
        ui.err(f'没有这个文件：{key}（用 brain uploads 看 ID）')
        return 1
    src = Path(row['path'])
    if not src.is_file():
        ui.err('磁盘上找不到这个文件（可能已被清理）。')
        return 1
    dst = Path(out) if out else (Path.cwd() / row['name'])
    if dst.is_dir():
        dst = dst / row['name']
    try:
        shutil.copyfile(src, dst)
    except OSError as e:
        ui.err(f'保存失败：{e}')
        return 1
    ui.good(f'已保存：{dst}（{_hsize(row["size"])}）')
    return 0
