# -*- coding: utf-8 -*-
"""给主人的通知（邮件）——走你自己的「消息推送」服务，不依赖 SMTP。

鉴权（与 API/apis/user_center/sign.py 一致）：
    app_id + timestamp + nonce + sign
    sign = HMAC-SHA256(app_secret, 把除 sign 外的参数按键名升序拼成 k=v&k=v)

配置（brain.conf）：
    PUSH_BASE         推送服务地址（默认 https://www.xiaoyingapi.com）
    PUSH_APP_ID       接入项目的 APPID
    PUSH_APP_SECRET   接入项目的 APPSECRET（签名密钥，务必保密）
    PUSH_TO           收件人邮箱，多个用逗号分隔
    PUSH_MIN_INTERVAL 同一类事件的最小发送间隔（秒），防刷邮件
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
import urllib.parse
import urllib.request

from . import conf as C

_last = {}          # key -> 上次发送时间（进程内节流，防同一事件刷屏）


def enabled(conf) -> bool:
    return bool(conf.get('PUSH_APP_ID') and conf.get('PUSH_APP_SECRET') and conf.get('PUSH_TO'))


def _sign(params: dict, secret: str) -> str:
    items = sorted((k, str(v)) for k, v in params.items() if k != 'sign' and v not in (None, ''))
    raw = '&'.join(f'{k}={v}' for k, v in items)
    return hmac.new(secret.encode('utf-8'), raw.encode('utf-8'), hashlib.sha256).hexdigest()


def send(conf, subject: str, body: str):
    """立即发一封邮件（不节流）。返回 (成功?, 说明)。"""
    if not enabled(conf):
        return False, '未配置通知（PUSH_APP_ID / PUSH_APP_SECRET / PUSH_TO）'
    form = {
        'app_id': conf['PUSH_APP_ID'],
        'timestamp': str(int(time.time())),
        'nonce': hashlib.sha256(f'{time.time()}-{subject}'.encode()).hexdigest()[:16],
        'subject': subject,
        'body': body,
        'recipients': conf['PUSH_TO'],
    }
    form['sign'] = _sign(form, conf['PUSH_APP_SECRET'])
    url = str(conf.get('PUSH_BASE') or 'https://www.xiaoyingapi.com').rstrip('/') + '/api/push/email/send'
    data = urllib.parse.urlencode(form).encode()
    # 必须带正常浏览器的 UA：Cloudflare 会 403 掉 Python 默认的 "Python-urllib/3.x"
    req = urllib.request.Request(url, data=data, headers={
        'User-Agent': ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                       '(KHTML, like Gecko) Chrome/120.0 Safari/537.36'),
        'Content-Type': 'application/x-www-form-urlencoded',
    })
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            out = resp.read().decode('utf-8', 'replace')
    except Exception as e:                           # noqa: BLE001
        C.log_line(f'notify send failed: {type(e).__name__}: {e}')
        return False, f'发送失败：{type(e).__name__}: {e}'
    try:
        j = json.loads(out)
    except ValueError:
        j = {}
    if str(j.get('code')) == '10000':
        C.log_line(f'notify ok: {subject}')
        return True, '已发送'
    C.log_line(f'notify rejected: {out[:200]}')
    return False, f'接口返回：{out[:200]}'


def notify(conf, key: str, subject: str, body: str) -> bool:
    """带节流的通知：同一个 key 在 PUSH_MIN_INTERVAL 秒内只发一次。"""
    if not enabled(conf):
        return False
    try:
        gap = int(conf.get('PUSH_MIN_INTERVAL') or 600)
    except (TypeError, ValueError):
        gap = 600
    now = time.time()
    if now - _last.get(key, 0) < gap:
        return False
    _last[key] = now
    ok, msg = send(conf, subject, body)
    if not ok:
        C.log_line(f'notify[{key}] 未发出：{msg}')
    return ok
