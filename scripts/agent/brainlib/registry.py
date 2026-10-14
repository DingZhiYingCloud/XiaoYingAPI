# -*- coding: utf-8 -*-
"""文件说明书：这套程序在你机器上生成的**每一个文件**，都在这里登记。

三处共用同一份数据（改一处就够，不会文档和代码对不上）：
  1) `brain files`   —— 本地打印成控制台文档（不调模型，秒出）
  2) `brain explain` —— 把这份说明 + 现场事实喂给模型，让它用大白话解读
  3) README 的"文件总览"表格

每条登记的信息：
    root    相对哪个目录（program=程序目录 / brain_home=大脑数据 / agent_home=子agent数据）
    path    文件名（目录以 / 结尾）
    kind    分类：程序 / 配置 / 数据 / 密钥 / 日志 / 运行态 / 备份
    when    什么时候会产生
    what    干什么用的（详细）
    dele    能不能删、删了会怎样
    peek    怎么看它
    secret  内含敏感值（展示时要打码）
"""
from __future__ import annotations

import os
import time
from pathlib import Path

from . import conf as C

SECRET_KEYS = ('AI_API_KEY', 'ENROLL_SECRET', 'BRAIN_ADMIN_TOKEN', 'AGENT_TOKEN')


def agent_home() -> Path:
    return Path(os.environ.get('AI_AGENT_HOME') or (Path.home() / '.ai-agent'))


def roots() -> dict:
    return {'program': C.script_dir(), 'brain_home': C.HOME, 'agent_home': agent_home()}


# ==================== 登记表 ====================
ENTRIES = [
    # ---------------- 程序目录（部署时上传的） ----------------
    dict(root='program', path='brain', kind='程序', secret=False,
         when='部署时上传；升级时整目录覆盖',
         what='大脑的入口脚本。你敲的 brain init / serve / status / files 都由它解析，'
              '再分发到 brainlib/ 里的各个模块去干活。',
         dele='删了就用不了；重新上传即可，数据不会丢。',
         peek='python3 brain -h'),
    dict(root='program', path='brainlib/', kind='程序', secret=False,
         when='部署时上传；升级时整目录覆盖',
         what='大脑的全部实现，按职责拆成十几个小模块：conf 配置、store 数据库、secure 签名、'
              'llm 调模型、render 流式渲染、prompts 提示词、server 接口、admin 管理命令、chat 对话。',
         dele='删了大脑起不来（brain 会找不到模块）。重新上传即可。',
         peek='ls brainlib/'),
    dict(root='program', path='prompts/', kind='程序', secret=False,
         when='部署时上传（随程序发布）',
         what='大脑的提示词与技能：system.md 是行为准则、actions.md 是可用动作清单、'
              'skills/ 放你自己的背景知识。改这里就能调整它的行为，不用碰代码。',
         dele='删了没法对话（会报"找不到提示词文件"）；但服务端仍能跑，子 agent 不受影响。',
         peek='cat prompts/system.md'),
    dict(root='program', path='brainlib/__pycache__/', kind='运行态', secret=False,
         when='第一次用 python3 跑 brain 时由 Python 自动生成',
         what='Python 的字节码缓存，用来让下次启动快一点。',
         dele='可以删，删了下次运行会自动重建。',
         peek='ls brainlib/__pycache__/'),
    dict(root='program', path='ai-agent', kind='程序', secret=False,
         when='部署子 agent 时上传到**每一台**被管的服务器',
         what='子 agent 脚本。它上线后主动连大脑、领任务、在本机用大模型做完、回报结论，'
              '还会自己检查并升级自己。',
         dele='子 agent 那台会掉线；重新上传 + 不用重新注册（令牌在 ~/.ai-agent/agent.conf 里）。',
         peek='./ai-agent --version'),

    # ---------------- 大脑数据目录 ~/.ai-brain ----------------
    dict(root='brain_home', path='brain.conf', kind='配置', secret=True,
         when='brain init 生成；之后你输 /auto 切挡位、或手动编辑时更新',
         what='大脑的全部配置：监听地址/端口、模型和 Key、挡位 MODE、步数上限、'
              '注册口令 ENROLL_SECRET、管理令牌 BRAIN_ADMIN_TOKEN、流式开关等。权限 600。',
         dele='**不要删**。删了等于恢复出厂：要重新 brain init，注册口令和管理令牌都会变，'
              '所有子 agent 都得重新注册。',
         peek='python3 brain files（会显示已配置项）／ cat ~/.ai-brain/brain.conf'),
    dict(root='brain_home', path='brain.db', kind='数据', secret=False,
         when='brain init 建表；之后每次注册/心跳/下发/执行/升级都会写入',
         what='大脑的**主数据库**（SQLite）。共 8 张表：agents（已接入的服务器）、'
              'enrollments（注册申请）、tasks（下发过的任务与结果）、releases（发布过的升级包）、'
              'uploads（子 agent 传上来的文件）、'
              'audit（审计流水：谁在何时对谁做了什么）、nonces（防重放的随机数）、meta（管理令牌等）。',
         dele='**不要删**。删了所有服务器要从头注册、任务与审计记录全没。',
         peek='python3 brain status（概况）／ sqlite3 ~/.ai-brain/brain.db ".tables"'),
    dict(root='brain_home', path='brain.db-wal', kind='数据', secret=False,
         when='数据库开着时自动出现（SQLite 的 WAL 模式）',
         what='数据库的"预写日志"：新数据先写这里、再合并进 brain.db。断电也不容易坏。',
         dele='**别单独删**（会丢最近的写入）。要清理请先停服务，再连同 brain.db 一起处理。',
         peek='ls -l ~/.ai-brain/brain.db*'),
    dict(root='brain_home', path='brain.db-shm', kind='运行态', secret=False,
         when='数据库开着时自动出现',
         what='WAL 模式用的共享内存索引文件，纯运行态产物。',
         dele='停服务后可以删；下次启动会自动重建。',
         peek='ls -l ~/.ai-brain/brain.db*'),
    dict(root='brain_home', path='brain.log', kind='日志', secret=False,
         when='服务启动、以及运行中遇到错误/异常时追加',
         what='大脑的运行日志：服务启停、接口处理异常、未预期错误（含堆栈）。'
              '排查问题第一时间看它。',
         dele='可以删（会重新生成），但排查问题前建议留着。',
         peek='tail -50 ~/.ai-brain/brain.log'),
    dict(root='brain_home', path='brain.pid', kind='运行态', secret=False,
         when='brain serve 启动时写入；服务正常退出时自动删除',
         what='服务进程号。brain stop 靠它精确定位并停止**这一个**服务，'
              '不会误杀你机器上别的大脑实例。',
         dele='可以删（服务下次启动会重建），但删了 brain stop 就找不到进程了。',
         peek='cat ~/.ai-brain/brain.pid；ps -p $(cat ~/.ai-brain/brain.pid)'),
    dict(root='brain_home', path='serve.out', kind='日志', secret=False,
         when='用 nohup ... >~/.ai-brain/serve.out 启动时产生；'
              'brain 自动后台拉起服务时也会写这里',
         what='服务的"前台输出"存档：启动横幅、绑定端口失败等启动期信息。'
              '服务起不来时先看它。',
         dele='可以删（下次启动重新写）。',
         peek='cat ~/.ai-brain/serve.out'),
    dict(root='brain_home', path='signing.key', kind='密钥', secret=True,
         when='brain init 生成（openssl genrsa 2048），权限 600',
         what='大脑的**RSA 私钥**，用来给子 agent 的升级包签名。'
              '它是"发布权"的根：拿到它的人可以伪造升级包。',
         dele='**千万别删也千万别外传**。删了要重新 brain init 并重发公钥给所有子 agent，'
              '否则升级会一直报"签名校验失败"。',
         peek='ls -l ~/.ai-brain/signing.key（内容是私钥，别打印出来）'),
    dict(root='brain_home', path='signing.pub', kind='密钥', secret=False,
         when='brain init 生成（由私钥导出）',
         what='对应的**RSA 公钥**，要拷到每台子 agent（如 ~/.ai-agent/brain.pub）。'
              '子 agent 用它验证升级包确实出自你的大脑。',
         dele='可以删（重新导出即可：brain pubkey），但子 agent 那边就没有了，升级会被拒。',
         peek='python3 brain pubkey'),
    dict(root='brain_home', path='releases/', kind='数据', secret=False,
         when='brain init 建目录；每次 brain release 发布新版本时写入一个包',
         what='已签名的**子 agent 升级包**（形如 ai-agent-1.1.1），以及数据库里对应的 '
              '记录（版本号/sha256/签名/说明）。子 agent 来取的就是这里的文件。',
         dele='可以删旧版本包（只影响"回滚到那个版本"）；删最新的会让子 agent 取不到更新。',
         peek='ls -l ~/.ai-brain/releases/'),
    dict(root='brain_home', path='uploads/', kind='数据', secret=False,
         when='子 agent 第一次用 ai-agent upload 传文件时自动创建',
         what='子 agent 传上来的**文件**（截图 / 日志 / 报告…），按 `<agent_id>/<时间>-<随机码>-<文件名>` 存放。'
              '在线查看/下载的链接是 `<PUBLIC_URL>/f/<id>`，对应记录在数据库 uploads 表里。',
         dele='可以删（用 brain uploads --rm <id> / --clean 删更干净，会连库记录一起清）。',
         peek='python3 brain uploads（列表，带在线链接）／ python3 brain get <id>（取回本机）'),
    dict(root='brain_home', path='prompts/', kind='配置', secret=False,
         when='**你自己建**（可选）。程序不会自动创建',
         what='你的自定义提示词：放同名文件（system.md / actions.md / skills/*.md）'
              '就会**覆盖程序自带的那一份**，而且升级程序不会冲掉它。',
         dele='可以删（删了就退回用程序自带的提示词）。',
         peek='ls -R ~/.ai-brain/prompts/'),

    # ---------------- 子 agent 数据目录 ~/.ai-agent ----------------
    dict(root='agent_home', path='agent.conf', kind='配置', secret=True,
         when='部署时手写基本项；ai-agent enroll 成功后会写入本机专属令牌',
         what='子 agent 的配置：大脑地址 BRAIN_URL（可多个候选）、本机 agent_id、'
              '**本机专属令牌 AGENT_TOKEN**、以及这台机器自己调大模型用的 Key。权限 600。',
         dele='**不要删**。删了要重新 enroll（还得去大脑侧批准），'
              '或者从大脑的 brain.db 里恢复对应记录。',
         peek='ai-agent status（脱敏显示）／ cat ~/.ai-agent/agent.conf'),
    dict(root='agent_home', path='brain.pub', kind='密钥', secret=False,
         when='部署子 agent 时从大脑拷过来',
         what='大脑公钥的副本，用于校验下载到的升级包（sha256 + RSA 签名）。',
         dele='可以删，但删了升级会**跳过签名校验**（不安全）；建议保留。',
         peek='cat ~/.ai-agent/brain.pub'),
    dict(root='agent_home', path='brain_cache', kind='运行态', secret=False,
         when='子 agent 第一次成功连上大脑时写入，之后自动更新',
         what='上次连通的**大脑地址**。子 agent 找大脑的顺序是：'
              '配置里的 → 这个缓存 → 大脑下发的地址清单 → 内置派生规则，这样大脑换地址也不会失联。',
         dele='可以删（会重新探测一遍）。',
         peek='cat ~/.ai-agent/brain_cache'),
    dict(root='agent_home', path='agent.pid', kind='运行态', secret=False,
         when='ai-agent run 启动时写入；正常退出时自动删除',
         what='子 agent 进程号，方便你停它（kill $(cat agent.pid)）。',
         dele='可以删，下次运行会重建。',
         peek='cat ~/.ai-agent/agent.pid'),
    dict(root='agent_home', path='agent.log', kind='日志', secret=False,
         when='ai-agent 运行中持续追加',
         what='子 agent 的**干活记录**：领到哪个任务、每一步在本机执行了什么命令、'
              '什么时候回报完成。要查"它到底做了什么"，就看这个。',
         dele='可以删（会重建），但出问题时先留着。',
         peek='tail -50 ~/.ai-agent/agent.log'),
    dict(root='agent_home', path='run.out', kind='日志', secret=False,
         when='用 nohup ./ai-agent run >>~/.ai-agent/run.out 启动时产生',
         what='子 agent 的前台输出存档（启动横幅等）。',
         dele='可以删。',
         peek='tail -20 ~/.ai-agent/run.out'),
    dict(root='agent_home', path='versions/', kind='运行态', secret=False,
         when='自升级时临时创建',
         what='升级包下载到这里，校验通过后由**新版本自己**替换原文件，然后整个目录被删掉。',
         dele='正常情况下会自己消失；如果残留，说明升级中途失败过（可安全删除）。',
         peek='ls -l ~/.ai-agent/versions/ 2>/dev/null'),
    dict(root='agent_home', path='*.bak-*', kind='备份', secret=False,
         when='**你自己**按 README 的升级步骤做备份时产生（如 brain.bak-20261011-2230）',
         what='升级前的旧版本文件，出问题可以一键回滚。',
         dele='确认新版本稳定后可以删；想回滚就留着。',
         peek='ls -l ~/agent/*.bak-* 2>/dev/null'),
]

KIND_ORDER = ['程序', '配置', '密钥', '数据', '日志', '运行态', '备份']


# ==================== 现场事实（给控制台 + 给 AI） ====================
def _human(n: int) -> str:
    for unit in ('B', 'KB', 'MB', 'GB'):
        if n < 1024 or unit == 'GB':
            return f'{n:.1f} {unit}' if unit != 'B' else f'{n} B'
        n /= 1024.0
    return f'{n:.1f} GB'


def _stat(path: Path) -> dict:
    try:
        st = path.stat()
    except OSError:
        return {'exists': False, 'size': '', 'mtime': '', 'count': ''}
    if path.is_dir():
        try:
            cnt = len(list(path.iterdir()))
        except OSError:
            cnt = 0
        return {'exists': True, 'size': '', 'mtime': time.strftime('%Y-%m-%d %H:%M', time.localtime(st.st_mtime)),
                'count': f'{cnt} 项'}
    return {'exists': True, 'size': _human(st.st_size),
            'mtime': time.strftime('%Y-%m-%d %H:%M', time.localtime(st.st_mtime)), 'count': ''}


def gather(conf) -> list:
    """把登记表 + 现场事实（是否存在/大小/时间）合起来。"""
    r = roots()
    out = []
    for e in ENTRIES:
        base = r[e['root']]
        p = base / e['path'].rstrip('/') if e['path'].endswith('/') else base / e['path']
        if '*' in e['path']:                       # 通配（备份文件）
            found = sorted(base.glob(e['path'])) if base.is_dir() else []
            info = {'exists': bool(found), 'size': '', 'count': f'{len(found)} 个',
                    'mtime': time.strftime('%Y-%m-%d %H:%M',
                                           time.localtime(found[-1].stat().st_mtime)) if found else ''}
        else:
            info = _stat(p)
        out.append({**e, 'full': str(p), 'base': str(base), **info})
    return out


def conf_summary(conf) -> str:
    """配置里"设了什么"，敏感项打码。"""
    hot = ('BRAIN_BIND', 'BRAIN_PORT', 'AI_MODEL', 'MODE', 'AI_MAX_STEPS',
           'AI_MAX_STEPS_AUTO', 'STREAM', 'SHOW_REASONING', 'STDIO_ENCODING', 'BRAIN_URLS')
    lines = []
    for k in hot:
        lines.append(f'{k}={conf.get(k, "")}')
    for k in SECRET_KEYS:
        v = conf.get(k) or ''
        lines.append(f'{k}={"已设置" if v else "（空）"}')
    return '；'.join(lines)


def db_summary() -> str:
    """各表行数。还没初始化就不去连数据库（免得凭空建出一个空库文件）。"""
    if not C.DBPATH.exists():
        return '（还没初始化，暂无数据库）'
    try:
        from .store import q
    except Exception:                                # noqa: BLE001
        return '（读不到）'
    parts = []
    for t in ('agents', 'enrollments', 'tasks', 'releases', 'uploads', 'audit', 'nonces'):
        try:
            row = q(f'SELECT COUNT(*) AS n FROM {t}', one=True)
            parts.append(f'{t}={row["n"] if row else 0}')
        except Exception:                            # noqa: BLE001
            parts.append(f'{t}=?')
    return '，'.join(parts)


def facts_text(conf) -> str:
    """给模型看的"现场事实"：绝不含任何密钥明文。"""
    r = roots()
    lines = [f'程序目录: {r["program"]}',
             f'大脑数据目录: {r["brain_home"]}',
             f'子 agent 数据目录: {r["agent_home"]}'
             + ('' if agent_home().exists() else '（本机未安装子 agent）'),
             '',
             f'【brain.conf 实际配置】{conf_summary(conf)}',
             f'【brain.db 各表行数】{db_summary()}',
             '',
             '【文件清单（现场）】']
    for e in gather(conf):
        state = ('存在' if e['exists'] else '不存在')
        extra = e['size'] or e['count']
        lines.append(f'- [{e["kind"]}] {e["path"]} @ {e["base"]} → {state}'
                     f'{(" " + extra) if extra else ""}'
                     f'{(" " + e["mtime"]) if e["mtime"] else ""}')
        lines.append(f'    何时产生: {e["when"]}')
        lines.append(f'    用途: {e["what"]}')
        lines.append(f'    能否删除: {e["dele"]}')
        lines.append(f'    查看方式: {e["peek"]}')
    lines.append('')
    lines.append('【安全提示】signing.key 是升级签名的私钥，绝不外传；'
                 'brain.conf / agent.conf 里有密钥令牌，权限必须保持 600。')
    return '\n'.join(lines)
