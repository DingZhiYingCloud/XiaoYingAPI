"""全量 API 冒烟测试脚本（配置驱动，真实 HTTP 调用）

用途：
    发布上线前（本地/预发）与上线后（线上）各跑一遍，快速确认全部 API 可用。

特点：
    - 覆盖：自动枚举 Django 全部 /api/ 路由，与本脚本用例清单比对，输出「未覆盖」清单
    - 参数：由 scripts/api_smoke_config.json 预填；支持 ${变量} 引用 vars 或前序响应（串联调用）
    - 签名：自动按项目 HMAC-SHA256 规则签名（GET/POST 覆盖全部参数，PATCH/DELETE 仅签 query，与中间件一致）
    - 凭据：优先用配置/环境变量的 app_id+app_secret（可测线上）；未提供且本机可访问数据库时，
            自动创建一个临时接入项目并在结束时删除
    - 判据：HTTP 200 且业务 code 命中 expect（默认 [10000]）；缺参数/缺变量的用例记为 SKIP
    - 结果：控制台汇总 + 可选 JSON 报告；存在 FAIL 时进程退出码非 0（可接 CI）

用法：
    # 本地（服务已在 8000 端口运行）
    .venv\\Scripts\\python.exe scripts\\test_all_api.py

    # 只测某个服务
    .venv\\Scripts\\python.exe scripts\\test_all_api.py --only mailcx

    # 线上：配置或环境变量提供 app_id/app_secret
    set XYAPI_APP_ID=app_xxx & set XYAPI_APP_SECRET=sk_xxx
    .venv\\Scripts\\python.exe scripts\\test_all_api.py --base https://api.example.com

    # 输出 JSON 报告 / 只看用例清单 / 跳过覆盖率检查
    ... --report smoke_report.json
    ... --list
    ... --no-coverage

参数文件：scripts/api_smoke_config.json（首次运行若不存在会自动生成模板）。
"""
import argparse
import json
import os
import re
import secrets
import sys
import time
from types import SimpleNamespace

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'XiaoYingAPI.settings')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import django

django.setup()

import requests

from API.apis.user_center.sign import build_sign
from API.models import UserApp

_HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CONFIG = os.path.join(_HERE, 'api_smoke_config.json')

_VAR_RE = re.compile(r'\$\{([^}]+)\}')
_CONVERTER_RE = re.compile(r'<[^>]+>')


# ------------------------- 配置与变量 -------------------------

def load_config(path):
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def _walk_json(obj, dotted):
    """按 a.b.c 路径取值；列表下标用数字，如 data.items.0.id"""
    cur = obj
    for part in dotted.split('.'):
        if cur is None:
            return None
        if isinstance(cur, list):
            if not part.isdigit() or int(part) >= len(cur):
                return None
            cur = cur[int(part)]
        elif isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return None
    return cur


def _resolve_value(value, ctx):
    """解析参数值：字符串支持 ${var} 插值；整串就是一个变量时返回原始类型"""
    if not isinstance(value, str):
        return value
    whole = _VAR_RE.fullmatch(value)
    if whole:
        return ctx.get(whole.group(1))
    return _VAR_RE.sub(lambda m: '' if ctx.get(m.group(1)) is None else str(ctx.get(m.group(1))), value)


def resolve_params(params, ctx):
    """解析整个参数字典，返回 (解析后字典, 缺失变量列表)"""
    missing = []
    out = {}
    for key, value in (params or {}).items():
        resolved = _resolve_value(value, ctx)
        if isinstance(resolved, str) and not resolved.strip():
            missing.append(key)
            continue
        if resolved is None:
            missing.append(key)
            continue
        out[key] = resolved
    return out, missing


# ------------------------- 路由覆盖 -------------------------

def _normalize_path(path):
    """归一化路由：去首尾斜杠、路径参数统一为 <>，便于与配置用例比对"""
    return '/' + _CONVERTER_RE.sub('<>', path.strip('/'))


def enumerate_api_routes():
    from django.urls import get_resolver

    def walk(patterns, prefix=''):
        for p in patterns:
            pat = str(p.pattern)
            if hasattr(p, 'url_patterns'):
                yield from walk(p.url_patterns, prefix + pat)
            else:
                yield prefix + pat

    return {_normalize_path(r) for r in walk(get_resolver().url_patterns) if r.startswith('api/')}


# ------------------------- HTTP 调用 -------------------------

class Runner:
    def __init__(self, base, app, timeout, insecure=False):
        self.base = base.rstrip('/')
        self.app = app
        self.timeout = timeout
        self.session = requests.Session()
        self.session.verify = not insecure

    def _resolve_path(self, path, params):
        """把路径占位符替换为具体值（与文档中心在线调试同口径），并从业务参数中移除该值"""
        business = dict(params or {})
        if '<uuid>' in path:
            for key in ('music_id', 'source_id'):
                if business.get(key):
                    path = path.replace('<uuid>', str(business.pop(key)))
                    break
        elif '<int>' in path:
            if business.get('link_id'):
                path = path.replace('<int>', str(business.pop('link_id')))
        return path, business

    def _auth_params(self, sign_source):
        """生成签名参数。

        sign_source 为「服务端验签时可见的业务参数」：GET/POST 含业务参数，
        PATCH/DELETE 仅签名参数（中间件对非 POST 不解析表单体，业务字段不参与验签）。
        """
        if self.app is None:
            return {}
        auth = {
            'app_id': self.app.app_id,
            'timestamp': str(int(time.time())),
            'nonce': secrets.token_hex(8),
        }
        auth['sign'] = build_sign({**sign_source, **auth}, self.app.app_secret)
        return auth

    def call(self, method, path, params, sign=True, files=None):
        method = method.upper()
        path, business = self._resolve_path(path, params)
        sign_source = business if method in ('GET', 'POST') else {}
        auth = self._auth_params(sign_source) if sign else {}
        url = self.base + path

        kwargs = {'timeout': self.timeout}
        if method == 'GET':
            kwargs['params'] = {**business, **auth}
            resp = self.session.get(url, **kwargs)
        elif method == 'POST':
            data = {**business, **auth}
            if files:
                resp = self.session.post(url, data=data, files=files, **kwargs)
            else:
                resp = self.session.post(url, data=data, **kwargs)
        else:
            # PATCH/DELETE：签名参数放 query（与中间件 request.POST 为空的口径一致），业务参数放表单体
            kwargs['params'] = auth
            resp = self.session.request(method, url, data=business, **kwargs)

        try:
            body = resp.json()
        except ValueError:
            body = None
        return resp.status_code, body


# ------------------------- 主流程 -------------------------

def resolve_app(cfg):
    """返回 (app 对象, 需清理的 UserApp 实例或 None)"""
    app_id = (cfg.get('app_id') or os.environ.get('XYAPI_APP_ID') or '').strip()
    app_secret = (cfg.get('app_secret') or os.environ.get('XYAPI_APP_SECRET') or '').strip()
    if app_id and app_secret:
        return SimpleNamespace(app_id=app_id, app_secret=app_secret), None
    name = f'SMOKE{int(time.time())}'
    app = UserApp.objects.create(name=name, token_expire_days=7, status=True)
    return app, app


def _build_files(case, ctx):
    """解析 case.files（{表单字段: 本地文件路径}），任一文件缺失则返回 (None, 原因)"""
    files_cfg = case.get('files') or {}
    if not files_cfg:
        return None, None
    out = {}
    for field, raw in files_cfg.items():
        path = _resolve_value(raw, ctx)
        if not path or not os.path.isfile(path):
            return None, f'文件不存在: {field}={path!r}（请在配置 vars 中填写真实路径）'
        out[field] = (os.path.basename(path), open(path, 'rb'))
    return out, None


def run_cases(runner, cases, ctx):
    results = []
    for idx, case in enumerate(cases, 1):
        name = case.get('name') or case.get('path')
        if case.get('disabled'):
            results.append({'name': name, 'status': 'SKIP', 'reason': '配置中已禁用'})
            print(f'  [SKIP] {name} — 配置中已禁用')
            continue

        params, missing = resolve_params(case.get('params'), ctx)
        if missing:
            reason = f'缺少参数值: {", ".join(missing)}（请在配置 vars 中填写或由前序用例 save）'
            results.append({'name': name, 'status': 'SKIP', 'reason': reason})
            print(f'  [SKIP] {name} — {reason}')
            continue

        files, file_err = _build_files(case, ctx)
        if file_err:
            results.append({'name': name, 'status': 'SKIP', 'reason': file_err})
            print(f'  [SKIP] {name} — {file_err}')
            continue
        if files:
            for fh in files.values():
                fh[1].seek(0)

        method = case.get('method', 'GET')
        path = case['path']
        expect = case.get('expect', [10000])
        if isinstance(expect, int):
            expect = [expect]

        started = time.monotonic()
        try:
            http_status, body = runner.call(method, path, params,
                                            sign=case.get('sign', True), files=files)
        except Exception as e:  # 网络层异常
            for fh in (files or {}).values():
                fh[1].close()
            results.append({'name': name, 'status': 'FAIL', 'reason': f'请求异常: {e}'})
            print(f'  [FAIL] {name} — 请求异常: {e}')
            continue
        finally:
            for fh in (files or {}).values():
                fh[1].close()
        cost_ms = int((time.monotonic() - started) * 1000)

        code = (body or {}).get('code')
        msg = (body or {}).get('msg', '')
        ok = http_status == 200 and code in expect
        status = 'PASS' if ok else 'FAIL'
        line = f'  [{status}] {name} — HTTP {http_status} code={code} cost={cost_ms}ms' + (f' msg={msg}' if msg else '')
        print(line)
        result = {'name': name, 'status': status, 'http_status': http_status, 'code': code,
                  'msg': msg, 'cost_ms': cost_ms, 'path': path, 'method': method}
        results.append(result)

        if ok and case.get('save'):
            for ctx_key, json_path in case['save'].items():
                ctx[ctx_key] = _walk_json(body, json_path)
    return results


def main():
    parser = argparse.ArgumentParser(description='全量 API 冒烟测试（真实 HTTP）')
    parser.add_argument('--config', default=DEFAULT_CONFIG, help='配置文件路径')
    parser.add_argument('--base', default=None, help='被测服务地址，如 http://127.0.0.1:8000')
    parser.add_argument('--only', default=None, help='只跑名称/路径包含该子串的用例')
    parser.add_argument('--list', action='store_true', help='仅列出用例清单后退出')
    parser.add_argument('--no-coverage', action='store_true', help='跳过路由覆盖率检查')
    parser.add_argument('--insecure', action='store_true', help='跳过 HTTPS 证书校验')
    parser.add_argument('--report', default=None, help='把结果写入指定 JSON 文件')
    args = parser.parse_args()

    if not os.path.exists(args.config):
        print(f'配置文件不存在: {args.config}')
        return 2

    cfg = load_config(args.config)
    base = args.base or cfg.get('base_url') or 'http://127.0.0.1:8000'
    cases = cfg.get('cases') or []

    if args.list:
        for i, c in enumerate(cases, 1):
            print(f'{i:>3}. {c.get("method", "GET"):<6} {c["path"]:<50} {c.get("name", "")}')
        print(f'共 {len(cases)} 条用例')
        return 0

    if args.only:
        cases = [c for c in cases if args.only in c.get('name', '') or args.only in c['path']]

    app, cleanup = resolve_app(cfg)
    print(f'被测地址: {base}')
    print(f'签名项目: {app.app_id}' + ('（临时项目，结束后删除）' if cleanup else '（来自配置/环境变量）'))
    if cleanup is not None:
        from urllib.parse import urlparse
        host = (urlparse(base).hostname or '')
        if host not in ('127.0.0.1', 'localhost', '::1'):
            print('[WARN] 未提供 app_id/app_secret，已在本机数据库创建临时项目；'
                  '若被测地址是远端环境，该凭据在远端无效，请通过配置或环境变量提供目标环境的 app_id/app_secret。')
    print(f'用例数: {len(cases)}\n')

    ctx = {'RunId': time.strftime('%Y%m%d%H%M%S')}
    ctx.update(cfg.get('vars') or {})
    runner = Runner(base, app, timeout=cfg.get('timeout', 60), insecure=args.insecure)
    try:
        print('===== 执行用例 =====')
        results = run_cases(runner, cases, ctx)
    finally:
        if cleanup is not None:
            UserApp.objects.filter(id=cleanup.id).delete()
            print('\n[清理] 已删除临时测试项目')

    passed = [r for r in results if r['status'] == 'PASS']
    failed = [r for r in results if r['status'] == 'FAIL']
    skipped = [r for r in results if r['status'] == 'SKIP']

    if not args.no_coverage:
        covered = {_normalize_path(c.get('cover') or c['path']) for c in (cfg.get('cases') or [])}
        uncovered = sorted(enumerate_api_routes() - covered)
        print('\n===== 路由覆盖 =====')
        if uncovered:
            print(f'以下 {len(uncovered)} 条路由未在用例清单中（新增服务后请补充用例）：')
            for p in uncovered:
                print(f'  - {p}')
        else:
            print('全部 /api/ 路由均已在用例清单中覆盖')

    print('\n===== 汇总 =====')
    print(f'通过: {len(passed)}  |  失败: {len(failed)}  |  跳过: {len(skipped)}  |  总计: {len(results)}')
    if failed:
        print('\n失败用例：')
        for r in failed:
            print(f'  - {r["name"]}（HTTP {r.get("http_status")} code={r.get("code")}）{r.get("msg", "")}')
    if skipped:
        print('\n跳过用例（缺参数/变量，填写 scripts/api_smoke_config.json 的 vars 后可执行）：')
        for r in skipped:
            print(f'  - {r["name"]}：{r.get("reason", "")}')

    if args.report:
        with open(args.report, 'w', encoding='utf-8') as f:
            json.dump({'base': base, 'total': len(results), 'results': results},
                      f, ensure_ascii=False, indent=2)
        print(f'\n报告已写入: {args.report}')

    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
