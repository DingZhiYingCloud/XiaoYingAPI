# -*- coding: utf-8 -*-
"""流式渲染：把模型的增量输出渲染成「思考」和「结果」两种截然不同的样式。

    思考模式（暗色 `· 思考 `）：模型在“想”——打算做什么、为什么
    结果模式（高亮框 `── 结果 ──`）：模型给你的最终答复
    （另有「动作」样式 ▶ 由 ui.act() 打印，是程序自己在干活，不是模型在说话）

模型被要求每条回复都用 `[思考]` 或 `[结果]` 开头；万一没写，就按
「有代码块＝思考，没代码块＝结果」兜底。

两种输出模式（STREAM=1/0）共用本类：整段模式只是“一次给一大块增量”而已。
"""
from __future__ import annotations

import sys

from . import ui

MARKS = (('[思考]', 'think'), ('[结果]', 'result'))
CLASSIFY_AT = 24          # 攒够这么多字符还没看到标记，就按“没有标记”来判断


class ReplyRenderer:
    def __init__(self, show_reasoning: bool = True):
        self.text = ''              # 原始完整回复（含标记，用于回灌给模型）
        self.style = None           # None / 'think' / 'result'
        self._pending = ''          # 还没判断出样式的缓冲
        self._hint_cleared = False
        self._reasoning = False
        self.show_reasoning = show_reasoning

    # ---------- 内部 ----------
    def _clear_hint(self):
        """把开头那句 “· 思考中…” 擦掉，只擦一次。"""
        if not self._hint_cleared:
            sys.stdout.write('\r\033[K')
            sys.stdout.flush()
            self._hint_cleared = True

    def _write(self, text):
        if text:
            sys.stdout.write(text)
            sys.stdout.flush()

    def _begin(self, style):
        if self.style == style:
            return
        self.style = style
        self._clear_hint()
        if self._reasoning:                       # 从思维链切到正式输出
            self._write(f'{ui.C_0}\n')
            self._reasoning = False
        if style == 'think':
            self._write(f'{ui.C_0}{ui.C_DIM}· 思考 ')
        else:
            self._write(f'{ui.C_0}{ui.C_G}── 结果 {"─" * 26}{ui.C_0}\n{ui.C_B}')
        sys.stdout.flush()

    def _classify(self, text):
        s = text.lstrip()
        for mark, style in MARKS:
            if s.startswith(mark):
                return style, text.replace(mark, '', 1).lstrip()
        if '```' in text:
            return 'think', text
        if len(text) >= CLASSIFY_AT:              # 没标记也没代码块 → 多半是最终结论
            return 'result', text
        return None, text

    # ---------- 外部 ----------
    def reasoning(self, delta):
        """思维链（reasoner 类模型才有）"""
        if not self.show_reasoning:
            return
        if self.style is None and not self._reasoning:
            self._clear_hint()
            self._write(f'{ui.C_DIM}💭 思考中：')
            self._reasoning = True
        self._write(delta)

    def content(self, delta):
        self.text += delta
        if self.style is not None:
            self._write(delta)
            return
        self._pending += delta
        style, stripped = self._classify(self._pending)
        if style is None:
            return                                # 还不能判断，先攒着
        self._pending = ''
        self._begin(style)
        self._write(stripped)

    def finish(self) -> str:
        if self.style is None:                    # 回复太短，来不及判断
            self._begin('think')
            self._write(self._pending)
            self._pending = ''
        if self.style == 'result':
            self._write(f'{ui.C_0}\n{ui.C_G}{"─" * 34}{ui.C_0}\n')
        else:
            self._write(f'{ui.C_0}\n')
        sys.stdout.flush()
        return self.text.strip()
