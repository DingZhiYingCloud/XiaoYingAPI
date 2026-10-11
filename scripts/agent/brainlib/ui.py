# -*- coding: utf-8 -*-
"""终端输出与交互：颜色、几种固定样式、确认框。

样式约定（README 第 4 节有说明）：
    say/dim/good/warn/err   普通提示
    act()                   「动作」样式 ▶ —— 程序在执行，跟模型的思考/结果区分开
    confirm()               需要用户点头的操作
"""
from __future__ import annotations

import sys

AUTO_YES = False            # 由入口在解析到 -y/--yes 时置 True


def setup_stdio(encoding: str = 'utf-8'):
    """把标准输入/输出/错误统一成指定编码（默认 UTF-8），并容错。

    **为什么必须做**：有些服务器的 locale 是 C/POSIX，或者你用的终端/面板把中文按
    别的编码发过来，Python 读输入时会直接抛 UnicodeDecodeError，把整个程序打断——
    线上绝不能出现这种崩溃。这里统一 errors='replace'：宁可个别字符显示成 '?'，
    也绝不因为一个坏字节把程序搞挂。

    若你的终端确实是 GBK，在 brain.conf 里设 STDIO_ENCODING=gbk 即可。
    """
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding=encoding, errors='replace')
        except Exception:                            # noqa: BLE001
            pass                                     # 流不支持重配（如已被包装）就跳过

C_0 = '\033[0m'
C_DIM = '\033[2m'
C_B = '\033[1m'
C_G = '\033[32m'
C_Y = '\033[33m'
C_R = '\033[31m'
C_C = '\033[36m'

if not sys.stdout.isatty():                 # 不是真终端就别输出颜色码
    C_0 = C_DIM = C_B = C_G = C_Y = C_R = C_C = ''


def say(*a):
    print(*a)


def dim(*a):
    print(f'{C_DIM}{" ".join(str(x) for x in a)}{C_0}')


def good(*a):
    print(f'{C_G}{" ".join(str(x) for x in a)}{C_0}')


def warn(*a):
    print(f'{C_Y}{" ".join(str(x) for x in a)}{C_0}')


def err(*a):
    print(f'{C_R}{" ".join(str(x) for x in a)}{C_0}', file=sys.stderr)


def act(*a):
    """「动作/执行」样式：区别于模型的「思考」和最终「结果」"""
    print(f'{C_Y}▶ {" ".join(str(x) for x in a)}{C_0}')
    sys.stdout.flush()


def confirm(prompt: str, force: bool = False) -> bool:
    """要不要执行？三个选项，别让主人反复被问。

        y 执行一次 / n 跳过这一次 / a 以后都别问了

    force=True 时即使开了「完全放行」也必须真问一次（用于接新机器这种安全动作）。
    """
    global AUTO_YES
    if AUTO_YES and not force:
        dim('  （完全放行模式，直接干）')
        return True
    if not sys.stdin.isatty():
        warn('  （非交互输入：默认不执行；要自动执行请用 brain -y 或 MODE=auto）')
        return False
    try:
        ans = input(f'  {C_Y}{prompt} [y=执行 / n=跳过 / a=以后都别问]{C_0} ').strip().lower()
    except (EOFError, UnicodeDecodeError):
        return False
    if ans in ('a', 'auto'):
        AUTO_YES = True
        try:
            from . import conf as C
            C.set_key('MODE', 'auto')               # 记住挡位，下次启动也不问
        except Exception:                            # noqa: BLE001
            pass
        warn('  已切到「完全放行」挡：以后不再问你（已写入 brain.conf，重启也生效）。'
             '想切回来就输 /auto')
        return True
    return ans in ('y', 'yes', '是')


def mask_key(k: str) -> str:
    """Key 只显示首尾，用于 /conf 之类的地方。"""
    if not k:
        return '(未配置)'
    if len(k) <= 8:
        return k
    return f'{k[:5]}…{k[-4:]}'


def pad(s: str, width: int) -> str:
    """按**显示宽度**右侧补空格（中文算 2 列），用来对齐带中文的标签。

    Python 的 f'{x:<20}' 只按字符数算，中文会短一截、对不齐，所以单独做这个。
    """
    w = sum(2 if ord(c) > 0x2E7F else 1 for c in s)
    return s + ' ' * max(1, width - w)
