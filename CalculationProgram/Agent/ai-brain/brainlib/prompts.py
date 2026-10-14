# -*- coding: utf-8 -*-
"""提示词与技能：全部放在文本文件里，改提示词不用碰代码。

查找顺序（同名文件，后者优先）：
    1) <脚本目录>/prompts/        ← 随程序一起发布的默认值
    2) <BRAIN_HOME>/prompts/      ← 你自己的自定义（升级程序不会覆盖）

目录里有什么：
    system.md     系统提示词主体，含 {{ACTIONS}} / {{SKILLS}} / {{ENV}} 占位
    actions.md    可用动作清单（会被塞进 system.md 的 {{ACTIONS}} 处）
    skills/*.md   额外技能/背景知识，按文件名排序拼接进 {{SKILLS}}（README.md 除外）

想加一个“技能”（例如你们自己的运维规范），就在这里丢一个 .md 文件即可。
"""
from __future__ import annotations

import time
from pathlib import Path

from . import conf as C
from .util import os_pretty

PLACEHOLDER = '{{%s}}'


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding='utf-8', errors='replace').strip()
    except OSError:
        return ''


def _pick(name: str):
    """按优先级找文件：用户自定义 → 程序自带。找不到返回 None。"""
    for base in (C.PROMPTS_OVERRIDE, C.builtin_prompts_dir()):
        p = base / name
        if p.is_file():
            return p
    return None


def actions() -> str:
    p = _pick('actions.md')
    return _read(p) if p else ''


def skills() -> str:
    """把 prompts/skills/*.md 拼起来（README.md 跳过；用户目录优先，按文件名去重）。"""
    seen, texts = set(), []
    for base in (C.PROMPTS_OVERRIDE, C.builtin_prompts_dir()):
        d = base / 'skills'
        if not d.is_dir():
            continue
        for f in sorted(d.glob('*.md')):
            if f.name.lower() == 'readme.md' or f.name in seen:
                continue
            seen.add(f.name)
            body = _read(f)
            if body:
                texts.append(body)
    return '\n\n'.join(texts)


def env_block() -> str:
    """当前环境（每次对话开始时现取，保证时间和目录是最新的）。"""
    import getpass
    import os
    return (
        f'- 系统：{os_pretty()}\n'
        f'- 当前用户：{getpass.getuser()}\n'
        f'- 当前目录：{os.getcwd()}\n'
        f'- 时间：{time.strftime("%Y-%m-%d %H:%M:%S %Z")}'
    )


def system_prompt() -> str:
    """组装最终的系统提示词。缺 system.md 会抛出可读的错误（服务器不受影响）。"""
    p = _pick('system.md')
    if not p:
        raise FileNotFoundError(
            f'找不到提示词文件 system.md。\n'
            f'应在 {C.builtin_prompts_dir()}/system.md，或你自定义的 {C.PROMPTS_OVERRIDE}/system.md。\n'
            f'部署时请把 prompts/ 目录一起上传。'
        )
    tpl = _read(p)
    return (tpl.replace(PLACEHOLDER % 'ACTIONS', actions())
               .replace(PLACEHOLDER % 'SKILLS', skills())
               .replace(PLACEHOLDER % 'ENV', env_block()))
