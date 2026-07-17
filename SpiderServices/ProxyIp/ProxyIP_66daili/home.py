"""
66免费代理IP爬虫 - ProxyIP66daili

爬取 https://www.66daili.com/ 的免费代理IP列表。

页面结构:
  - 代理列表: 每个代理信息在 <div.table-sj> 下的 <ul.flex> 中
  - 列顺序: IP地址 | 端口 | 地区 | 匿名 | 协议 | 响应时长 | 上次检测 | 操作
  - 分页: 通过 URL 参数 ?page={n}&size=15 切换页码
  - 总数: 页面标题中的 "代理IP总数量：N"

使用示例:
    spider = ProxyIP66daili()
    proxies = spider.get_proxies(pages=2)  # 爬取前 2 页
    # proxies = [{ip, port, protocol, region, anonymity, speed, ...}, ...]
"""

import re

import requests
from lxml import etree

from .utils import BASE_URL, PAGE_SIZE, REQUEST_TIMEOUT
from ..utils import get_desktop_headers, response_dict


class ProxyIP66daili:
    """66免费代理IP爬虫"""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(get_desktop_headers())

    def get_proxies(self, pages: int = 1, page_size: int = PAGE_SIZE) -> dict:
        """
        爬取 66免费代理IP 的列表。

        :param pages: 爬取页数，默认 1 页（15 条）
        :param page_size: 每页条数（15/30/45），默认 15
        :return: dict 含:
            - code: 0 成功，1 失败
            - message: 描述信息
            - data: {
                proxies: [{ip, port, protocol, region, anonymity, speed, check_time}, ...],
                total: 代理总数（int，从页面标题提取），
                fetched: 实际提取的代理数
              }
        """
        all_proxies = []
        total = 0

        for page in range(1, pages + 1):
            try:
                url = f"{BASE_URL}/?page={page}&size={page_size}"
                resp = self.session.get(url, timeout=REQUEST_TIMEOUT)
                resp.encoding = "utf-8"
            except requests.RequestException as e:
                return response_dict(
                    code=1,
                    message=f"第 {page} 页请求失败: {e}",
                    data={"proxies": all_proxies, "total": total, "fetched": len(all_proxies)},
                )

            tree = etree.HTML(resp.text)
            page_proxies, page_total = self._parse_page(tree)

            if page == 1:
                total = page_total
            all_proxies.extend(page_proxies)

        return response_dict(
            code=0,
            message=f"成功获取 {len(all_proxies)} 条代理",
            data={"proxies": all_proxies, "total": total, "fetched": len(all_proxies)},
        )

    def _parse_page(self, tree) -> tuple:
        """
        解析单页 HTML 中的代理列表和总数。

        :param tree: etree 解析后的 HTML 树
        :return: (proxies, total)
            proxies: [{ip, port, protocol, region, anonymity, speed, check_time}, ...]
            total: 代理总数（int）
        """
        proxies = []
        total = 0

        # 1. 提取代理总数
        total_text = self._extract_total(tree)
        if total_text:
            match = re.search(r"(\d+)", total_text)
            if match:
                total = int(match.group(1))

        # 2. 提取代理列表
        rows = tree.xpath('//div[contains(@class, "table-sj")]/ul[contains(@class, "flex")]')
        for row in rows:
            lis = row.xpath("./li")
            if len(lis) < 7:
                continue

            ip = self._get_text(lis[0])
            port = self._get_text(lis[1])
            region = self._get_text(lis[2])
            anonymity = self._get_text(lis[3])
            protocol = self._get_text(lis[4])
            speed = self._get_text(lis[5])
            check_time = self._get_text(lis[6])

            if not ip or not port:
                continue

            proxies.append({
                "ip": ip.strip(),
                "port": port.strip(),
                "protocol": protocol.strip() if protocol else "HTTP",
                "region": region.strip(),
                "anonymity": anonymity.strip(),
                "speed": speed.strip(),
                "check_time": check_time.strip(),
            })

        return proxies, total

    @staticmethod
    def _extract_total(tree) -> str:
        """从页面标题中提取代理总数文本"""
        texts = tree.xpath('//h1[contains(text(), "代理IP总数量")]/text()')
        if texts:
            return texts[0].strip()
        return ""

    @staticmethod
    def _get_text(element) -> str:
        """安全提取元素的文本内容"""
        text = element.text
        if text:
            return text.strip()
        spans = element.xpath(".//span/text()")
        if spans:
            return spans[0].strip()
        return ""
