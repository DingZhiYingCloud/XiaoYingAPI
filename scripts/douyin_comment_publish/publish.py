"""抖音发布评论 - 端到端发布（路线 B：node 补环境签名 + requests 发送）

流程：拼参数 → 交给 node sign_cli.js 签名（bdms 自动追加 a_bogus）→ requests 发出 → 解析响应。

安全设计（避免误发公开评论）：
    - 默认**干跑**：目标视频用不存在的 PROBE_AWEME_ID，即使参数全对也不会产生任何评论；
    - 只有显式加 --confirm 且传入真实 --aweme-id 时才会真正发布。

【实测结论 2026-09-11】参数必须放 **query**、POST 的 body 留空（本脚本默认行为）；
    --in-body 已实测失败（同一会话下返回 status_code=8，未发布）。
    本脚本走「纯服务端」路线，三件套齐备即可发布成功（[实测] status_code=0，无浏览器参与）：
        1) a_bogus     —— sign_cli.js 跑 bdms 生成
        2) msToken     —— 读 ms_token.txt
        3) 运行时安全头 —— node 补环境跑抖音 securitySDK **现场产出** x-tt-session-dtrait
                          （见 route_b_sign/secsdk_cli.js）；失败时回退 sec_headers.json

用法（在项目根目录执行）：
    python scripts/douyin_comment_publish/publish.py                          # 干跑（不存在的视频）
    python scripts/douyin_comment_publish/publish.py --in-body                # 干跑：参数放 body 的形态（已实测失败）
    python scripts/douyin_comment_publish/publish.py --aweme-id 123 --text "内容" --confirm   # 真发

登录态：读同目录 cookie.txt（缺失则匿名，必然失败）；脚本只打印 Cookie 键名，不打印值。
"""

import argparse
import base64
import json
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import quote, urlencode

import requests

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.douyin_comment_publish.spec import (  # noqa: E402
    PROBE_AWEME_ID,
    PUBLISH_API,
    REQUEST_TIMEOUT,
    UA_STRING,
    build_params,
    load_cookie,
)

SIGN_CLI = Path(__file__).resolve().parent / "route_b_sign" / "sign_cli.js"
MS_TOKEN_FILE = Path(__file__).resolve().parent / "ms_token.txt"
SEC_HEADERS_FILE = Path(__file__).resolve().parent / "sec_headers.json"
SECSDK_CLI = Path(__file__).resolve().parent / "route_b_sign" / "secsdk_cli.js"


def read_ms_token() -> str:
    """读 ms_token.txt（浏览器 localStorage 里的 msToken，node 侧的 bdms 不产出它）

    缺失时发布大概率 403 —— 这是纯服务端发布当前的关键缺口。
    """
    if not MS_TOKEN_FILE.exists():
        return ""
    return MS_TOKEN_FILE.read_text(encoding="utf-8").strip()


def gen_sec_headers_by_node() -> dict:
    """用 node 补环境跑抖音 securitySDK，**现场产出** x-tt-session-dtrait（不需要浏览器）

    [实测 2026-09-11] 消融实验结论：comment/publish 真正必需的只有两个头 ——
        x-tt-session-dtrait（内容严格校验） + x-secsdk-csrf-token（常量 "DOWNGRADE"）；
        bd-ticket-guard-* 整套（含 client-data / req_sign）都可以不带。
    失败时返回空 dict，由调用方退回 sec_headers.json。
    """
    try:
        proc = subprocess.run(
            ["node", str(SECSDK_CLI)], capture_output=True, text=True,
            encoding="utf-8", timeout=180, cwd=str(_PROJECT_ROOT),
        )
    except (OSError, subprocess.SubprocessError):
        return {}
    for line in (proc.stdout or "").splitlines():
        if line.startswith("DTRAIT="):
            return {
                "x-secsdk-csrf-token": "DOWNGRADE",
                "x-tt-session-dtrait": line[len("DTRAIT="):].strip(),
            }
    return {}


def load_sec_headers() -> dict:
    """读 sec_headers.json（浏览器侧 securitySDK 产出的静态安全头）

    这套头（bd-ticket-guard-* / x-tt-session-dtrait）是纯服务端发布的**最后一道门槛**：
    缺了它，请求在风控层就被 403 空响应拦掉。[实测 2026-09-11] 借来浏览器抓到的值后，
    纯 HTTP(requests) 侧同一路径即返回业务 JSON（风控放行）。

    bd-ticket-guard-client-data 是 base64(JSON)，其中 ts_sign/req_sign 是签好的常量
    （req_sign 只对 ticket 签名，与 path、时间无关），而 timestamp **不参与签名** ——
    所以每次发送把 timestamp 换成当前秒即可，无需重新签名。
    """
    if not SEC_HEADERS_FILE.exists():
        return {}
    cfg = json.loads(SEC_HEADERS_FILE.read_text(encoding="utf-8"))
    out = {k: v for k, v in cfg.items() if not k.startswith("_")}
    client_data = out.get("bd-ticket-guard-client-data")
    if client_data:
        obj = json.loads(base64.b64decode(client_data))
        obj["timestamp"] = int(time.time())
        out["bd-ticket-guard-client-data"] = base64.b64encode(
            json.dumps(obj, separators=(",", ":")).encode()
        ).decode()
    return out


def parse_cookie(cookie: str) -> dict:
    """Cookie 字符串 → dict（只用于取 s_v_web_id 等派生值，不打印）"""
    out = {}
    for item in (cookie or "").split(";"):
        if "=" in item:
            k, v = item.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def sign(method: str, url: str, body: str = None) -> dict:
    """调用 node 签名器，返回 {signedUrl, signedBody, urlChanged, bodyChanged, error}"""
    proc = subprocess.run(
        ["node", str(SIGN_CLI), method, url, body or ""],
        capture_output=True, text=True, encoding="utf-8", timeout=60,
        cwd=str(_PROJECT_ROOT),
    )
    stdout = (proc.stdout or "").strip().splitlines()
    if not stdout:
        raise RuntimeError(f"签名器无输出；stderr={proc.stderr[-400:]}")
    result = json.loads(stdout[-1])
    result["stderr"] = proc.stderr
    return result


def build_headers(cookie: str, aweme_id: str, referer_kind: str) -> dict:
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Origin": "https://www.douyin.com",
        "User-Agent": UA_STRING,
        "Cookie": cookie,
    }
    headers["Referer"] = (
        f"https://www.douyin.com/video/{aweme_id}" if referer_kind == "video"
        else "https://www.douyin.com/"
    )
    return headers


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--aweme-id", default=PROBE_AWEME_ID, help="目标视频 ID（默认：不存在的探针 ID）")
    ap.add_argument("--text", default="干跑测试（不会真的发出）", help="评论内容")
    ap.add_argument("--reply-id", default="0", help="回复目标评论 ID，一级评论为 0")
    ap.add_argument("--in-body", action="store_true", help="把参数放 body（默认放 query）")
    ap.add_argument("--referer", choices=["video", "home"], default="video")
    ap.add_argument("--confirm", action="store_true", help="对真实视频真正发布（危险，需显式指定）")
    ap.add_argument("--ms-token", default="", help="msToken（默认读同目录 ms_token.txt）")
    args = ap.parse_args()

    real_target = args.aweme_id != PROBE_AWEME_ID
    if real_target and not args.confirm:
        print(f"拒绝执行：--aweme-id {args.aweme_id} 是真实视频，必须加 --confirm 才允许发布。")
        return 1

    cookie = load_cookie()
    if not cookie:
        print("缺少 cookie.txt（匿名声明的发布必然失败），请先放置登录 Cookie。")
        return 1

    cookie_map = parse_cookie(cookie)
    print(f"登录态: 已加载 {len(cookie_map)} 个 Cookie 键 | "
          f"sessionid: {'有' if 'sessionid' in cookie_map else '无'} | "
          f"s_v_web_id: {'有' if 's_v_web_id' in cookie_map else '无'}")
    print(f"模式  : {'【真实发布】' if real_target else '干跑（不存在的视频，不会产生评论）'}")
    print(f"目标  : aweme_id={args.aweme_id} | text={args.text!r} | reply_id={args.reply_id}")

    params = build_params(args.aweme_id, args.text, reply_id=args.reply_id)

    # msToken：node 侧 bdms 不产出它，必须从浏览器取；缺失时发布大概率 403
    ms_token = args.ms_token or read_ms_token()
    if ms_token:
        params["msToken"] = ms_token

    if args.in_body:
        url_params, body_params = {}, params
    else:
        url_params, body_params = params, {}

    # 关键：参数必须**先 URL 编码再签名**。服务端校验时看到的是编码后的串，
    # 若拿未编码的中文去签名，签名必然对不上（这是之前 403 的原因之一）。
    base_url = PUBLISH_API + ("?" + urlencode(url_params) if url_params else "")
    body = urlencode(body_params)

    verify_fp = cookie_map.get("s_v_web_id", "")
    print(f"\n[1/3] 签名（node bdms）… 参数 {'放 body' if args.in_body else '放 query'}")
    print(f"      msToken: {'有（%d 字符）' % len(ms_token) if ms_token else '无（发布很可能被 403）'}")
    signed = sign("POST", base_url, body or None)
    if signed.get("error"):
        print(f"      签名器报错: {signed['error']}")
    print(f"      url 被改写: {signed['urlChanged']} | body 被改写: {signed['bodyChanged']}")
    print(f"      签名后 URL 长度: {len(signed['signedUrl'])} | 含 a_bogus: {'a_bogus=' in signed['signedUrl']}")
    if "a_bogus=" in signed["signedUrl"]:
        frag = signed["signedUrl"].split("a_bogus=")[1][:60]
        print(f"      a_bogus 片段: {frag}…")

    signed_body = signed["signedBody"] or ""

    # verifyFp / fp：浏览器把它们追加在 a_bogus **之后**（不参与签名），这里照同样顺序拼
    final_url = signed["signedUrl"]
    if verify_fp:
        final_url += f"&verifyFp={quote(verify_fp)}&fp={quote(verify_fp)}"

    print("\n[2/3] 发送请求…")
    headers = build_headers(cookie, args.aweme_id, args.referer)
    sec_headers = gen_sec_headers_by_node()
    src = "node 补环境现场产出"
    if not sec_headers:
        sec_headers = load_sec_headers()
        src = "借用 sec_headers.json（补环境未产出时的回退）"
    headers.update(sec_headers)
    print(f"      安全头: {'已附上 %d 个（%s）' % (len(sec_headers), src) if sec_headers else '缺失（发布必被 403）'}")
    resp = requests.post(
        final_url,
        data=signed_body,
        headers=headers,
        timeout=REQUEST_TIMEOUT,
        allow_redirects=False,
    )

    print(f"\n[3/3] 响应: HTTP {resp.status_code} | {len(resp.content)} 字节")
    body_text = resp.text or ""
    if not body_text:
        print("      空响应 → 仍在风控层（签名或登录态未通过）")
        return 2
    print(f"      原始前 400 字: {body_text[:400]!r}")
    try:
        data = resp.json()
        print("\n----- 解析 -----")
        print(f"status_code: {data.get('status_code')}")
        print(f"status_msg : {data.get('status_msg') or data.get('message')}")
        comment = data.get("comment")
        if comment:
            print(f"comment_id  : {comment.get('cid')}")
            print(f"内容        : {comment.get('text')}")
            print(f"作者        : {(comment.get('user') or {}).get('nickname')}")
        return 0
    except ValueError:
        print("      非 JSON 响应")
        return 3


if __name__ == "__main__":
    sys.exit(main())
