"""抖音评论发布爬虫

纯服务端实现（不依赖浏览器），链路：
    1) 拼参数：公共参数 + 业务参数，**全部放 query，POST 的 body 留空**
       （[实测] 参数放 body 会返回 status_code=8，未发布）
    2) a_bogus：node 补环境跑 bdms 生成（sign/sign_cli.js）
    3) 安全头：node 补环境跑抖音 securitySDK，现场产出 x-tt-session-dtrait（sign/secsdk_cli.js）
    4) 发送：requests POST → 解析 {status_code, comment}

登录态由调用方按次传入（不落盘、不共享），因此本类无状态、线程安全。

使用示例:
    pub = DouyinCommentPublisher()
    result = pub.publish_comment(cookie, '7622798120358923583', '你好')
    # -> {'cid': '7684103483653391114', 'text': '你好', 'create_time': 1789095055}

注意:
    - 抖音风控严格，需低频调用 + 失败退避，高频会导致账号被限流。
    - 只能评论「存在且公开」的视频，否则业务层返回错误。
    - 被风控拦截时抖音返回 HTTP 200 + **空响应体**（不是 403），据此判定。
"""

import json
import subprocess
from urllib.parse import urlencode

import requests

from .utils import (
    BASE_PARAMS,
    NODE_BIN,
    PUBLISH_API,
    PUBLISH_DEFAULTS,
    REQUEST_TIMEOUT,
    SECSDK_CLI,
    SECSDK_CSRF_TOKEN,
    SIGN_CLI,
    SIGN_TIMEOUT,
    UA_STRING,
)


class DouyinCommentPublisher:
    """抖音评论发布（纯服务端）"""

    def publish_comment(self, cookie, aweme_id, text):
        """发布一条一级纯文本评论

        :param cookie: 抖音登录 Cookie（完整字符串，由调用方提供）
        :param aweme_id: 目标视频 ID
        :param text: 评论内容
        :return: dict {'cid': 评论ID, 'text': 内容, 'create_time': 时间戳}
        :raises RuntimeError: 签名失败 / 被风控拦截 / 抖音返回业务错误
        """
        params = dict(BASE_PARAMS)
        params.update(PUBLISH_DEFAULTS)
        params.update({
            "aweme_id": str(aweme_id),
            "text": text,
        })

        # 参数先 URL 编码再交给签名器：服务端校验的是编码后的串
        base_url = PUBLISH_API + "?" + urlencode(params)
        signed_url = self._sign_url(base_url)

        headers = {
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Origin": "https://www.douyin.com",
            "Referer": "https://www.douyin.com/",
            "User-Agent": UA_STRING,
            "Cookie": cookie,
            "x-secsdk-csrf-token": SECSDK_CSRF_TOKEN,
            "x-tt-session-dtrait": self._get_dtrait(cookie),
        }

        try:
            resp = requests.post(signed_url, data="", headers=headers,
                                 timeout=REQUEST_TIMEOUT, allow_redirects=False)
        except requests.RequestException as e:
            raise RuntimeError(f"请求抖音接口失败: {e}")

        if not resp.content:
            raise RuntimeError("被抖音风控拦截（空响应），请降低频率或稍后重试")

        try:
            data = resp.json()
        except ValueError:
            raise RuntimeError(f"抖音返回非 JSON 响应: {resp.text[:200]}")

        if data.get("status_code") != 0:
            raise RuntimeError(f"抖音返回错误: status_code={data.get('status_code')}")

        comment = data.get("comment") or {}
        return {
            "cid": comment.get("cid"),
            "text": comment.get("text"),
            "create_time": comment.get("create_time"),
        }

    # ---------- 内部：补环境签名 ----------

    @staticmethod
    def _sign_url(url):
        """调 node 补环境跑 bdms，给 URL 补上 a_bogus

        :param url: 已 URL 编码的完整请求 URL
        :return: 签名后的 URL
        """
        try:
            proc = subprocess.run(
                [NODE_BIN, str(SIGN_CLI), "POST", url],
                capture_output=True, text=True, encoding="utf-8", timeout=SIGN_TIMEOUT,
            )
        except (OSError, subprocess.SubprocessError) as e:
            raise RuntimeError(f"a_bogus 签名失败（node 调用异常）: {e}")

        lines = (proc.stdout or "").strip().splitlines()
        if not lines:
            raise RuntimeError(f"a_bogus 签名失败: {(proc.stderr or '')[-300:]}")

        try:
            result = json.loads(lines[-1])
        except ValueError:
            raise RuntimeError("a_bogus 签名失败: 签名器输出无法解析")

        signed_url = result.get("signedUrl") or ""
        if result.get("error") or "a_bogus=" not in signed_url:
            raise RuntimeError(f"a_bogus 签名失败: {result.get('error') or '未产出 a_bogus'}")
        return signed_url

    @staticmethod
    def _get_dtrait(cookie):
        """调 node 补环境跑抖音 securitySDK，现场产出 x-tt-session-dtrait

        :param cookie: 抖音登录 Cookie（SDK 注册客户端证书时要用）
        :return: dtrait 头值
        """
        try:
            proc = subprocess.run(
                [NODE_BIN, str(SECSDK_CLI), cookie],
                capture_output=True, text=True, encoding="utf-8", timeout=SIGN_TIMEOUT,
            )
        except (OSError, subprocess.SubprocessError) as e:
            raise RuntimeError(f"安全头产出失败（node 调用异常）: {e}")

        for line in (proc.stdout or "").splitlines():
            if line.startswith("DTRAIT="):
                return line[len("DTRAIT="):].strip()
        raise RuntimeError(f"安全头产出失败: {(proc.stderr or '')[-300:]}")
