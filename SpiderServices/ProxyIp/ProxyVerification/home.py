"""
代理IP验证工具 - ProxyVerification

用于验证代理IP是否可用。通过代理发送 HTTP 请求到测试 URL，
如果能成功获取响应则认为代理可用。

使用示例:
    verifier = ProxyVerifier()
    # 验证单个代理
    result = verifier.verify("http://121.204.140.3:8081")
    # 批量验证
    results = verifier.batch_verify(["http://8.138.149.37:9080", "https://8.213.197.208:1081"])
"""

import requests

from .utils import VERIFY_URL_HTTP, VERIFY_URL_HTTPS, VERIFY_TIMEOUT
from ..utils import get_desktop_headers, response_dict


class ProxyVerifier:
    """代理IP可用性验证器"""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(get_desktop_headers())

    def verify(self, proxy: str) -> dict:
        """
        验证单个代理IP是否可用。

        :param proxy: 代理地址，格式如 "http://ip:port" 或 "socks5://ip:port"
            如果未指定协议前缀，默认视为 HTTP 代理。
        :return: dict 含:
            - code: 0=可用，1=不可用
            - message: 描述信息
            - data: {
                proxy: 原始代理地址,
                speed_ms: 响应耗时（毫秒），
                external_ip: 代理出口 IP（可能为空）
              }
        """
        proxy = proxy.strip()
        # 未指定协议时默认添加 http://
        if not proxy.startswith(("http://", "https://", "socks4://", "socks5://")):
            proxy = f"http://{proxy}"

        proxies = {"http": proxy, "https": proxy}

        # 优先用 HTTPS 测试，HTTP 降级
        test_urls = [VERIFY_URL_HTTPS, VERIFY_URL_HTTP]

        for url in test_urls:
            try:
                resp = self.session.get(
                    url,
                    proxies=proxies,
                    timeout=VERIFY_TIMEOUT,
                )
                if resp.ok:
                    speed_ms = round(resp.elapsed.total_seconds() * 1000)
                    try:
                        external_ip = resp.json().get("origin", "")
                    except Exception:
                        external_ip = resp.text.strip()[:50]
                    return response_dict(
                        code=0,
                        message="代理可用",
                        data={
                            "proxy": proxy,
                            "speed_ms": speed_ms,
                            "external_ip": external_ip,
                        },
                    )
            except requests.RequestException:
                continue  # 尝试下一个测试 URL

        return response_dict(
            code=1,
            message="代理不可用（连接超时或拒绝）",
            data={"proxy": proxy, "speed_ms": None, "external_ip": ""},
        )

    def batch_verify(self, proxies: list, max_workers: int = 10) -> list:
        """
        批量验证代理IP（顺序执行，无需额外依赖）。

        :param proxies: 代理地址列表
        :param max_workers: 最大并发数（当前为顺序执行，保留参数便于后续扩展）
        :return: 可用代理列表，每项为 verify() 的 data 字段
        """
        available = []
        for p in proxies:
            result = self.verify(p)
            if result["code"] == 0:
                available.append(result["data"])
        return available
