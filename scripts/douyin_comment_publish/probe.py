"""抖音发布评论 - 门槛探测（沙箱工具，不发真实评论）

作用：确认 comment/publish 当前是否仍被风控层拦截，是两条签名路线的**通用验收工具**：
    - 被拦截 → HTTP 403 空响应（此时签名与登录问题无法区分）
    - 通过   → 返回业务 JSON（哪怕内容是「未登录」，也说明签名这一关过了）

用法（在项目根目录执行）：
    python scripts/douyin_comment_publish/probe.py              # 用 cookie.txt（没有则匿名）
    python scripts/douyin_comment_publish/probe.py --abogus     # 额外带本仓库旧版签名再试一次

安全说明：默认用不存在的 aweme_id（7400000000000000000），即使处于登录态也不会真的发出评论。
"""

import json
import sys
from pathlib import Path

import requests

# 允许从项目根目录复用 SpiderServices 里的旧版 abogus（仅用于对比验证）
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.douyin_comment_publish.spec import (  # noqa: E402
    HEADERS_TEMPLATE,
    HOME_URL,
    PROBE_AWEME_ID,
    PUBLISH_API,
    REQUEST_TIMEOUT,
    TTWID_URL,
    UA_STRING,
    build_params,
    load_cookie,
)


class DouyinCommentProbe:
    """comment/publish 门槛探测"""

    def __init__(self, cookie: str = "", csrf_token: str = ""):
        """
        :param cookie: 登录 Cookie；留空表示匿名（只能探测门槛，无法发布）
        :param csrf_token: X-Secsdk-Csrf-Token 请求头值，来自已登录页面
        """
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": UA_STRING})
        self._cookie = cookie
        self._csrf_token = csrf_token

    def _anonymous_cookie(self) -> str:
        """匿名会话 Cookie（__ac_nonce + ttwid）"""
        self.session.get(HOME_URL, timeout=REQUEST_TIMEOUT)
        self.session.post(
            TTWID_URL,
            json={
                "region": "cn",
                "aid": 1768,
                "needFid": False,
                "service": "www.ixigua.com",
                "migrate_info": {"ticket": "", "source": "node"},
                "cbUrlProtocol": "https",
                "union": True,
            },
            timeout=REQUEST_TIMEOUT,
        )
        return "; ".join(f"{k}={v}" for k, v in self.session.cookies.items())

    def _headers(self, aweme_id) -> dict:
        headers = HEADERS_TEMPLATE.copy()
        headers["Referer"] = f"https://www.douyin.com/video/{aweme_id}"
        headers["Cookie"] = self._cookie or self._anonymous_cookie()
        if self._csrf_token:
            headers["X-Secsdk-Csrf-Token"] = self._csrf_token
        return headers

    def probe(self, aweme_id=PROBE_AWEME_ID, text: str = "probe", abogus: bool = False) -> dict:
        """发起一次探测请求（不携带登录态时不会真的发出评论）

        :param abogus: True 时附带本仓库旧版 a_bogus，用于对比
        :return: {http_status, gated, json, body}
        """
        params = build_params(aweme_id, text)
        if abogus:
            from SpiderServices.Douyin.Video.abogus import ABogus

            params["a_bogus"] = ABogus().get_value(params, method="POST")

        resp = self.session.post(
            PUBLISH_API,
            data=params,
            headers=self._headers(aweme_id),
            timeout=REQUEST_TIMEOUT,
        )
        result = {
            "http_status": resp.status_code,
            "gated": resp.status_code != 200 or not resp.content,
            "json": None,
            "body": (resp.text or "")[:200],
        }
        try:
            result["json"] = json.loads(resp.text)
        except ValueError:
            pass
        return result


def main():
    cookie = load_cookie()
    probe = DouyinCommentProbe(cookie=cookie)
    print(f"目标接口: {PUBLISH_API}")
    print(f"登录态  : {'已加载 cookie.txt' if cookie else '匿名（未提供 cookie.txt）'}\n")

    for label, use_abogus in (("不签名", False), ("带仓库旧版 a_bogus", True)):
        r = probe.probe(abogus=use_abogus)
        print(f"[{label:<22}] HTTP {r['http_status']} | gated={r['gated']} | body={r['body']!r}")
        if r["json"]:
            print(f"{'':<26}status_code={r['json'].get('status_code')} "
                  f"msg={r['json'].get('status_msg') or r['json'].get('message')}")

    print("\n判读：gated=True → 仍在风控层，签名/登录两者缺一；")
    print("      返回业务 JSON → 签名已通过，此时业务错误才是有效信息。")


if __name__ == "__main__":
    main()
