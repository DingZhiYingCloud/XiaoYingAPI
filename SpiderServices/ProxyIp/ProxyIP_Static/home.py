"""
静态代理IP服务 - StaticIPService

管理由用户手动维护的静态代理IP列表。
IP存储在 JSON 文件中，提供查询、新增、删除操作，每次操作后自动重新读取。

JSON 文件路径可通过环境变量 `PROXY_STATIC_JSON_PATH` 自定义，
默认为本模块目录下的 proxies.json。

JSON 格式:
```json
[
  {"ip": "27.43.224.67", "port": "8888", "username": "yldt18y", "password": "yldt18y"}
]
```

使用示例:
    service = StaticIPService()
    result = service.get_proxies()           # 获取全部
    service.add_proxy("1.2.3.4", "8080", "user", "pass")  # 新增
    service.delete_proxy("1.2.3.4", "8080")                # 删除
"""

import json
import os

from .utils import DEFAULT_JSON
from ..utils import get_desktop_headers, response_dict


class StaticIPService:
    """静态代理IP服务"""

    def __init__(self, json_path: str = None):
        """
        :param json_path: JSON 文件路径。为 None 时从环境变量
            PROXY_STATIC_JSON_PATH 读取，均未设置则使用默认路径。
        """
        if json_path:
            self.json_path = json_path
        else:
            self.json_path = os.getenv("PROXY_STATIC_JSON_PATH", "").strip() or DEFAULT_JSON

        self._proxies = []  # 缓存：启动时加载一次
        self._load()

    def _load(self):
        """从 JSON 文件加载代理列表到内存"""
        try:
            with open(self.json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            # 校验格式
            self._proxies = []
            for item in data:
                if isinstance(item, dict) and item.get("ip") and item.get("port"):
                    self._proxies.append({
                        "ip": str(item["ip"]).strip(),
                        "port": str(item["port"]).strip(),
                        "username": str(item.get("username", "")).strip(),
                        "password": str(item.get("password", "")).strip(),
                        "protocol": "HTTP",  # 静态IP默认 HTTP
                    })
        except (FileNotFoundError, json.JSONDecodeError) as e:
            self._proxies = []

    def reload(self):
        """重新从 JSON 文件加载（修改文件后调用）"""
        self._load()

    def _save(self):
        """将当前内存中的代理列表写回 JSON 文件"""
        with open(self.json_path, "w", encoding="utf-8") as f:
            json.dump(self._proxies, f, ensure_ascii=False, indent=2)

    def add_proxy(self, ip: str, port: str, username: str = "", password: str = ""):
        """
        新增一条静态代理。

        同时更新内存和 JSON 文件。

        :param ip: IP 地址
        :param port: 端口
        :param username: 用户名（可选）
        :param password: 密码（可选）
        :return: response_dict，code=0 成功
        """
        ip = ip.strip()
        port = port.strip()
        if not ip or not port:
            return response_dict(code=1, message="IP 和端口不能为空")

        # 检查是否已存在（ip:port 唯一）
        for p in self._proxies:
            if p["ip"] == ip and p["port"] == port:
                return response_dict(code=1, message=f"代理 {ip}:{port} 已存在")

        entry = {
            "ip": ip,
            "port": port,
            "username": username.strip(),
            "password": password.strip(),
            "protocol": "HTTP",
        }
        self._proxies.append(entry)
        self._save()
        return response_dict(code=0, message=f"新增代理 {ip}:{port} 成功")

    def delete_proxy(self, ip: str, port: str):
        """
        删除一条静态代理（按 ip:port 匹配）。

        同时更新内存和 JSON 文件。

        :param ip: IP 地址
        :param port: 端口
        :return: response_dict，code=0 成功，code=1 未找到
        """
        ip = ip.strip()
        port = port.strip()
        before = len(self._proxies)
        self._proxies = [
            p for p in self._proxies
            if not (p["ip"] == ip and p["port"] == port)
        ]
        if len(self._proxies) == before:
            return response_dict(code=1, message=f"代理 {ip}:{port} 不存在")
        self._save()
        return response_dict(code=0, message=f"删除代理 {ip}:{port} 成功")

    @property
    def count(self) -> int:
        """当前缓存的代理总数"""
        return len(self._proxies)

    def get_proxies(self, pages: int = 1, page_size: int = None) -> dict:
        """
        获取静态代理IP列表（接口签名与动态源 Crawler 保持一致）。

        :param pages: 忽略，固定返回全部（不更新无需分页）
        :param page_size: 忽略
        :return: dict 含:
            - code: 0 成功，1 失败
            - message: 描述信息
            - data: {
                proxies: [{ip, port, username, password, protocol}, ...],
                total: 总数,
                fetched: 返回数,
              }
        """
        if not self._proxies:
            return response_dict(
                code=1,
                message=f"未读取到代理数据，请检查文件: {self.json_path}",
                data={"proxies": [], "total": 0, "fetched": 0},
            )

        total = len(self._proxies)
        return response_dict(
            code=0,
            message=f"成功获取 {total} 条静态代理",
            data={
                "proxies": self._proxies,
                "total": total,
                "fetched": total,
            },
        )

    def get_all(self) -> list:
        """
        直接获取全部代理原始列表（简化调用）。

        :return: [{ip, port, username, password, protocol}, ...]
        """
        return self._proxies
