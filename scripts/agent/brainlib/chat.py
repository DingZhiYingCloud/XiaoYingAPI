# -*- coding: utf-8 -*-
"""对话 CLI：把用户的大白话变成「动作」，执行后把结果回喂给模型，直到它给出结论。

这是唯一会调用大模型的地方（服务端不调模型）。
"""
from __future__ import annotations

import json
import re
import sys
import time

from . import VERSION
from . import api as apicli
from . import conf as C
from . import llm, prompts, render, ui
from .util import now

ACTION_RE = re.compile(r'```(?:json|JSON)?\s*(\{[\s\S]*?\})\s*```')


def extract_action(text: str):
    """从模型回复里取出那个 json 动作块（没有就返回 None）。"""
    m = ACTION_RE.search(text or '')
    if not m:
        return None
    try:
        obj = json.loads(m.group(1))
    except ValueError:
        return None
    return obj if isinstance(obj, dict) and obj.get('action') else None


# ==================== 执行一个动作 ====================
def _do_action(conf, action) -> str:
    """执行动作，返回一段文本（这段文本会被回喂给模型，不直接给用户看）。"""
    name = action.get('action')

    if name == 'list_agents':
        r, e = apicli.api(conf, 'GET', '/internal/agents')
        if e:
            return f'查询失败：{e}'
        rows = (r or {}).get('agents') or []
        if not rows:
            return '当前没有任何子 agent 接入。'
        lines = [f'{a["agent_id"]}｜{"在线" if a["online"] else "离线"}｜'
                 f'负载 {a["load1"] or "-"}｜磁盘 {a["disk"] or "-"}｜版本 {a["version"] or "-"}'
                 for a in rows]
        return '当前服务器：\n' + '\n'.join(lines)

    if name == 'dispatch':
        task = str(action.get('task') or '').strip()
        sel = action.get('agents') or 'all'
        if not task:
            return '任务为空，未下发。'
        r, e = apicli.api(conf, 'GET', '/internal/agents')
        if e:
            return f'查询失败：{e}'
        agents = (r or {}).get('agents') or []
        if sel in ('all', ['all']):
            targets = [a['agent_id'] for a in agents if a['online']]
        else:
            wanted = sel if isinstance(sel, list) else [sel]
            targets = [a['agent_id'] for a in agents if a['agent_id'] in wanted]
        if not targets:
            return '没有匹配到的在线子 agent，无法下发。'
        ui.act(f'将在 {len(targets)} 台执行：{", ".join(targets)}')
        ui.act(f'任务：{task}')
        if not ui.confirm('确认下发？'):
            return '【系统】用户拒绝了本次下发。请换一种做法，或询问用户。'
        r, e = apicli.api(conf, 'POST', '/internal/dispatch',
                          {'agents': targets, 'task': task})
        if e or (r or {}).get('error'):
            return f'下发失败：{e or (r or {}).get("error")}'
        ids = r['task_ids']
        ui.act(f'已下发 {len(ids)} 条任务，等待各服务器回报…')
        deadline = now() + int(conf['TASK_TIMEOUT'])
        while now() < deadline:
            tr, _ = apicli.api(conf, 'POST', '/internal/tasks', {'task_ids': ids})
            tasks = (tr or {}).get('tasks') or []
            if tasks and all(t['state'] in ('done', 'failed') for t in tasks):
                break
            time.sleep(2)
        tr, _ = apicli.api(conf, 'POST', '/internal/tasks', {'task_ids': ids})
        tasks = (tr or {}).get('tasks') or []
        lines = []
        for t in tasks:
            st = {'done': '成功', 'failed': '失败', 'running': '超时未完成',
                  'queued': '超时未开始'}.get(t['state'], t['state'])
            body = (t['result'] or '').strip() or '(无结果)'
            lines.append(f'【{t["agent_id"]}】{st}：{body}')
        return '各服务器回报如下：\n' + '\n'.join(lines)

    if name == 'run_local':
        cmd = str(action.get('cmd') or '').strip()
        if not cmd:
            return '命令为空。'
        ui.act(f'将在本机（大脑所在机器）执行：{cmd}')
        if not ui.confirm('确认执行？'):
            return '【系统】用户拒绝了本机命令。'
        r, e = apicli.api(conf, 'POST', '/internal/run_local', {'cmd': cmd},
                          timeout=int(conf['AI_CMD_TIMEOUT']) + 10)
        if e or (r or {}).get('error'):
            return f'执行失败：{e or (r or {}).get("error")}'
        out = (r.get('output') or '').strip() or '(无输出)'
        return f'退出码={r.get("rc")}\n{out[:6000]}'

    return f'未知动作：{name}'


# ==================== 待批准的新机器 ====================
def _check_pending(conf):
    r, e = apicli.api(conf, 'GET', '/internal/pending')
    if e:
        return
    for p in (r or {}).get('pending') or []:
        ui.say()
        ui.warn('⚠ 新机器请求加入：')
        ui.say(f'    agent_id : {p["agent_id"]}')
        ui.say(f'    主机信息 : {p.get("host") or "-"}')
        ui.say(f'    指纹     : {(p.get("fingerprint") or "-")[:60]}')
        # 接新机器属于“安全动作”：即使开了完全放行，也必须主人亲自点头
        if ui.confirm('允许它接入吗？', force=True):
            d, _ = apicli.api(conf, 'POST', '/internal/decide',
                              {'enroll_id': p['id'], 'allow': True})
            if (d or {}).get('error'):
                ui.err('    批准失败：', d['error'])
            else:
                ui.good(f'    已批准 {p["agent_id"]}')
        else:
            apicli.api(conf, 'POST', '/internal/decide',
                       {'enroll_id': p['id'], 'allow': False})
            ui.warn(f'    已拒绝 {p["agent_id"]}')


def _max_steps(conf) -> int:
    """一次提问最多来回几步。

    manual 挡用 AI_MAX_STEPS；auto 挡用 AI_MAX_STEPS_AUTO（大到等同“一直做下去”，
    只是防止模型兜圈子停不下来）。
    """
    key = 'AI_MAX_STEPS_AUTO' if ui.AUTO_YES else 'AI_MAX_STEPS'
    default = 200 if ui.AUTO_YES else 20
    try:
        return max(1, int(conf.get(key) or default))
    except (TypeError, ValueError):
        return default


# ==================== 一轮问答 ====================
def _one_round(conf, hist, question: str):
    hist.append({'role': 'user', 'content': question})
    cap = _max_steps(conf)
    for _ in range(cap):
        sys.stdout.write(f'{ui.C_DIM}· 思考中…{ui.C_0}')
        sys.stdout.flush()
        r = render.ReplyRenderer(show_reasoning=(conf.get('SHOW_REASONING', '1') != '0'))
        on_think = r.reasoning if conf.get('SHOW_REASONING', '1') != '0' else None
        try:
            llm.call(conf, hist, on_think=on_think, on_content=r.content)
        except llm.LLMError as e:
            sys.stdout.write('\r\033[K')
            ui.err('✗', e)
            return
        reply = r.finish()
        if not reply:
            ui.err('✗ 模型没有返回内容（可能被限流）。稍后重试或换个问法。')
            return
        hist.append({'role': 'assistant', 'content': reply})
        action = extract_action(reply)
        if not action:
            return                                   # 【结果】已给出，本轮结束
        result = _do_action(conf, action)
        hist.append({'role': 'user',
                     'content': f'【动作执行结果】\n{result}\n\n请继续：需要动作就再给一个 json 块；'
                                f'已可汇报就直接给结论。'})
    ui.warn(f'⚠ 还没做完就停了：达到步数上限（{cap}）—— 任务可能只做了一半，这不是失败。')
    ui.dim('  直接输入「继续」，我就接着往下做；')
    ui.dim(f'  想让它一口气做完：把 brain.conf 里的 AI_MAX_STEPS 调大（现在 {conf["AI_MAX_STEPS"]}），')
    ui.dim('  或输 /auto 切到「完全放行」挡 —— 那一挡不看这个上限，一直做到完或彻底失败。')


HELP = """能直接说：
  看看磁盘和内存还剩多少
  网站打不开了，帮我查查为什么
  让 server-1 和 server-2 各自重启一下 nginx

命令：
  /agents    列出所有服务器与在线状态
  /status    大脑服务与任务概况
  /pending   待批准的新机器
  /auto      切换挡位：手动审核 ⇄ 完全放行（写进 brain.conf，重启也生效）
  /help      本帮助
  /exit      退出（Ctrl-D 也行）

两个挡位（brain.conf 里也能直接写 MODE=manual / MODE=auto）：
  manual 手动审核 —— 每个动作执行前问你一次（默认）
  auto   完全放行 —— 不问、不停，一直做到任务完成或彻底失败
"""


def _banner(conf):
    ui.say(f'{ui.C_B}ai-brain v{VERSION}{ui.C_0} '
           f'{ui.C_DIM}· 用大白话指挥你的多台服务器（模型 {conf["AI_MODEL"]}）{ui.C_0}')
    if ui.AUTO_YES:
        ui.warn('⚡ 挡位：完全放行 —— 不问、不停，直到做完或彻底失败（输 /auto 切回手动审核）')
    else:
        ui.dim('挡位：手动审核 —— 每个动作执行前问你一次；不想被问就输 /auto（完全放行）')
    if conf.get('STREAM', '1') == '0':
        ui.dim('输出模式：整段返回（STREAM=0）')
    ui.dim('直接说需求即可；/help 看命令，/exit 退出。')


def _log_exc(what: str, exc: Exception):
    """把异常写进日志，并给用户一句人话——绝不把 traceback 喷到脸上、也绝不让程序退出。"""
    import traceback
    C.log_line(f'{what}: {traceback.format_exc()}')
    ui.err(f'✗ {what}：{type(exc).__name__}: {exc}')
    ui.dim('  已记录日志；可以继续输入，或 /exit 退出。')


def run(conf, question=None) -> int:
    """question 给了就先问那一句：在终端里会接着留在对话中，被脚本/管道调用则问完退出。
    没给就直接进对话。"""
    if not conf['AI_API_KEY']:
        ui.err('大脑还没配置模型 Key。请编辑 ' + str(C.CONF) + ' 填入 AI_API_KEY')
        return 1
    if not apicli.ensure_server(conf):
        return 1
    try:
        sysmsg = prompts.system_prompt()
    except FileNotFoundError as e:
        ui.err('✗ 提示词加载失败：')
        ui.err(str(e))
        return 1
    hist = [{'role': 'system', 'content': sysmsg}]

    if question:
        _check_pending(conf)
        _one_round(conf, hist, question)
        # 只有“人肉在终端里跑”时才继续留在会话里；被脚本/管道调用（stdin 不是终端）时
        # 仍按一次性执行、完事退出 —— 免得“随口打了一句就把整个会话退掉”。
        if not sys.stdin.isatty():
            return 0

    _banner(conf)
    while True:
        try:
            _check_pending(conf)
            line = input(f'{ui.C_C}你 ❯ {ui.C_0}')
        except (EOFError, KeyboardInterrupt):
            ui.say()
            break
        except UnicodeDecodeError:
            ui.warn('这次输入里有无法识别的字节（已忽略）。若反复出现，说明你终端的编码不是 UTF-8：'
                    '可在 brain.conf 里加一行 STDIO_ENCODING=gbk')
            continue
        except Exception as exc:                     # noqa: BLE001
            _log_exc('读取输入时出错', exc)
            continue

        line = (line or '').strip()
        if not line:
            continue
        try:
            if line in ('/exit', '/quit', 'exit', 'quit'):
                break
            if line == '/help':
                ui.say(HELP)
            elif line == '/agents':
                ui.say(_do_action(conf, {'action': 'list_agents'}))
            elif line == '/status':
                from . import admin
                admin.cmd_status(conf)
            elif line == '/pending':
                _check_pending(conf)
            elif line == '/auto':
                ui.AUTO_YES = not ui.AUTO_YES
                conf['MODE'] = 'auto' if ui.AUTO_YES else 'manual'
                try:
                    C.set_key('MODE', conf['MODE'])
                except Exception as e:               # noqa: BLE001
                    _log_exc('写配置失败（本次会话仍然生效）', e)
                if ui.AUTO_YES:
                    ui.warn('⚡ 已切到「完全放行」挡：你说什么它直接做，不再问你，'
                            '也不再受步数上限限制，一直做到完或彻底失败。'
                            '（已写入 brain.conf，重启也生效；再输 /auto 切回手动审核）')
                else:
                    ui.good('已切回「手动审核」挡：每个动作执行前都会问你一次。')
            else:
                _one_round(conf, hist, line)
        except BrokenPipeError:
            break                                    # 输出被管道掐断，安静退出
        except KeyboardInterrupt:
            ui.say()
        except Exception as exc:                     # noqa: BLE001
            _log_exc('处理这一轮时出错', exc)
    ui.dim('再见。')
    return 0
