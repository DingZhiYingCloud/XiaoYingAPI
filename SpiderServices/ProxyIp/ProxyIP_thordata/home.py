"""
Thordata 动态住宅代理爬虫 - ProxyIPThordata

Thordata（thordata.com）住宅代理是「网关型」代理：入口主机 / 端口固定，
出口 IP 由 Thordata 侧按请求轮换，因此没有可拉取的 IP 列表。本线路负责：

- 拼装可直接使用的代理地址（http://账号:密码@主机:端口）；
- 可选的可用性验证（复用 ProxyVerification：真实经代理访问测试站点，
  返回是否可用、耗时与出口 IP）——注意验证会消耗住宅代理流量。

入口主机 / 端口 / 账号 / 密码优先取调用方传入，未传则回退 .env 默认值
（PROXY_THORDATA_*，见 utils.py）。

使用示例:
    spider = ProxyIPThordata()

    # 1) 用 .env 默认网关拼装（不发起任何请求）
    result = spider.get_proxies()

    # 2) 调用方自带主机 / 账号密码
    result = spider.get_proxies(host="1rdjtq76.pr.thordata.net", port="9999",
                                username="td-customer-xxx", password="xxx")

    # 3) 顺带验证可用性（会真实经代理发一次请求）
    result = spider.get_proxies(verify=True)
"""

from urllib.parse import quote

from API.common.url_safety import check_public_http_url

from .utils import (DEFAULT_HOST, DEFAULT_PASSWORD, DEFAULT_PORT,
                    DEFAULT_USERNAME, PROTOCOL, REGION)
from ..utils import response_dict
from ..ProxyVerification.home import ProxyVerifier


class ProxyIPThordata:
    """Thordata 动态住宅代理（网关型：入口固定，出口 IP 轮换）"""

    def __init__(self):
        self.verifier = ProxyVerifier()

    @staticmethod
    def build_proxy(host: str, port: str, username: str = "", password: str = "") -> str:
        """拼装可直接用于 requests 的代理地址

        账号密码做百分号编码，避免密码中的 @ : / 等字符破坏 URL 解析；
        账号为空（白名单认证）时返回 http://主机:端口。

        :param host: 网关主机（域名或 IP）
        :param port: 网关端口
        :param username: 账号，可为空
        :param password: 密码，可为空
        :return: 代理地址，如 http://user:pass@host:9999
        """
        auth = f"{quote(username, safe='')}:{quote(password, safe='')}@" if username else ""
        return f"http://{auth}{host}:{port}"

    def get_proxies(self, pages: int = 1, page_size: int = None, **kwargs) -> dict:
        """
        获取 Thordata 住宅代理入口地址（固定 1 条）。

        :param pages: 忽略（网关型代理无分页 / 数量概念）
        :param page_size: 忽略
        :param kwargs: 可选业务参数:
            - host: str, 网关主机（默认取 .env PROXY_THORDATA_HOST）
            - port: str, 网关端口（默认取 .env PROXY_THORDATA_PORT）
            - username: str, 账号（默认取 .env；与 password 必须成对出现）
            - password: str, 密码（默认取 .env；与 username 必须成对出现）
            - verify: bool, 是否真实经代理发一次请求验证可用性（默认 False，不消耗流量）
        :return: dict 含:
            - code: 0 成功，1 失败
            - message: 描述信息
            - data: {
                proxies: [{ip, port, username, password, protocol, region, proxy}],
                total: 返回总数,
                fetched: 返回数,
              }
              verify=True 且验证通过时，proxies 每项额外含
              available=True / speed_ms / external_ip。
        """
        host = str(kwargs.get("host") or DEFAULT_HOST).strip()
        port = str(kwargs.get("port") or DEFAULT_PORT).strip()
        if not host or not port:
            return response_dict(
                code=1,
                message="Thordata 代理未配置：请在 .env 设置 PROXY_THORDATA_HOST / PROXY_THORDATA_PORT，"
                        "或由调用方传入 host / port",
                data={"proxies": [], "total": 0, "fetched": 0},
            )

        # 账号密码按「整对」处理：都没传 → 用 .env 默认整对；只传一个 → 非法
        username = str(kwargs.get("username") or "").strip()
        password = str(kwargs.get("password") or "").strip()
        if not username and not password:
            username, password = DEFAULT_USERNAME, DEFAULT_PASSWORD
        elif not (username and password):
            return response_dict(
                code=1,
                message="参数缺失: username 和 password 必须同时传入",
                data={"proxies": [], "total": 0, "fetched": 0},
            )

        proxy = self.build_proxy(host, port, username, password)
        entry = {
            "ip": host,
            "port": port,
            "username": username,
            "password": password,
            "protocol": PROTOCOL,
            "region": REGION,
            "proxy": proxy,
        }
        data = {"proxies": [entry], "total": 1, "fetched": 1}

        if not kwargs.get("verify"):
            return response_dict(
                code=0,
                message="成功获取 1 条 Thordata 动态住宅代理（未验证）",
                data=data,
            )

        # 连接前校验网关为公网地址，避免调用方把内网 / 回环地址当代理（S-09）
        ok, err = check_public_http_url(f"http://{host}:{port}")
        if not ok:
            return response_dict(code=1, message=f"参数值非法: host 不可用（{err}）", data=data)

        result = self.verifier.verify(proxy)
        if result.get("code") != 0:
            return response_dict(
                code=1,
                message=f"Thordata 代理验证失败：{result.get('message', '代理不可用')}",
                data=data,
            )

        verify_data = result.get("data") or {}
        entry["available"] = True
        entry["speed_ms"] = verify_data.get("speed_ms")
        entry["external_ip"] = verify_data.get("external_ip", "")
        return response_dict(
            code=0,
            message=f"成功获取 1 条 Thordata 动态住宅代理（已验证，出口 IP {entry['external_ip']}）",
            data=data,
        )
