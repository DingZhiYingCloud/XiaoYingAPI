"""抖音签名 JS 抓取（路线 B 第一步）

从抖音页面里定位并下载当前版本的签名脚本，供 route_b_sign/ 的 node 补环境尝试使用。

来源证据（[实测] 2026-09-10 浏览器里读到的 <script src>）：
    https://p-pc-weboff.byteimg.com/tos-cn-i-9r5gewecjs/bdms_1.0.1.19_fix.js
    https://lf-c-flwb.bytetos.com/obj/rc-client-security/c-webmssdk/1.0.0.20/webmssdk.es5.js
    https://lf-c-flwb.bytetos.com/obj/rc-client-security/web/glue/1.0.0.64-fix.01/sdk-glue.js

用法（在项目根目录执行）：
    python scripts/douyin_comment_publish/fetch_js.py

产物落在同目录 js/ 下（随代码入库；抖音改版后重跑本脚本即可更新这几个签名脚本）。
"""

import json
import sys
from pathlib import Path

import requests

# 允许以 `python scripts/douyin_comment_publish/fetch_js.py` 直接运行（脚本目录不在项目根时需手动补 sys.path）
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.douyin_comment_publish.spec import HOME_URL, REQUEST_TIMEOUT, UA_STRING  # noqa: E402

# 已知的签名脚本地址（[实测] 见文件头；[实测 2026-09-11] 后两条由浏览器子任务定位）
JS_SOURCES = {
    "bdms_1.0.1.19_fix.js": "https://p-pc-weboff.byteimg.com/tos-cn-i-9r5gewecjs/bdms_1.0.1.19_fix.js",
    "webmssdk.es5.js": "https://lf-c-flwb.bytetos.com/obj/rc-client-security/c-webmssdk/1.0.0.20/webmssdk.es5.js",
    "sdk-glue.js": "https://lf-c-flwb.bytetos.com/obj/rc-client-security/web/glue/1.0.0.64-fix.01/sdk-glue.js",
    # securitySDK（bd-ticket-guard 那套头由它产出；comment/publish 被其 consumerPathList 点名）
    "runtime_bundler_34.js": "https://lf-security.bytegoofy.com/obj/security-secsdk/runtime_bundler_34.js",
    # x-tt-session-dtrait 由它写入请求头（浏览器子任务实测的调用栈指向它）
    "uc-secure-dtrait-core.js": (
        "https://lf-douyin-pc-web.douyinstatic.com/obj/passport-fe/ucenter_fe/"
        "@byted/uc-secure-dtrait-core/1.0.0.16/dist/index.umd.production.js"
    ),
}

OUT_DIR = Path(__file__).resolve().parent / "js"


def discover_from_homepage() -> list:
    """顺带从首页 HTML 里扫描签名相关 script 地址（地址会随版本变化，用于核对）"""
    try:
        html = requests.get(
            HOME_URL, headers={"User-Agent": UA_STRING}, timeout=REQUEST_TIMEOUT
        ).text
    except requests.RequestException as e:
        print(f"# 首页抓取失败（不影响下载已知地址）: {e}")
        return []
    found = []
    for chunk in html.split("<script"):
        if "src=" not in chunk:
            continue
        src = chunk.split("src=", 1)[1].split('"')[1] if '"' in chunk.split("src=", 1)[1] else ""
        if any(k in src for k in ("webmssdk", "bdms", "sdk-glue")):
            found.append(src)
    return found


def download(name: str, url: str) -> dict:
    resp = requests.get(url, headers={"User-Agent": UA_STRING}, timeout=REQUEST_TIMEOUT)
    path = OUT_DIR / name
    path.write_bytes(resp.content)
    return {"name": name, "url": url, "status": resp.status_code, "bytes": len(resp.content)}


def main():
    OUT_DIR.mkdir(exist_ok=True)

    print("== 首页扫描到的签名脚本地址 ==")
    for src in discover_from_homepage():
        print("  ", src)

    print("\n== 下载 ==")
    results = [download(name, url) for name, url in JS_SOURCES.items()]
    for r in results:
        print(f"   {r['name']:<24} HTTP {r['status']} {r['bytes']:>9} 字节 -> js/{r['name']}")

    (OUT_DIR / "_sources.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\n产物目录: {OUT_DIR}")


if __name__ == "__main__":
    main()
