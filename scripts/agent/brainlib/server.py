# -*- coding: utf-8 -*-
"""HTTP 服务：子 agent 连的就是这里；本机 CLI 也只通过这里操作数据。

对外端点（子 agent 用，全部要签名）：
    GET  /health                探活（免签，也用于子 agent“找大脑”）
    GET  /agent/install         下载子 agent 客户端（免签；用于“一行命令”安装）
    GET  /agent/pubkey          取升级公钥（免签；公钥本就公开，供子 agent 自动取回）
    POST /agent/enroll          发起注册（拿挑战码）
    POST /agent/enroll/verify   用注册口令应答挑战
    POST /agent/enroll/status   轮询批准结果（批准后拿到本机令牌）
    POST /agent/poll            领任务（长轮询）
    POST /agent/report          回传进度 / 结果
    POST /agent/heartbeat       心跳（在线 / 负载 / 磁盘）
    GET  /agent/update          检查有没有新版本（返回已签名包信息）
    GET  /agent/pkg/<ver>       下载升级包
    POST /agent/upload          上传文件（截图/日志/任意文件；签名 + 大小上限）
    POST /agent/bye             被拉黑的子 agent 回报“我已自毁”
    POST /agent/key             凭注册口令换“生产版解密口令”（文件里不存密钥）

公开只读（给“在线查看/下载”用；ID 不可猜）：
    GET  /f/<id>                查看/下载某个上传的文件（?dl=1 强制下载）

内部端点（只有本机 CLI 用，需管理令牌）：
    GET  /internal/pending   POST /internal/decide
    POST /internal/dispatch  POST /internal/tasks   POST /internal/block
    POST /internal/unblock   GET  /internal/agents
    GET  /internal/overview  POST /internal/run_local
"""
from __future__ import annotations

import hashlib
import hmac
import json
import mimetypes
import os
import re
import signal
import subprocess
import threading
import time
import traceback
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import VERSION
from . import conf as C
from . import notify, rendezvous, secure, ui
from .store import audit, init, q, x
from .util import new_id, now

ONLINE_WINDOW = 180          # 心跳超过这个秒数没来就算“离线”


def _os_name(v) -> str:
    """归一化子 agent 上报的系统名：只认 linux / win（不认的一律当 linux）。"""
    v = str(v or '').strip().lower()
    return v if v in ('linux', 'win') else 'linux'


# 上传文件：允许“直接内联在浏览器里看”的类型（图片 + 纯文本）。
# ⚠ 故意**不含** html / svg / js / xml —— 那是脚本，内联会在大脑的域名下执行，
#    等于给上传方一个"挂马位"；这类一律当附件下载。
_INLINE_TYPES = {
    '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
    '.gif': 'image/gif', '.webp': 'image/webp', '.bmp': 'image/bmp',
    '.txt': 'text/plain; charset=utf-8', '.log': 'text/plain; charset=utf-8',
    '.md': 'text/plain; charset=utf-8', '.csv': 'text/plain; charset=utf-8',
    '.tsv': 'text/plain; charset=utf-8', '.json': 'text/plain; charset=utf-8',
    '.ini': 'text/plain; charset=utf-8', '.conf': 'text/plain; charset=utf-8',
    '.yaml': 'text/plain; charset=utf-8', '.yml': 'text/plain; charset=utf-8',
}

_UNSAFE_NAME = re.compile(r'[^0-9A-Za-z\u4e00-\u9fff._\-]')


def _safe_name(s) -> str:
    """收拾上传的文件名：只留最后一层、去掉路径与奇怪字符、限长（防目录穿越/怪字符）。"""
    s = os.path.basename(str(s or '').replace('\\', '/')).strip()
    s = _UNSAFE_NAME.sub('_', s).lstrip('.')
    return s[:80]


def _hsize(n) -> str:
    """人类可读的大小：1234 → 1.2KB。"""
    n = float(n or 0)
    for u in ('B', 'KB', 'MB', 'GB'):
        if n < 1024 or u == 'GB':
            return f'{int(n)}{u}' if u == 'B' else f'{n:.1f}{u}'
        n /= 1024.0
    return f'{int(n)}B'


def _with_uploads(conf, task_id, result: str) -> str:
    """任务结束时，把它上传过的文件（链接）附在结论后面 —— 主人一眼就能点开看。"""
    try:
        ups = q('SELECT id,name,size FROM uploads WHERE task_id=? ORDER BY created_at', (task_id,))
    except Exception:                                # noqa: BLE001
        return result
    if not ups:
        return result
    base = C.public_base(conf)
    lines = ['', '', '【本任务上传的文件】']
    for u in ups:
        lines.append(f'- {u["name"]}（{_hsize(u["size"])}）→ {base}/f/{u["id"]}' if base
                     else f'- {u["name"]}（{_hsize(u["size"])}）')
    return result.rstrip() + '\n' + '\n'.join(lines)


_KEY_HITS = {}          # ip -> (次数, 窗口起点)：给 /agent/key 做暴力猜口令限速
_KEY_FAILS = {}         # ip -> 连续猜错次数（成功即清零，用于报警）


def _key_rate(ip, limit=8, window=60) -> bool:
    t = now()
    n, ts = _KEY_HITS.get(ip, (0, t))
    if t - ts > window:
        n, ts = 0, t
    n += 1
    _KEY_HITS[ip] = (n, ts)
    return n <= limit


def _key_fail(ip) -> int:
    n = _KEY_FAILS.get(ip, 0) + 1
    _KEY_FAILS[ip] = n
    return n


def _key_ok(ip):
    _KEY_FAILS.pop(ip, None)


def blocked_row(agent_id):
    """该 agent 是否已被拉黑（返回记录或 None）。"""
    if not agent_id:
        return None
    return q('SELECT * FROM blocked WHERE agent_id=?', (agent_id,), one=True)


class Handler(BaseHTTPRequestHandler):
    server_version = 'ai-brain'
    conf = {}

    def log_message(self, fmt, *args):     # 静音默认访问日志
        pass

    # ---------- 基础 ----------
    def _read(self) -> bytes:
        n = int(self.headers.get('Content-Length') or 0)
        return self.rfile.read(n) if n else b''

    def _send(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_bytes(self, data, ctype='application/octet-stream'):
        self.send_response(200)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    # ---------- 路由 ----------
    def do_GET(self):
        try:
            self._route_get()
        except Exception as exc:                     # noqa: BLE001
            self._fail(exc)

    def do_POST(self):
        try:
            self._route_post()
        except Exception as exc:                     # noqa: BLE001
            self._fail(exc)

    def _fail(self, exc):
        """任何未预期错误都变成 JSON 500：绝不让服务线程带着 traceback 死掉。"""
        C.log_line(f'[{self.path}] handler error: {traceback.format_exc()}')
        try:
            self._send({'error': f'服务内部错误：{type(exc).__name__}: {exc}'}, 500)
        except Exception:                            # noqa: BLE001
            pass

    def live_conf(self) -> dict:
        """现读配置文件（本进程的 conf 是启动时快照）。

        用于"下发给子 agent、改完必须立刻生效"的字段：会合信息（`brain rendezvous rotate
        / set` 改的就是它）、地址清单、解密口令 —— 这几项都不该逼你重启 `serve`。
        """
        return C.load()

    def _route_get(self):
        path = self.path.split('?')[0]
        if path == '/health':
            seed = self.live_conf().get('RDV_SEED') or ''
            return self._send({'ok': True, 'version': VERSION, 'time': now(),
                               'id': rendezvous.brain_id(seed) if seed else ''})
        m = re.match(r'^/f/([0-9a-fA-F]{8,64})$', path)
        if m:
            return self._file_view(m.group(1))          # 公开只读：上传的文件（ID 不可猜）
        if path == '/agent/install':
            return self._agent_install()
        if path == '/agent/pubkey':
            return self._agent_pubkey()
        if path == '/agent/update':
            return self._agent_update()
        m = re.match(r'^/agent/pkg/([\w.\-]+)$', path)
        if m:
            return self._agent_pkg(m.group(1))
        if path == '/internal/pending':
            return self._internal(lambda: {'pending': q(
                "SELECT id,agent_id,fingerprint,host,created_at FROM enrollments "
                "WHERE status='pending' ORDER BY created_at")})
        if path == '/internal/agents':
            return self._internal(lambda: {'agents': self._agents_view()})
        if path == '/internal/overview':
            return self._internal(self._overview)
        return self._send({'error': 'not found'}, 404)

    def _route_post(self):
        routes = {
            '/agent/enroll': self._agent_enroll,
            '/agent/enroll/verify': self._agent_enroll_verify,
            '/agent/enroll/status': self._agent_enroll_status,
            '/agent/poll': self._agent_poll,
            '/agent/report': self._agent_report,
            '/agent/heartbeat': self._agent_heartbeat,
            '/agent/bye': self._agent_bye,
            '/agent/notice': self._agent_notice,
            '/agent/upload': self._agent_upload,
            '/agent/key': self._agent_key,
            '/internal/decide': self._internal_decide,
            '/internal/dispatch': self._internal_dispatch,
            '/internal/tasks': self._internal_tasks,
            '/internal/block': self._internal_block,
            '/internal/unblock': self._internal_unblock,
            '/internal/run_local': self._internal_run_local,
        }
        fn = routes.get(self.path.split('?')[0])
        if not fn:
            return self._send({'error': 'not found'}, 404)
        return fn()

    # ---------- 子 agent：注册 ----------
    def _agent_enroll(self):
        body = self._read()
        d = secure.parse_body(body)
        if d is None:
            return self._send({'error': 'JSON 解析失败'}, 400)
        agent_id = str(d.get('agent_id') or '').strip()
        if not re.match(r'^[\w.\-]{1,64}$', agent_id):
            return self._send({'error': 'agent_id 非法（仅字母数字._-，≤64）'}, 400)
        if blocked_row(agent_id):
            return self._send({'error': '该机器已被拉黑，不能再注册'}, 403)
        enroll_id = new_id(12)
        challenge = new_id(24)
        x('INSERT INTO enrollments(id,agent_id,fingerprint,host,os,challenge,status,created_at)'
          ' VALUES(?,?,?,?,?,?,?,?)',
          (enroll_id, agent_id, str(d.get('fingerprint') or '')[:200],
           str(d.get('host') or '')[:200], _os_name(d.get('os')), challenge, 'pending', now()))
        audit('agent', 'enroll-begin', agent_id, '发起注册')
        return self._send({'status': 'pending', 'enroll_id': enroll_id,
                           'challenge': challenge})

    def _agent_enroll_verify(self):
        body = self._read()
        d = secure.parse_body(body)
        if d is None:
            return self._send({'error': 'JSON 解析失败'}, 400)
        row = q('SELECT * FROM enrollments WHERE id=?',
                (str(d.get('enroll_id') or ''),), one=True)
        if not row:
            return self._send({'error': 'enroll_id 不存在'}, 404)
        if row['status'] != 'pending':
            return self._send({'status': row['status']})
        proof = str(d.get('proof') or '')
        secret = self.conf['ENROLL_SECRET']
        expect = hmac.new(secret.encode(), row['challenge'].encode(),
                          hashlib.sha256).hexdigest()
        if not secret or not hmac.compare_digest(expect, proof):
            audit('agent', 'enroll-deny', row['agent_id'], '注册口令校验失败')
            return self._send({'status': 'denied', 'error': '注册口令不正确'}, 403)
        x('UPDATE enrollments SET secret_ok=1 WHERE id=?', (row['id'],))
        audit('agent', 'enroll-verified', row['agent_id'], '口令校验通过，等待人工批准')
        return self._send({'status': 'pending', 'verified': True})

    def _agent_enroll_status(self):
        body = self._read()
        d = secure.parse_body(body)
        if d is None:
            return self._send({'error': 'JSON 解析失败'}, 400)
        row = q('SELECT * FROM enrollments WHERE id=?',
                (str(d.get('enroll_id') or ''),), one=True)
        if not row:
            return self._send({'error': 'enroll_id 不存在'}, 404)
        if row['status'] == 'approved':
            live = self.live_conf()
            resp = {'status': 'approved', 'token': row['token'],
                    'brain_version': VERSION,
                    'brain_urls': live['BRAIN_URLS']}
            resp.update(rendezvous.payload(live))           # 下发会合信息（种子/模板/期号）
            return self._send(resp)
        if row['status'] == 'pending' and now() - row['created_at'] > 900:
            x("UPDATE enrollments SET status='expired' WHERE id=?", (row['id'],))
            return self._send({'status': 'expired'})
        return self._send({'status': row['status'], 'verified': bool(row['secret_ok'])})

    # ---------- 子 agent：任务 ----------
    def _agent_poll(self):
        body = self._read()
        row, e = secure.verify_agent(self, body)
        if e:
            return self._send({'error': e}, 401)
        # 被拉黑：先把“自毁指令”发给它，等它回过来后再一律拒绝
        b = blocked_row(row['agent_id'])
        if b:
            if not b['wipe_done']:
                return self._send({'wipe': True, 'reason': b['reason'] or '被管理员拉黑'})
            return self._send({'error': '已被拉黑'}, 403)
        deadline = now() + int(self.conf['POLL_TIMEOUT'])
        while True:
            t = q("SELECT * FROM tasks WHERE agent_id=? AND state='queued' "
                  "ORDER BY created_at LIMIT 1", (row['agent_id'],), one=True)
            if t:
                x("UPDATE tasks SET state='running', started_at=? WHERE id=?",
                  (now(), t['id']))
                return self._send({'task': {'id': t['id'], 'batch_id': t['batch_id'],
                                            'text': t['task'], 'created_at': t['created_at']}})
            if now() >= deadline:
                return self._send({'task': None})
            time.sleep(1.0)

    def _agent_report(self):
        body = self._read()
        row, e = secure.verify_agent(self, body)
        if e:
            return self._send({'error': e}, 401)
        d = secure.parse_body(body)
        if d is None:
            return self._send({'error': 'JSON 解析失败'}, 400)
        task_id = str(d.get('task_id') or '')
        state = str(d.get('state') or '')
        if state not in ('running', 'done', 'failed'):
            return self._send({'error': 'state 非法'}, 400)
        t = q('SELECT * FROM tasks WHERE id=? AND agent_id=?',
              (task_id, row['agent_id']), one=True)
        if not t:
            return self._send({'error': '任务不存在或不属于该 agent'}, 404)
        finished = now() if state in ('done', 'failed') else None
        result = str(d.get('result') or '')
        if state in ('done', 'failed'):
            result = _with_uploads(self.conf, task_id, result)   # 附上本任务上传的文件链接
        x('UPDATE tasks SET state=?, result=?, log=?, finished_at=? WHERE id=?',
          (state, result[:20000], str(d.get('log') or '')[:20000],
           finished, task_id))
        if state in ('done', 'failed'):
            audit('agent', f'task-{state}', row['agent_id'], f'任务 {task_id}', task_id)
        if state == 'failed':
            try:
                notify.notify(self.conf, f'taskfail:{row["agent_id"]}',
                              f'[ai-brain] {row["agent_id"]} 任务失败',
                              f'服务器：{row["agent_id"]}\n任务：{t["task"]}\n结果：{str(d.get("result") or "")[:500]}\n\n时间：{time.strftime("%F %T")}')
            except Exception:                        # noqa: BLE001
                pass
        return self._send({'ok': True})

    def _agent_heartbeat(self):
        body = self._read()
        row, e = secure.verify_agent(self, body)
        if e:
            return self._send({'error': e}, 401)
        if blocked_row(row['agent_id']):
            return self._send({'error': '已被拉黑'}, 403)
        d = secure.parse_body(body) or {}
        osv = _os_name(d.get('os')) if str(d.get('os') or '').strip() else ''
        x("UPDATE agents SET last_seen=?, version=?, load1=?, disk=?, mem=?, extra=?,"
          " os=COALESCE(NULLIF(?,''), os) WHERE agent_id=?",
          (now(), str(d.get('version') or '')[:32], str(d.get('load') or '')[:64],
           str(d.get('disk') or '')[:128], str(d.get('mem') or '')[:128],
           json.dumps(d.get('extra') or {}, ensure_ascii=False)[:1000], osv, row['agent_id']))
        live = self.live_conf()                             # 现读：改完立刻下发，不用重启 serve
        resp = {'ok': True, 'server_time': now(),
                'brain_urls': live['BRAIN_URLS']}
        resp.update(rendezvous.payload(live))               # 每次心跳同步会合信息（种子可轮换）
        return self._send(resp)

    def _agent_bye(self):
        """被拉黑的子 agent 来报「我已按指令自毁」，作为最后一条记录。"""
        body = self._read()
        row, e = secure.verify_agent(self, body)
        if e:
            return self._send({'error': e}, 401)
        d = secure.parse_body(body) or {}
        note = str(d.get('note') or '')[:200]
        if blocked_row(row['agent_id']):
            x('UPDATE blocked SET wipe_done=1 WHERE agent_id=?', (row['agent_id'],))
            audit('brain', 'agent-wiped', row['agent_id'], note or '收到自毁完成回报')
            try:
                notify.notify(self.conf, f'bye:{row["agent_id"]}',
                              f'[ai-brain] {row["agent_id"]} 已按指令自毁',
                              f'服务器：{row["agent_id"]} 已完成自毁（关于它的一切已删除）。\n'
                              f'备注：{note}\n\n时间：{time.strftime("%F %T")}')
            except Exception:                        # noqa: BLE001
                pass
        return self._send({'ok': True})

    def _agent_key(self):
        """凭注册口令发「生产版解密口令」——生产版文件里不存密钥，启动时来这儿换。

        首次部署时子 agent 还没有令牌，所以这个端点**不走签名**；靠注册口令 + 限速保护。
        """
        raw = self._read()
        d = secure.parse_body(raw)
        if d is None:                       # 兼容表单提交（生产版 stub 用 curl --data-urlencode）
            d = dict(urllib.parse.parse_qsl(raw.decode('utf-8', 'replace')))
        ip = self.client_address[0] if self.client_address else '?'
        xff = (self.headers.get('X-Forwarded-For') or '').split(',')[0].strip()
        if xff:                             # 反代后 client_address 全是 127.0.0.1，取真实来源
            ip = xff
        secret = str(d.get('secret') or '')
        live = self.live_conf()             # 现读：brain pack-key rotate 改的就是它，不该逼着重启 serve
        expect = live.get('ENROLL_SECRET') or ''
        if not expect or not secret or not hmac.compare_digest(secret, expect):
            # ⚠ 只对「猜错口令」限速：口令正确的正常取钥匙**不限速**。
            #   否则子 agent 重启 / 自升级时会连着来取几次，被自己人挡成 429，
            #   进而 systemd 反复重启 → 自锁。
            if not _key_rate(ip):
                notify.notify(self.conf, f'keyrate:{ip}', '[ai-brain] 有人在爆破解密口令',
                              f'IP {ip} 连续多次猜错注册口令，已被暂时限速。\n\n'
                              f'时间：{time.strftime("%F %T")}')
                return self._send({'error': '请求太频繁，稍后再试'}, 429)
            audit('agent', 'key-deny', '', f'ip={ip} 取解密口令：口令不正确')
            if _key_fail(ip) >= 5:
                notify.notify(self.conf, f'keyfail:{ip}', '[ai-brain] 有人在猜注册口令',
                              f'IP {ip} 已连续猜错注册口令 5 次以上，请查一下。\n\n'
                              f'时间：{time.strftime("%F %T")}')
            return self._send({'error': '口令不正确'}, 403)
        _key_ok(ip)                         # 口令正确：清掉失败与限速记录（正常重启用）
        _KEY_HITS.pop(ip, None)
        key = live.get('PACK_KEY') or ''
        if not key:
            return self._send({'error': '大脑还没配 PACK_KEY（brain init 会自动生成）'}, 404)
        # 同时下发“轮换过渡期的旧口令”：子 agent 先按新口令校验，不匹配再退到旧口令 ——
        # 这样轮换时，还没升级的老文件仍能启动，不会整片失联。
        old = live.get('PACK_KEY_OLD') or ''
        audit('agent', 'key-ok', '', f'ip={ip} 已下发解密口令')
        return self._send({'key': key, 'old': old})

    def _agent_notice(self):
        """子 agent 上报事件（如"我被清理过、已自我恢复"）→ 大脑据此给你发邮件报警。"""
        body = self._read()
        row, e = secure.verify_agent(self, body)
        if e:
            return self._send({'error': e}, 401)
        if blocked_row(row['agent_id']):
            return self._send({'error': '已被拉黑'}, 403)
        d = secure.parse_body(body) or {}
        kind = str(d.get('kind') or 'unknown')[:32]
        detail = str(d.get('detail') or '')[:1000]
        aid = row['agent_id']
        audit('agent', f'notice-{kind}', aid, detail)
        try:
            notify.notify(self.conf, f'notice:{aid}:{kind}',
                          f'[ai-brain] {aid} 报告：{kind}',
                          f'服务器：{aid}\n事件：{kind}\n详情：\n{detail}\n\n时间：{time.strftime("%F %T")}')
        except Exception:                            # noqa: BLE001
            C.log_line(f'notice notify error: {traceback.format_exc()}')
        return self._send({'ok': True})

    # ---------- 子 agent：上传文件 ----------
    def _agent_upload(self):
        """子 agent 上传文件（截图 / 日志 / 任意文件）。

        文件名与任务号放在 **query** 里 —— 它们会进 `handler.path`，被签名覆盖；
        请求体就是**文件原始字节**（它的 sha256 也在签名里）。有大小上限。
        """
        body = self._read()
        row, e = secure.verify_agent(self, body)
        if e:
            return self._send({'error': e}, 401)
        if blocked_row(row['agent_id']):
            return self._send({'error': '已被拉黑'}, 403)
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        name = _safe_name((qs.get('name') or [''])[0])
        task_id = str((qs.get('task') or [''])[0])[:64]
        if not name:
            return self._send({'error': '缺少 name 参数（文件名）'}, 400)
        if not body:
            return self._send({'error': '空文件'}, 400)
        limit = C.max_upload_bytes(self.conf)
        if len(body) > limit:
            return self._send({'error': f'文件太大：{_hsize(len(body))}，上限 {limit // (1024 * 1024)}MB'}, 413)
        aid = row['agent_id']
        fid = new_id(32)                                  # 128 位随机，公开链接靠它不可猜
        try:
            d = C.UPLOAD_DIR / aid
            d.mkdir(parents=True, exist_ok=True)
            p = d / f'{time.strftime("%Y%m%d-%H%M%S")}-{fid[:8]}-{name}'
            p.write_bytes(body)
        except OSError as exc:
            C.log_line(f'upload save error: {exc!r}')
            return self._send({'error': '大脑写入文件失败'}, 500)
        digest = hashlib.sha256(body).hexdigest()
        x('INSERT INTO uploads(id,agent_id,task_id,name,size,sha256,path,created_at)'
          ' VALUES(?,?,?,?,?,?,?,?)',
          (fid, aid, task_id, name, len(body), digest, str(p), now()))
        audit('agent', 'upload', aid, f'{name}（{_hsize(len(body))}）', task_id)
        base = C.public_base(self.conf)
        return self._send({'ok': True, 'id': fid, 'name': name, 'size': len(body),
                           'sha256': digest, 'url': f'{base}/f/{fid}' if base else ''})

    def _file_view(self, fid):
        """公开只读：在线查看 / 下载一个上传的文件（`?dl=1` 强制下载）。

        安全：只按 **ID 查库**拿路径（不拼用户输入），并校验路径确实在 uploads 目录内；
        能内联的只有图片和纯文本，其它（html/svg/js/压缩包/可执行…）一律当附件下载。
        """
        row = q('SELECT * FROM uploads WHERE id=?', (fid,), one=True)
        if not row:
            return self._send({'error': '文件不存在或已被删除'}, 404)
        try:
            p = Path(row['path']).resolve()
            p.relative_to(C.UPLOAD_DIR.resolve())         # 防目录穿越（万一路径被改过）
        except (ValueError, OSError):
            return self._send({'error': '文件不存在或已被删除'}, 404)
        if not p.is_file():
            return self._send({'error': '文件不存在或已被删除'}, 404)
        force_dl = bool((urllib.parse.parse_qs(
            urllib.parse.urlparse(self.path).query).get('dl') or [''])[0])
        ctype = _INLINE_TYPES.get(p.suffix.lower())
        if ctype and not force_dl:
            disp = 'inline'
        else:
            ctype, disp = 'application/octet-stream', 'attachment'
        data = p.read_bytes()
        self.send_response(200)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Content-Disposition',
                         f"{disp}; filename*=UTF-8''{urllib.parse.quote(row['name'])}")
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-Robots-Tag', 'noindex, nofollow')
        self.end_headers()
        self.wfile.write(data)

    # ---------- 子 agent：升级 ----------
    def _agent_install(self):
        """公开分发子 agent 客户端，供“一行命令”安装下载。

        ⚠ 这是**公开**端点（不走签名），所以只发**生产版密文**：
        优先发"已发布的最新升级包"（一定是加密生产版）；没有发布过就回退到程序目录里
        的 ai-agent，但**该文件若是明文（含 SYS_TASK）就拒绝分发** —— 否则等于把源码和
        提示词公开到网上，违背"隐藏自身"。
        """
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        osname = _os_name((qs.get('os') or [''])[0])
        rel = q('SELECT * FROM releases WHERE os=? ORDER BY created_at DESC LIMIT 1',
                (osname,), one=True)
        if rel:
            pkg = C.PKG_DIR / rel['filename']
            if pkg.exists():
                data = pkg.read_bytes()
                # 兜底：万一"发布"那一步被 --force 放过了明文，公开端点也绝不外发。
                if b'SYS_TASK' in data:
                    return self._send({'error': '拒绝分发：最新发布包是【明文开发版】（会泄露源码/提示词）。'
                                                '请重新发布加密生产版。'}, 403)
                return self._send_bytes(data, 'text/plain; charset=utf-8')
        path = Path(__file__).resolve().parent.parent / 'ai-agent'
        if osname == 'win':
            # Windows：只允许分发上面那条"已发布的最新生产版（密文）"。
            # 程序目录里的 win/ai-agent.ps1 是**明文开发版**，绝不能公开分发（会泄露全部逻辑与提示词）。
            return self._send({'error': '还没有可分发的 Windows 生产版：请先 tools/pack-agent.ps1 打包，'
                                        '再 brain release <打包产物> --os win --version <x> --notes "…"'}, 404)
        if not path.exists():
            return self._send({'error': '还没有可分发的子 agent：请先 brain release 一版生产版'}, 404)
        try:
            text = path.read_text(encoding='utf-8', errors='replace')
        except OSError:
            return self._send({'error': '读取 ai-agent 失败'}, 500)
        if re.search(r'\$?SYS_TASK\s*=', text):
            return self._send({'error': '拒绝分发：程序目录里的 ai-agent 是【明文开发版】。'
                                        '请用 tools/pack-agent.sh 打包后 brain release 一版生产版'}, 403)
        return self._send_bytes(path.read_bytes(), 'text/plain; charset=utf-8')

    def _agent_pubkey(self):
        """公开大脑的升级公钥（公钥本就公开），供子 agent 自动取回以校验升级包签名。"""
        if not C.SIGN_PUB.exists():
            return self._send({'error': '公钥不存在（请先 brain init）'}, 404)
        return self._send_bytes(C.SIGN_PUB.read_bytes(), 'text/plain; charset=utf-8')

    def _agent_update(self):
        row, e = secure.verify_agent(self, b'')
        if e:
            return self._send({'error': e}, 401)
        if blocked_row(row['agent_id']):
            return self._send({'error': '已被拉黑'}, 403)
        cur = (self.headers.get('X-Agent-Version') or '').strip()
        osname = _os_name(row.get('os'))
        rel = q('SELECT * FROM releases WHERE os=? ORDER BY created_at DESC LIMIT 1',
                (osname,), one=True)
        if not rel:
            return self._send({'version': None})
        if cur == rel['version']:
            return self._send({'version': rel['version'], 'up_to_date': True})
        # linux 老 agent 不认 ?os=，保持老 URL 形式；win 才带上 os
        url = f'/agent/pkg/{rel["version"]}' + ('' if osname == 'linux' else f'?os={osname}')
        return self._send({'version': rel['version'], 'up_to_date': False,
                           'sha256': rel['sha256'], 'sig': rel['sig'],
                           'url': url, 'notes': rel['notes']})

    def _agent_pkg(self, version):
        row, e = secure.verify_agent(self, b'')
        if e:
            return self._send({'error': e}, 401)
        if blocked_row(row['agent_id']):
            return self._send({'error': '已被拉黑'}, 403)
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        osname = _os_name((qs.get('os') or [''])[0])
        rel = q('SELECT * FROM releases WHERE version=? AND os=?', (version, osname), one=True)
        if not rel:
            return self._send({'error': '版本不存在'}, 404)
        path = C.PKG_DIR / rel['filename']
        if not path.exists():
            return self._send({'error': '升级包文件缺失'}, 404)
        return self._send_bytes(path.read_bytes())

    # ---------- 内部（本机 CLI） ----------
    def _internal(self, fn):
        ok, e = secure.verify_admin(self)
        if not ok:
            return self._send({'error': e}, 403)
        try:
            return self._send(fn())
        except Exception as exc:                     # noqa: BLE001
            return self._send({'error': str(exc)}, 500)

    def _internal_decide(self):
        def go():
            d = secure.parse_body(self._read()) or {}
            row = q('SELECT * FROM enrollments WHERE id=?',
                    (str(d.get('enroll_id') or ''),), one=True)
            if not row:
                return {'error': 'enroll_id 不存在'}
            if row['status'] != 'pending':
                return {'status': row['status']}
            if not d.get('allow'):
                x("UPDATE enrollments SET status='denied', decided_at=? WHERE id=?",
                  (now(), row['id']))
                audit('brain', 'enroll-denied', row['agent_id'], '人工拒绝')
                return {'status': 'denied'}
            token = new_id(48)
            x("UPDATE enrollments SET status='approved', token=?, decided_at=? WHERE id=?",
              (token, now(), row['id']))
            x('INSERT INTO agents(agent_id,token,fingerprint,host,os,version,created_at,last_seen)'
              ' VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(agent_id) DO UPDATE SET token=excluded.token,'
              ' fingerprint=excluded.fingerprint, host=excluded.host, os=excluded.os',
              (row['agent_id'], token, row['fingerprint'], row['host'],
               row.get('os') or 'linux', '', now(), 0))
            audit('brain', 'enroll-approved', row['agent_id'], '人工批准')
            return {'status': 'approved', 'agent_id': row['agent_id']}
        return self._internal(go)

    def _internal_block(self):
        def go():
            d = secure.parse_body(self._read()) or {}
            aid = str(d.get('agent_id') or '').strip()
            if not aid:
                return {'error': 'agent_id 为空'}
            if not q('SELECT 1 FROM agents WHERE agent_id=?', (aid,), one=True):
                return {'error': f'没有这台子 agent：{aid}'}
            reason = str(d.get('reason') or '')[:200]
            x('INSERT INTO blocked(agent_id,reason,at,wipe,wipe_done) VALUES(?,?,?,1,0)'
              ' ON CONFLICT(agent_id) DO UPDATE SET reason=excluded.reason, at=excluded.at,'
              ' wipe=1, wipe_done=0', (aid, reason, now()))
            audit('brain', 'block', aid, reason or '管理员拉黑')
            try:
                notify.notify(self.conf, f'block:{aid}',
                              f'[ai-brain] 已拉黑 {aid}',
                              f'服务器：{aid}\n已拉黑并下发自毁指令。\n原因：{reason or "（未填）"}\n\n时间：{time.strftime("%F %T")}')
            except Exception:                        # noqa: BLE001
                pass
            return {'ok': True, 'agent_id': aid}
        return self._internal(go)

    def _internal_unblock(self):
        def go():
            d = secure.parse_body(self._read()) or {}
            aid = str(d.get('agent_id') or '').strip()
            if not aid:
                return {'error': 'agent_id 为空'}
            x('DELETE FROM blocked WHERE agent_id=?', (aid,))
            audit('brain', 'unblock', aid, '管理员解除拉黑')
            return {'ok': True, 'agent_id': aid}
        return self._internal(go)

    def _internal_dispatch(self):
        def go():
            d = secure.parse_body(self._read()) or {}
            task_text = str(d.get('task') or '').strip()
            if not task_text:
                return {'error': '任务为空'}
            sel = d.get('agents') or 'all'
            if sel == 'all' or sel == ['all']:
                ids = [a['agent_id'] for a in self._agents_view() if a['online']]
            else:
                ids = [str(a) for a in (sel if isinstance(sel, list) else [sel])]
            if not ids:
                return {'error': '没有可用的在线 agent'}
            batch = new_id(8)
            created = []
            for aid in ids:
                tid = new_id(12)
                x('INSERT INTO tasks(id,batch_id,agent_id,task,state,created_at) '
                  "VALUES(?,?,?,?, 'queued',?)", (tid, batch, aid, task_text[:4000], now()))
                created.append(tid)
            audit('brain', 'dispatch', ','.join(ids), task_text, batch)
            return {'batch_id': batch, 'task_ids': created, 'agents': ids}
        return self._internal(go)

    def _internal_tasks(self):
        def go():
            d = secure.parse_body(self._read()) or {}
            ids = d.get('task_ids') or []
            if not ids:
                return {'tasks': []}
            ph = ','.join('?' * len(ids))
            return {'tasks': q(f'SELECT * FROM tasks WHERE id IN ({ph})', tuple(ids))}
        return self._internal(go)

    def _internal_run_local(self):
        def go():
            d = secure.parse_body(self._read()) or {}
            cmd = str(d.get('cmd') or '')
            if not cmd:
                return {'error': '命令为空'}
            audit('brain', 'run_local', 'brain-host', cmd)
            try:
                p = subprocess.run(['bash', '-lc', cmd], capture_output=True,
                                   timeout=int(self.conf['AI_CMD_TIMEOUT']))
                out = (p.stdout + p.stderr).decode('utf-8', 'replace')
                return {'rc': p.returncode, 'output': out[:20000]}
            except subprocess.TimeoutExpired:
                return {'rc': 124, 'output': '命令超时'}
        return self._internal(go)

    # ---------- 视图 ----------
    def _agents_view(self):
        out = []
        for r in q('SELECT * FROM agents ORDER BY agent_id'):
            b = blocked_row(r['agent_id'])
            out.append({
                'agent_id': r['agent_id'], 'host': r['host'], 'version': r['version'],
                'os': (r.get('os') or 'linux'),
                'online': bool(r['last_seen'] and now() - r['last_seen'] < ONLINE_WINDOW),
                'last_seen_ago': int(now() - r['last_seen']) if r['last_seen'] else None,
                'load1': r['load1'], 'disk': r['disk'], 'mem': r['mem'],
                'blocked': bool(b), 'wipe_done': bool(b['wipe_done']) if b else False,
            })
        return out

    def _overview(self):
        return {
            'version': VERSION,
            'agents': self._agents_view(),
            'pending': len(q("SELECT 1 FROM enrollments WHERE status='pending'")),
            'tasks_running': len(q("SELECT 1 FROM tasks WHERE state='running'")),
            'tasks_queued': len(q("SELECT 1 FROM tasks WHERE state='queued'")),
        }


def _offline_pass(conf, alerted):
    """跑一轮失联检查（抽出来便于验证）：返回"这一轮报给了谁"。"""
    fired = []
    if not notify.enabled(conf):
        return fired
    thr = int(conf.get('OFFLINE_ALERT_SEC') or 300)
    for a in q('SELECT agent_id,last_seen FROM agents'):
        aid, ls = a['agent_id'], a['last_seen'] or 0
        if not ls or blocked_row(aid):              # 从没心跳过 / 已拉黑：不报警
            continue
        gap = int(now() - ls)
        if gap > thr:
            if aid not in alerted:
                alerted[aid] = True
                fired.append(aid)
                notify.notify(conf, f'offline:{aid}',
                              f'[ai-brain] {aid} 失联了',
                              f'服务器：{aid}\n已失联约 {gap} 秒（阈值 {thr} 秒）。\n'
                              f'可能被安全软件清理、或服务/网络异常 —— 请上去看一眼。\n\n'
                              f'时间：{time.strftime("%F %T")}')
        else:
            alerted.pop(aid, None)                  # 回来了，下次再失联可再报
    return fired


def _offline_watch(conf):
    """后台巡检：子 agent 失联（心跳中断）超过阈值就发一次邮件报警 —— 这是"被清理"最可靠的信号。"""
    alerted = {}
    while True:
        try:
            _offline_pass(conf, alerted)
        except Exception:                                    # noqa: BLE001
            C.log_line(f'offline watch error: {traceback.format_exc()}')
        time.sleep(30)


class _Server(ThreadingHTTPServer):
    """自定义 server：线程里的异常记进日志，而不是往 stderr 喷 traceback。"""
    daemon_threads = True

    def handle_error(self, request, client_address):
        last = traceback.format_exc().strip().splitlines()[-1:]
        C.log_line(f'request error from {client_address}: {" ".join(last)}')


def serve(conf):
    """前台运行 HTTP 服务（brain serve）。绑不上端口就给一句人话，不抛 traceback。"""
    init()
    Handler.conf = conf
    bind, port = conf['BRAIN_BIND'], int(conf['BRAIN_PORT'])
    try:
        httpd = _Server((bind, port), Handler)
    except OSError as e:
        ui.err(f'✗ 无法监听 {bind}:{port} —— {e}')
        ui.dim('  端口可能已被占用（改 brain.conf 里的 BRAIN_PORT），或该地址不可绑定。')
        return 1
    C.ensure_home()
    try:
        C.PID_FILE.write_text(str(os.getpid()))
    except OSError:
        pass

    C.log_line(f'serve start {bind}:{port} v{VERSION}')
    ui.say(f'{ui.C_B}ai-brain v{VERSION}{ui.C_0} 监听 {bind}:{port}')
    threading.Thread(target=_offline_watch, args=(conf,), daemon=True).start()   # 失联巡检（发邮件）

    def _stop(*_):
        ui.say('\n正在停止…')
        threading.Thread(target=httpd.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        try:
            C.PID_FILE.unlink()
        except OSError:
            pass
    ui.say('已停止。')
    return 0
