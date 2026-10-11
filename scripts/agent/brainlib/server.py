# -*- coding: utf-8 -*-
"""HTTP 服务：子 agent 连的就是这里；本机 CLI 也只通过这里操作数据。

对外端点（子 agent 用，全部要签名）：
    GET  /health                探活（免签，也用于子 agent“找大脑”）
    POST /agent/enroll          发起注册（拿挑战码）
    POST /agent/enroll/verify   用注册口令应答挑战
    POST /agent/enroll/status   轮询批准结果（批准后拿到本机令牌）
    POST /agent/poll            领任务（长轮询）
    POST /agent/report          回传进度 / 结果
    POST /agent/heartbeat       心跳（在线 / 负载 / 磁盘）
    GET  /agent/update          检查有没有新版本（返回已签名包信息）
    GET  /agent/pkg/<ver>       下载升级包

内部端点（只有本机 CLI 用，需管理令牌）：
    GET  /internal/pending   POST /internal/decide
    POST /internal/dispatch  POST /internal/tasks
    GET  /internal/agents    GET  /internal/overview   POST /internal/run_local
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import signal
import subprocess
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import VERSION
from . import conf as C
from . import rendezvous, secure, ui
from .store import audit, init, q, x
from .util import new_id, now

ONLINE_WINDOW = 180          # 心跳超过这个秒数没来就算“离线”


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

    def _route_get(self):
        path = self.path.split('?')[0]
        if path == '/health':
            seed = self.conf.get('RDV_SEED') or ''
            return self._send({'ok': True, 'version': VERSION, 'time': now(),
                               'id': rendezvous.brain_id(seed) if seed else ''})
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
            '/internal/decide': self._internal_decide,
            '/internal/dispatch': self._internal_dispatch,
            '/internal/tasks': self._internal_tasks,
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
        enroll_id = new_id(12)
        challenge = new_id(24)
        x('INSERT INTO enrollments(id,agent_id,fingerprint,host,challenge,status,created_at)'
          ' VALUES(?,?,?,?,?,?,?)',
          (enroll_id, agent_id, str(d.get('fingerprint') or '')[:200],
           str(d.get('host') or '')[:200], challenge, 'pending', now()))
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
            resp = {'status': 'approved', 'token': row['token'],
                    'brain_version': VERSION,
                    'brain_urls': self.conf['BRAIN_URLS']}
            resp.update(rendezvous.payload(self.conf))      # 下发会合信息（种子/模板/期号）
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
        x('UPDATE tasks SET state=?, result=?, log=?, finished_at=? WHERE id=?',
          (state, str(d.get('result') or '')[:20000], str(d.get('log') or '')[:20000],
           finished, task_id))
        if state in ('done', 'failed'):
            audit('agent', f'task-{state}', row['agent_id'], f'任务 {task_id}', task_id)
        return self._send({'ok': True})

    def _agent_heartbeat(self):
        body = self._read()
        row, e = secure.verify_agent(self, body)
        if e:
            return self._send({'error': e}, 401)
        d = secure.parse_body(body) or {}
        x('UPDATE agents SET last_seen=?, version=?, load1=?, disk=?, mem=?, extra=? '
          'WHERE agent_id=?',
          (now(), str(d.get('version') or '')[:32], str(d.get('load') or '')[:64],
           str(d.get('disk') or '')[:128], str(d.get('mem') or '')[:128],
           json.dumps(d.get('extra') or {}, ensure_ascii=False)[:1000], row['agent_id']))
        resp = {'ok': True, 'server_time': now(),
                'brain_urls': self.conf['BRAIN_URLS']}
        resp.update(rendezvous.payload(self.conf))          # 每次心跳同步会合信息（种子可轮换）
        return self._send(resp)

    # ---------- 子 agent：升级 ----------
    def _agent_update(self):
        row, e = secure.verify_agent(self, b'')
        if e:
            return self._send({'error': e}, 401)
        cur = (self.headers.get('X-Agent-Version') or '').strip()
        rel = q('SELECT * FROM releases ORDER BY created_at DESC LIMIT 1', one=True)
        if not rel:
            return self._send({'version': None})
        if cur == rel['version']:
            return self._send({'version': rel['version'], 'up_to_date': True})
        return self._send({'version': rel['version'], 'up_to_date': False,
                           'sha256': rel['sha256'], 'sig': rel['sig'],
                           'url': f'/agent/pkg/{rel["version"]}',
                           'notes': rel['notes']})

    def _agent_pkg(self, version):
        row, e = secure.verify_agent(self, b'')
        if e:
            return self._send({'error': e}, 401)
        rel = q('SELECT * FROM releases WHERE version=?', (version,), one=True)
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
            x('INSERT INTO agents(agent_id,token,fingerprint,host,version,created_at,last_seen)'
              ' VALUES(?,?,?,?,?,?,?) ON CONFLICT(agent_id) DO UPDATE SET token=excluded.token,'
              ' fingerprint=excluded.fingerprint, host=excluded.host',
              (row['agent_id'], token, row['fingerprint'], row['host'], '', now(), 0))
            audit('brain', 'enroll-approved', row['agent_id'], '人工批准')
            return {'status': 'approved', 'agent_id': row['agent_id']}
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
            out.append({
                'agent_id': r['agent_id'], 'host': r['host'], 'version': r['version'],
                'online': bool(r['last_seen'] and now() - r['last_seen'] < ONLINE_WINDOW),
                'last_seen_ago': int(now() - r['last_seen']) if r['last_seen'] else None,
                'load1': r['load1'], 'disk': r['disk'], 'mem': r['mem'],
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
