"""路线 B 验收：把 node 生成的签名 URL 真实回放，看服务端认不认这个 a_bogus

判读标准（本沙箱全程统一的唯一口径）：
    403 / 空响应 → 签名没被接受（仍在风控层）
    200 + JSON   → 签名被接受（进入业务层）

用法（在项目根目录执行）：
    node scripts/douyin_comment_publish/route_b_sign/sign_abogus.js   # 先生成 signed_url.txt
    python scripts/douyin_comment_publish/route_b_sign/verify_signed.py
"""

import sys
from pathlib import Path

import requests

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.douyin_comment_publish.spec import (  # noqa: E402
    HOME_URL, REQUEST_TIMEOUT, TTWID_URL, UA_STRING, load_cookie,
)

SIGNED_URL_FILE = Path(__file__).resolve().parent / "signed_url.txt"

# 浏览器最终出网用的是这个域（bdms 在浏览器里会把 host 改写成它）
BROWSER_HOST = "www-hj.douyin.com"


def anonymous_cookie() -> str:
    """匿名会话 Cookie（__ac_nonce + ttwid）"""
    s = requests.Session()
    s.headers.update({"User-Agent": UA_STRING})
    s.get(HOME_URL, timeout=REQUEST_TIMEOUT)
    s.post(TTWID_URL, json={
        "region": "cn", "aid": 1768, "needFid": False, "service": "www.ixigua.com",
        "migrate_info": {"ticket": "", "source": "node"},
        "cbUrlProtocol": "https", "union": True,
    }, timeout=REQUEST_TIMEOUT)
    return "; ".join(f"{k}={v}" for k, v in s.cookies.items())


def fetch(url: str, cookie: str, ua: str = UA_STRING) -> dict:
    resp = requests.get(
        url,
        headers={
            "User-Agent": ua,
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://www.douyin.com/",
            "Cookie": cookie,
        },
        timeout=REQUEST_TIMEOUT,
    )
    body = resp.text or ""
    out = {"status": resp.status_code, "len": len(body), "head": body[:200]}
    try:
        data = resp.json()
        out["status_code"] = data.get("status_code")
        out["comments"] = len(data.get("comments") or [])
    except ValueError:
        pass
    return out


def report(label: str, result: dict):
    extra = ""
    if "status_code" in result:
        extra = f" | status_code={result['status_code']} | comments={result['comments']}"
    print(f"[{label:<28}] HTTP {result['status']} | {result['len']} 字节{extra}")
    print(f"{'':<32}body: {result['head']!r}")


def main():
    if not SIGNED_URL_FILE.exists():
        print("缺少 signed_url.txt，请先执行：node scripts/douyin_comment_publish/route_b_sign/sign_abogus.js")
        return
    signed_url = SIGNED_URL_FILE.read_text(encoding="utf-8").strip()
    print(f"签名 URL（node 生成）长度 {len(signed_url)}")
    print(f"  含 a_bogus: {'a_bogus=' in signed_url}\n")

    cookie = load_cookie() or anonymous_cookie()
    print(f"登录态: {'cookie.txt' if load_cookie() else '匿名（__ac_nonce + ttwid）'}")
    print(f"UA    : {UA_STRING[:60]}...\n")

    # 对照组：同一 URL 去掉 a_bogus，观察是否仍被拦（本机已验证过是 403）
    unsigned = signed_url.split("&a_bogus=")[0]
    report("对照：去掉 a_bogus", fetch(unsigned, cookie))

    # 实验组 1：node 生成的原始 host
    report("实验：node 签名(原 host)", fetch(signed_url, cookie))

    # 实验组 2：换成浏览器实际使用的 host
    alt = signed_url.replace("//www.douyin.com/", f"//{BROWSER_HOST}/")
    if alt != signed_url:
        report(f"实验：改 host 为 {BROWSER_HOST}", fetch(alt, cookie))

    # 实验组 3：换一个 UA 回放（判断签名是否与 UA 绑定 —— 决定实现时 UA 能否自由设置）
    other_ua = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    report("实验：换其他 UA 回放", fetch(signed_url, cookie, ua=other_ua))
    report("对照：换 UA 且去签名", fetch(unsigned, cookie, ua=other_ua))

    print("\n判读：200 + JSON → 签名被接受；403/空 → 未被接受。")


if __name__ == "__main__":
    main()
