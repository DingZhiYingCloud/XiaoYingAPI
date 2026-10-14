# -*- coding: utf-8 -*-
"""让大脑用大白话解读"每个文件是干什么的"（brain explain）。

做法：把 registry 里的文件说明书 + 现场事实（哪些存在、多大、什么时候改的、库里有多少条）
拼成提示词交给模型，由它用人话讲给主人听。**不会把任何密钥明文喂给模型**（敏感项只报"已设置"）。
"""
from __future__ import annotations

import sys

from . import llm, registry, render, ui

SYS = """你是「ai-brain」的运维助手，负责向主人解释这套程序在他机器上生成的每一个文件。

规则：
- **只依据**下面给出的【现场事实】回答，不要编造不存在的文件或行为。
- 用大白话讲，假设主人不懂 Linux；能用表格/列表就列清楚。
- 主人最关心这几点，回答时都要讲明白：这文件干什么用 / 什么时候产生 / 能不能删 / 删了会怎样 / 怎么看它。
- **不要**输出任何代码块，直接给结论。
- 提到密钥类文件（signing.key、brain.conf、agent.conf）时，提醒别外传、别贴聊天记录。
"""


def run(conf, question=None) -> int:
    if not conf.get('AI_API_KEY'):
        ui.err('大脑还没配置模型 Key，没法让 AI 解读。')
        ui.dim('  先用本地控制台看（不调模型）：brain files')
        return 1

    facts = registry.facts_text(conf)
    q = (question or '').strip() or (
        '请把这些文件逐个讲清楚：每个文件干什么用、什么时候产生、能不能删、删了会怎样、怎么看它。'
        '最后用一句话总结"哪些文件绝对不能删"。')
    msgs = [{'role': 'system', 'content': SYS},
            {'role': 'user', 'content': f'【现场事实】\n{facts}\n\n【主人的问题】\n{q}'}]

    show_r = conf.get('SHOW_REASONING', '1') != '0'
    r = render.ReplyRenderer(show_reasoning=show_r)
    sys.stdout.write(f'{ui.C_DIM}· 正在整理…{ui.C_0}')
    sys.stdout.flush()
    try:
        llm.call(conf, msgs, on_think=r.reasoning if show_r else None, on_content=r.content)
    except llm.LLMError as e:
        sys.stdout.write('\r\033[K')
        ui.err('✗', e)
        return 1
    r.finish()
    return 0
