# -*- coding: utf-8 -*-
"""配置与路径：所有“文件放哪、读哪份配置”都在这里定义，别的模块不要自己拼路径。

数据目录默认 `~/.ai-brain`，可用环境变量 `BRAIN_HOME` 换到任意目录。
"""
from __future__ import annotations

import os
import re
import time
from pathlib import Path

from .util import is_num

HOME = Path(os.environ.get('BRAIN_HOME') or (Path.home() / '.ai-brain'))
CONF = HOME / 'brain.conf'
DBPATH = HOME / 'brain.db'
SIGN_KEY = HOME / 'signing.key'
SIGN_PUB = HOME / 'signing.pub'
PKG_DIR = HOME / 'releases'
LOG_PATH = HOME / 'brain.log'
PID_FILE = HOME / 'brain.pid'
PROMPTS_OVERRIDE = HOME / 'prompts'          # 你自己的提示词（优先级高于程序自带）

# 所有可配置项及其默认值。改这里就能加新配置项（旧的配置文件缺项会自动用默认值）
DEFAULT_CONF = {
    'BRAIN_BIND': '127.0.0.1',       # 只监听本机；对外一律经 nginx + 域名 + HTTPS（别改成 0.0.0.0）
    'BRAIN_PORT': '8787',
    'PUBLIC_URL': '',                 # 大脑的对外地址，**必须** https://域名（如 https://brain.example.com[/ai-brain]）。
                                      # 本机 CLI 与子 agent 都只认它：http:// 或 IP 一律拒绝。
    'RDV_SEED': '',                   # 会合主密钥（init 自动生成）；子 agent 靠它算出未来的后台域名
    'RDV_PATTERN': 'xybrain-{h}.icu', # 会合域名模板，{h} 会被替换；用你买的 .icu 后缀
    'RDV_INDEX': '1',                 # 当前期号；换后台域名时 +1（用 brain rendezvous set <n>）
    'BRAIN_ADMIN_TOKEN': '',          # 自动生成（本机 CLI 用）
    'ENROLL_SECRET': '',              # 注册口令（部署子 agent 时用）
    'PACK_KEY': '',                   # 【生产版】解密口令：只存在大脑上，运行时凭注册口令在线取
    'PACK_KEY_OLD': '',               # 轮换过渡期的旧口令（brain pack-key rotate 写入；新口令生效后，
                                      # 让还没升级的子 agent 也能开；全部升级后 brain pack-key drop-old 清掉）
    'AI_BASE_URL': 'https://api.deepseek.com',
    'AI_MODEL': 'deepseek-v4-flash',
    'AI_API_KEY': '',                 # 大脑自己用的模型 Key
    'AI_MAX_STEPS': '20',             # 【manual 模式】一次提问最多来回几步
    'AI_MAX_STEPS_AUTO': '200',       # 【auto 模式】的兜底上限（等同“一直做下去”，只是防死循环）
    'MODE': 'manual',                 # manual=每个动作都要你确认；auto=完全放行：不问、不停，直到做完或失败
    'AI_CMD_TIMEOUT': '120',          # run_local 单条命令最长秒数
    'AI_API_TIMEOUT': '180',          # 单次模型请求最长秒数
    'POLL_TIMEOUT': '25',             # 子 agent 领任务的长轮询秒数
    'TASK_TIMEOUT': '300',            # 等所有服务器回报的最长秒数
    'BRAIN_URLS': '',                 # 下发给子 agent 的“大脑地址清单”
    'PUSH_BASE': 'https://www.xiaoyingapi.com',   # 通知（邮件）走你的「消息推送」服务
    'PUSH_APP_ID': '',                # 推送服务接入项目的 APPID
    'PUSH_APP_SECRET': '',            # 推送服务的 APPSECRET（签名密钥，务必保密）
    'PUSH_TO': '',                    # 报警收件人邮箱，多个用逗号分隔
    'PUSH_MIN_INTERVAL': '600',       # 同一类事件的最小发送间隔（秒），防刷邮件
    'OFFLINE_ALERT_SEC': '300',       # 子 agent 失联超过这个秒数就发邮件报警
    'STREAM': '1',                    # 1=流式输出（边生成边显示）；0=生成完整段再显示
    'SHOW_REASONING': '1',            # 1=显示模型思维链（💭 那一段）；0=不显示
    'STDIO_ENCODING': 'utf-8',        # 终端编码；若你的终端是 GBK，改成 gbk
}

NUMERIC_KEYS = ('BRAIN_PORT', 'RDV_INDEX', 'AI_MAX_STEPS', 'AI_MAX_STEPS_AUTO', 'AI_CMD_TIMEOUT',
                'AI_API_TIMEOUT', 'POLL_TIMEOUT', 'TASK_TIMEOUT',
                'PUSH_MIN_INTERVAL', 'OFFLINE_ALERT_SEC')


def mode(conf) -> str:
    """当前挡位（两种）：

        'manual' —— 每个动作（下发 / 本机执行）都要主人点确认
        'auto'   —— 完全放行：不问、不停，直到任务做完或彻底失败
    """
    v = str(conf.get('MODE', 'manual')).strip().lower()
    return 'auto' if v in ('auto', 'full', 'all', '1', 'yes', 'on') else 'manual'


def is_auto(conf) -> bool:
    return mode(conf) == 'auto'


_DOMAIN_RE = re.compile(r'([A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,}$')
_IPV4_RE = re.compile(r'\d{1,3}(\.\d{1,3}){3}$')


def is_https_domain(url: str) -> bool:
    """只认 https://域名；http://、IP（v4/v6）、localhost 一律不合格。"""
    if not url or not url.startswith('https://'):
        return False
    host = url[len('https://'):].split('/', 1)[0].split('?', 1)[0].split('#', 1)[0]
    if host.startswith('['):                      # IPv6 字面量
        return False
    if ':' in host:                               # host:port → 取 host
        host = host.split(':', 1)[0]
    host = host.rstrip('.')
    if not host or host.lower() == 'localhost':
        return False
    if _IPV4_RE.match(host):
        return False
    return bool(_DOMAIN_RE.match(host))


def public_base(conf) -> str:
    """大脑的对外根地址（本机 CLI 与子 agent 都只用它）。不合格则返回空串。"""
    u = str(conf.get('PUBLIC_URL') or '').strip().rstrip('/')
    return u if is_https_domain(u) else ''


def script_dir() -> Path:
    """brain 脚本所在目录（brainlib 的上一层）。"""
    return Path(__file__).resolve().parent.parent


def builtin_prompts_dir() -> Path:
    """随程序一起发布的默认提示词目录。"""
    return script_dir() / 'prompts'


def ensure_home():
    HOME.mkdir(parents=True, exist_ok=True)


def load() -> dict:
    """读配置：默认值 ← 配置文件 ← 环境变量（越靠后优先级越高）"""
    conf = dict(DEFAULT_CONF)
    if CONF.exists():
        for line in CONF.read_text(encoding='utf-8', errors='replace').splitlines():
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            k, v = line.split('=', 1)
            conf[k.strip()] = v.strip()
    for k in list(conf):
        if os.environ.get(k):
            conf[k] = os.environ[k]
    for k in NUMERIC_KEYS:                      # 防呆：数字项写坏了就退回默认
        if not is_num(conf.get(k)):
            conf[k] = DEFAULT_CONF[k]
    return conf


def save(conf: dict):
    """写回配置。

    只覆盖已知键；用户在文件里自己加的其它行**原样保留**（不会因为重新 init 被抹掉）。
    """
    ensure_home()
    keep = []
    if CONF.exists():
        for line in CONF.read_text(encoding='utf-8', errors='replace').splitlines():
            s = line.strip()
            if not s or s.startswith('#') or '=' not in s:
                continue
            if s.split('=', 1)[0].strip() not in DEFAULT_CONF:
                keep.append(s)
    old = os.umask(0o077)
    try:
        with open(CONF, 'w', encoding='utf-8') as fh:
            for k in DEFAULT_CONF:
                fh.write(f'{k}={conf.get(k, "")}\n')
            for line in keep:
                fh.write(line + '\n')
    finally:
        os.umask(old)
    try:
        os.chmod(CONF, 0o600)
    except OSError:
        pass


def set_key(key: str, value: str):
    """就地改**一个**配置项：只动那一行，其它行原样保留，也不受环境变量影响。

    用它是为了安全地“记住”某个开关（例如 /auto 把 AUTO_CONFIRM=1 写进去），
    而不是把整份配置重写一遍。
    """
    ensure_home()
    lines, found = [], False
    if CONF.exists():
        for line in CONF.read_text(encoding='utf-8', errors='replace').splitlines():
            s = line.strip()
            if s and not s.startswith('#') and '=' in s and s.split('=', 1)[0].strip() == key:
                lines.append(f'{key}={value}')
                found = True
            else:
                lines.append(line)
    if not found:
        lines.append(f'{key}={value}')
    old = os.umask(0o077)
    try:
        with open(CONF, 'w', encoding='utf-8') as fh:
            fh.write('\n'.join(lines).rstrip('\n') + '\n')
    finally:
        os.umask(old)
    try:
        os.chmod(CONF, 0o600)
    except OSError:
        pass


def log_line(msg: str):
    """追加一行运行日志（供排查用）。"""
    try:
        ensure_home()
        with open(LOG_PATH, 'a', encoding='utf-8') as fh:
            fh.write(f'{time.strftime("%Y-%m-%d %H:%M:%S")} {msg}\n')
    except OSError:
        pass
