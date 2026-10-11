# -*- coding: utf-8 -*-
"""管理类子命令：init / serve / status / pending / approve / deny / release / stop / pubkey。

这些命令要么直接读写本机数据（init/release），要么通过 api 调本机服务。
"""
from __future__ import annotations

import os
import re
import shutil
import signal
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
    ui.say(f'{"AGENT":<20}{"状态":<8}{"负载":<18}{"磁盘":<32}{"版本":<10}')
    for a in ov['agents']:
        st = '在线' if a['online'] else '离线'
        color = ui.C_G if a['online'] else ui.C_R
        load = str(a['load1'] or '-')[:16]
        disk = str(a['disk'] or '-')[:30]
        ui.say(f'{a["agent_id"]:<20}{color}{st}{ui.C_0}      {load:<18}{disk:<32}'
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
    """brain release <文件> --version 1.1.0 [--notes "说明"]"""
    if not args:
        ui.err('用法：brain release <文件> --version 1.1.0 [--notes "说明"]')
        return 1
    src = Path(args[0])
    ver = notes = ''
    for i, a in enumerate(args):
        if a == '--version' and i + 1 < len(args):
            ver = args[i + 1]
        elif a == '--notes' and i + 1 < len(args):
            notes = args[i + 1]
    if not src.exists():
        ui.err('文件不存在：', src)
        return 1
    if not re.match(r'^[\w.\-]{1,32}$', ver or ''):
        ui.err('必须用 --version 指定版本号（字母数字._-）')
        return 1
    init()
    if not C.SIGN_KEY.exists():
        ui.err('还没生成签名密钥，请先执行：brain init')
        return 1
    C.PKG_DIR.mkdir(parents=True, exist_ok=True)
    dst = C.PKG_DIR / f'ai-agent-{ver}'
    try:
        shutil.copyfile(src, dst)
        digest = secure.sha256_file(dst)
        sig_b64 = secure.b64(secure.sign_file(dst))
    except (OSError, RuntimeError) as e:
        ui.err(f'✗ 发布失败：{type(e).__name__}: {e}')
        ui.dim('  常见原因：文件读不了/写不进去，或 openssl 不可用（签名需要它）。')
        return 1
    x('INSERT INTO releases(version,filename,sha256,sig,notes,created_at) VALUES(?,?,?,?,?,?)'
      ' ON CONFLICT(version) DO UPDATE SET filename=excluded.filename, sha256=excluded.sha256,'
      ' sig=excluded.sig, notes=excluded.notes, created_at=excluded.created_at',
      (ver, dst.name, digest, sig_b64, notes, now()))
    audit('brain', 'release', '', f'{ver} {digest[:12]}')
    ui.good(f'已发布子 agent 版本 {ver}')
    ui.say(f'  sha256 : {digest}')
    ui.say(f'  包路径 : {dst}')
    ui.dim('子 agent 最多 10 分钟内自动升级；也可在任意一台执行 ai-agent update 立刻升。')
    return 0


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
def shipped_agent_version() -> str:
    """程序目录里 ai-agent 脚本自带的版本号（读它文件里的 VERSION='x.y.z'）。"""
    f = C.script_dir() / 'ai-agent'
    try:
        m = re.search(r"^VERSION='([^']+)'",
                      f.read_text(encoding='utf-8', errors='replace'), re.M)
        return m.group(1) if m else '未知'
    except OSError:
        return '未知'


def latest_release():
    """大脑上已发布的最新子 agent 版本（没发布过就返回 None）。"""
    if not C.DBPATH.exists():
        return None
    try:
        return q('SELECT version, notes, created_at FROM releases '
                 'ORDER BY created_at DESC LIMIT 1', one=True)
    except Exception:                                # noqa: BLE001
        return None


def _agent_rows():
    if not C.DBPATH.exists():
        return []
    try:
        return q('SELECT agent_id, version, last_seen FROM agents ORDER BY agent_id')
    except Exception:                                # noqa: BLE001
        return []


def cmd_version(conf) -> int:
    """看版本：大脑自己 / 程序自带的子 agent / 大脑上发布的最新版 / 每台服务器的实际版本。"""
    W = 24
    ui.say(f'{ui.C_B}{ui.pad("大脑当前版本", W)}{ui.C_0}: {VERSION}')
    ui.say(f'{ui.pad("程序里自带的 ai-agent", W)}: {shipped_agent_version()}'
           f'{ui.C_DIM}（程序目录里那个 ai-agent 文件自带的版本）{ui.C_0}')
    rel = latest_release()
    if rel:
        t = time.strftime('%Y-%m-%d %H:%M', time.localtime(rel['created_at'] or 0))
        note = f'：{rel["notes"]}' if rel['notes'] else ''
        ui.say(f'{ui.C_B}{ui.pad("大脑上已发布的最新版", W)}{ui.C_0}: {rel["version"]}'
               f'{ui.C_DIM}（{t} 发布{note}）{ui.C_0}')
    else:
        ui.warn(f'{ui.pad("大脑上已发布的最新版", W)}: （还没发布过）')
        ui.dim('  发布方法：brain release <ai-agent文件> --version 1.1.3 --notes "说明"')

    rows = _agent_rows()
    ui.say()
    if not rows:
        ui.dim(f'{ui.pad("各服务器", W)}: （还没有子 agent 接入）')
        return 0
    latest = rel['version'] if rel else None
    ui.say(f'{"服务器":<18}{"它上报的版本":<18}{"最后心跳":<14}状态')
    for r in rows:
        v = r['version'] or '未上报'
        if not latest:
            st = '（还没发布过版本）'
        elif v == latest:
            st = f'{ui.C_G}已是最新{ui.C_0}'
        else:
            st = f'{ui.C_Y}与最新发布不一致{ui.C_0}'
        ago = f'{int(now() - r["last_seen"])}s 前' if r['last_seen'] else '从未'
        ui.say(f'{r["agent_id"]:<18}{v:<18}{ago:<14}{st}')
    if latest:
        ui.dim(f'（“不一致”＝它与大脑上最新发布版 {latest} 不同；在那一台执行 ai-agent update 即可升级）')
    return 0
