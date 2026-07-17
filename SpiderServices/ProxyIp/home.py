"""
代理IP服务 - ProxyIPService

统一的代理IP服务入口，聚合多个代理源并返回可用 IP 列表。

架构:
  ProxyIPService (home.py)          # 主入口，聚合+验证+返回
    ├── ProxyVerification/          # IP 可用性验证工具
    ├── ProxyIP_66daili/            # 66免费代理IP 源（动态爬虫）
    ├── ProxyIP_Static/             # 静态代理IP 源（JSON 文件）
    └── ...（后续可添加更多代理源）

核心逻辑:
  1. 调用各源爬虫获取原始代理列表
  2. 若 verify=True，对所有代理进行可用性验证
  3. 返回指定数量的可用代理

使用示例:
    service = ProxyIPService()
    # 动态代理（默认 66daili）
    result = service.get_available_proxies(count=5)
    # 静态代理
    result = service.get_available_proxies(count=3, sources=["static"])
    # 混合源
    result = service.get_available_proxies(count=5, sources=["66daili", "static"])
"""

import sys
import os
import importlib.util


# ── Python 3.14 兼容：手动加载子包 ──
# Python 3.14 的 PathFinder 无法通过 sys.path 定位带 __init__.py 的子包，
# 因此使用 spec_from_file_location 预先注册所有子包。
def _ensure_subpackage(parent_name, child_path):
    """如果子包尚未注册，使用 spec_from_file_location 加载并注册到 sys.modules"""
    if parent_name in sys.modules:
        return
    spec = importlib.util.spec_from_file_location(parent_name, child_path)
    if spec:
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        sys.modules[parent_name] = mod


_PKG_DIR = os.path.dirname(os.path.abspath(__file__))
for _sub in ["ProxyIP_66daili", "ProxyVerification", "ProxyIP_Static"]:
    _ensure_subpackage(
        f"ProxyIP.{_sub}",
        os.path.join(_PKG_DIR, _sub, "__init__.py"),
    )


from .utils import response_dict
from .ProxyVerification.home import ProxyVerifier
from .ProxyIP_66daili.home import ProxyIP66daili
from .ProxyIP_Static.home import StaticIPService


class ProxyIPService:
    """代理IP服务 - 主入口"""

    SOURCE_MAP = {
        "66daili": ProxyIP66daili,
        "static": StaticIPService,
    }
    """代理源映射表：source_name -> CrawlerClass
    后续新增代理源时只需在此注册即可。"""

    def __init__(self):
        self.verifier = ProxyVerifier()
        self._crawlers = {}

    def _get_crawler(self, source: str):
        """延迟加载指定源的爬虫实例"""
        if source not in self._crawlers:
            cls = self.SOURCE_MAP.get(source)
            if not cls:
                raise ValueError(f"不支持的代理源: {source}，可选: {list(self.SOURCE_MAP.keys())}")
            self._crawlers[source] = cls()
        return self._crawlers[source]

    def get_available_proxies(self, count: int = 10, sources: list = None, verify: bool = True) -> dict:
        """
        获取指定数量的（可用）代理IP。

        流程:
          1. 调用各源爬虫获取原始代理列表
          2. 若 verify=True，对所有代理进行可用性验证
          3. 返回 count 个代理（验证模式按速度排序返回最快的）

        :param count: 需要返回的代理数量（默认 10）
        :param sources: 代理源名称列表（默认 ["66daili"]），后续可扩展
        :param verify: 是否验证代理可用性（默认 True）。
            True 返回已验证可用的代理（格式：{proxy, speed_ms, external_ip}）；
            False 返回原始代理。
              动态源格式：{ip, port, protocol, region, anonymity}；
              静态源格式：{ip, port, username, password, protocol}。
        :return: dict 含:
            - code: 0 成功，1 失败
            - message: 描述信息
            - data: {
                proxies: [{...}, ...],
                total_fetched: 原始爬取总数,
                total_available: 验证通过数（verify=False 时为 total_fetched），
                requested: 请求数量,
              }
        """
        if sources is None:
            sources = ["66daili"]
        if count < 1:
            return response_dict(code=1, message="count 必须 >= 1", data={
                "proxies": [], "total_fetched": 0, "total_available": 0, "requested": count,
            })

        # 1. 聚合所有源代理
        raw_proxies = []     # 字符串列表（用于验证 / 最终返回）
        raw_proxy_infos = [] # 原始详情列表 [{ip, port, protocol, ...}]
        for source in sources:
            try:
                crawler = self._get_crawler(source)
                result = crawler.get_proxies(pages=1)
                if result["code"] == 0:
                    proxies = result["data"]["proxies"]
                    for p in proxies:
                        # 静态IP 有用户名密码 → 构造 auth 代理地址
                        if p.get("username") and p.get("password"):
                            raw_proxies.append(
                                f"http://{p['username']}:{p['password']}@{p['ip']}:{p['port']}"
                            )
                        else:
                            raw_proxies.append(f"{p['ip']}:{p['port']}")
                    raw_proxy_infos.extend(proxies)
            except Exception:
                continue

        if not raw_proxies:
            return response_dict(
                code=1,
                message="未能从任何源获取到代理",
                data={"proxies": [], "total_fetched": 0, "total_available": 0, "requested": count},
            )

        total_fetched = len(raw_proxies)

        # 2. 根据 verify 参数决定是否验证
        if verify:
            available = self.verifier.batch_verify(raw_proxies)
            available.sort(key=lambda x: x.get("speed_ms", 9999))
            result_proxies = available[:count]
            total_available = len(available)
        else:
            result_proxies = raw_proxy_infos[:count]
            total_available = total_fetched

        return response_dict(
            code=0,
            message=f"获取到 {len(result_proxies)} 个代理" + ("（已验证）" if verify else "（未验证）"),
            data={
                "proxies": result_proxies,
                "total_fetched": total_fetched,
                "total_available": total_available,
                "requested": count,
            },
        )


if __name__ == "__main__":
    service = ProxyIPService()

    print("===== 模式1: 默认 66daili（verify=True）=====")
    result = service.get_available_proxies(count=3, verify=True)
    print(f"状态: {'成功' if result['code'] == 0 else '失败'}")
    print(f"原始爬取: {result['data']['total_fetched']}")
    print(f"验证通过: {result['data']['total_available']}")
    print(f"返回数量: {len(result['data']['proxies'])}")
    for p in result["data"]["proxies"]:
        print(f"  {p['proxy']} - {p['speed_ms']}ms | 出口IP: {p.get('external_ip', '?')}")

    print()

    print("===== 模式2: 静态IP static（verify=False）=====")
    result = service.get_available_proxies(count=3, sources=["static"], verify=False)
    print(f"状态: {'成功' if result['code'] == 0 else '失败'}")
    print(f"原始爬取: {result['data']['total_fetched']}")
    print(f"返回数量: {len(result['data']['proxies'])}")
    for p in result["data"]["proxies"]:
        auth = f" | 账号: {p.get('username', '')}" if p.get('username') else ""
        print(f"  {p['ip']}:{p['port']}{auth}")

    print()

    print("===== 模式3: 静态IP static（verify=True，带auth验证）=====")
    result = service.get_available_proxies(count=3, sources=["static"], verify=True)
    print(f"状态: {'成功' if result['code'] == 0 else '失败'}")
    print(f"原始爬取: {result['data']['total_fetched']}")
    print(f"验证通过: {result['data']['total_available']}")
    print(f"返回数量: {len(result['data']['proxies'])}")
    for p in result["data"]["proxies"]:
        print(f"  {p['proxy']} - {p['speed_ms']}ms")
