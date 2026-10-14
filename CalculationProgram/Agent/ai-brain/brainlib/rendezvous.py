# -*- coding: utf-8 -*-
"""会合（rendezvous）：大脑换服务器 / 换域名后，子 agent 靠“种子 + 期号”算出新域名找回来。

- 派生：域名(n) = RDV_PATTERN 里的 {h} 换成 hmac_sha256(RDV_SEED, "rdv:"+n)[:10]
- 身份：brain_id = hmac_sha256(RDV_SEED, "brain-id")[:16]（写在 /health 里，子 agent 比对）

子 agent 侧是等价的 bash 实现（见 ai-agent），两边算出来必须一致，所以算法固定在这里。
"""
from __future__ import annotations

import hashlib
import hmac
import json
import urllib.error
import urllib.request

DEFAULT_PATTERN = 'xybrain-{h}.icu'      # 默认模板（用你买的 .icu 后缀）；部署时可在 brain.conf 里改


def _hmac(seed: str, msg: str, n: int) -> str:
    return hmac.new(seed.encode(), msg.encode(), hashlib.sha256).hexdigest()[:n]


def derive(seed: str, pattern: str, index: int) -> str:
    """算第 index 期的后台域名。"""
    pat = (pattern or DEFAULT_PATTERN).strip()
    return pat.replace('{h}', _hmac(seed, f'rdv:{index}', 10))


def brain_id(seed: str) -> str:
    """大脑身份标识（/health 里返回，供子 agent 校验“这是不是我们的大脑”）。"""
    return _hmac(seed, 'brain-id', 16)


def payload(conf) -> dict:
    """注册/心跳时下发给子 agent 的会合信息。"""
    try:
        index = int(str(conf.get('RDV_INDEX') or '1').strip())
    except ValueError:
        index = 1
    return {
        'rdv_seed': str(conf.get('RDV_SEED') or ''),
        'rdv_pattern': str(conf.get('RDV_PATTERN') or DEFAULT_PATTERN),
        'rdv_index': str(index),
    }


def _http_code(url: str, headers: dict, timeout: int = 6):
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception:                                # noqa: BLE001
        return None


def looks_registered(domain: str):
    """查域名“是否已被注册”，多重判定以求稳。

    返回 (已注册?, 依据字符串)：
        True  已注册   False 没注册   None 查询失败/未知
    """
    def doh_status():
        """向 Cloudflare DoH 查 NS：返回 DNS 响应 Status（0=NOERROR 存在；3=NXDOMAIN 不存在）。"""
        try:
            req = urllib.request.Request(
                f'https://cloudflare-dns.com/dns-query?name={domain}&type=NS',
                headers={'accept': 'application/dns-json'})
            with urllib.request.urlopen(req, timeout=6) as r:
                return json.loads(r.read().decode('utf-8', 'replace')).get('Status')
        except Exception:                            # noqa: BLE001
            return None

    # ① 首选 RDAP：200=已注册，404=未注册（权威）
    code = _http_code(f'https://rdap.org/domain/{domain}', {'Accept': 'application/json'})
    if code == 200:
        return True, 'rdap=200'
    if code == 404:
        if doh_status() == 0:                        # 再用 DNS 复核一下
            return True, 'dns=NOERROR'
        return False, 'rdap=404'

    # ② RDAP 没查到 → 只看 DNS 的 Status（注意：不能用 Authority 段判，NXDOMAIN 也带它）
    st = doh_status()
    if st == 0:
        return True, 'dns=NOERROR'
    if st == 3:
        return False, 'dns=NXDOMAIN'
    return None, 'unknown'
