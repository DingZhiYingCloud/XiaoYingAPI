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


def _read_line(prompt: str):
    """读一行（供逐条提问用）。非终端或读不到就返回 None。"""
    try:
        return input(f'  {C_DIM}{prompt}{C_0} ').strip()
    except (EOFError, UnicodeDecodeError):
        return None


def _show_points(points):
    """打印「它想请你拍板」一览（最多 4 条）。"""
    if not points:
        return
    print()
    print(f'  {C_Y}它想请你拍板（{len(points)} 条）：{C_0}')
    for i, s in enumerate(points, 1):
        q = str(s.get('q') or '').strip() or '（未说明）'
        d = str(s.get('default') or '').strip()
        tail = f'   {C_DIM}它倾向：{d}{C_0}' if d else ''
        print(f'   {i}) {q}{tail}')


def decide(prompt: str, suggestions=None):
    """需要动手前的确认（带 AI 的待拍板项）—— 返回 (verdict, note)。

    suggestions: 模型给的待拍板项，形如 [{'q': 问题, 'default': 它的倾向}]，最多 4 条。

    verdict:
        'yes'   照办（note 为空）
        'no'    跳过这一次
        'amend' 有修改意见；note 是给模型看的「主人意见」原文
    （选 a=以后都别问 时也返回 'yes'，并顺手把挡位切成 auto）
    """
    global AUTO_YES
    points = [s for s in (suggestions or [])
              if isinstance(s, dict) and (s.get('q') or s.get('default'))][:4]
    _show_points(points)

    if AUTO_YES:                                     # 完全放行：只打印，不阻塞
        dim('  （完全放行模式，不问，直接干）')
        return 'yes', ''
    if not sys.stdin.isatty():
        warn('  （非交互输入：默认不执行；要自动执行请用 brain -y 或 MODE=auto）')
        return 'no', ''

    # ① 逐条给意见（回车＝照它的倾向办；写了就回喂给模型改写任务）
    if points:
        dim('  逐条给意见（直接回车＝照它倾向办）：')
        notes = []
        for i, s in enumerate(points, 1):
            d = str(s.get('default') or '').strip()
            hint = f'{i} ❯' + (f'（它倾向：{d}）' if d else '')
            a = _read_line(hint)
            if a is None:
                return 'no', ''
            if a:
                notes.append(f'{i}. {str(s.get("q") or "").strip()} → 主人意见：{a}')
        if notes:
            return 'amend', '主人对本次下发的方案有修改意见：\n' + '\n'.join(notes)

    # ② 最终确认（也可直接打字说修改）
    dim('  （回车＝跳过；也可直接打字说你的修改）')
    raw = _read_line(f'{prompt} [y=执行 / n=跳过 / a=以后都别问]')
    if raw is None:
        return 'no', ''
    low = raw.lower()
    if low in ('a', 'auto'):
        AUTO_YES = True
        try:
            from . import conf as C
            C.set_key('MODE', 'auto')                # 记住挡位，下次启动也不问
        except Exception:                            # noqa: BLE001
            pass
        warn('  已切到「完全放行」挡：以后不再问你（已写入 brain.conf，重启也生效）。想切回来就输 /auto')
        return 'yes', ''
    if low in ('y', 'yes', '是'):
        return 'yes', ''
    if low in ('', 'n', 'no', '否'):
        return 'no', ''
    return 'amend', f'主人对本次下发的方案有修改意见：{raw}'


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
