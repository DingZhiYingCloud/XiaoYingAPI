import requests
from lxml import etree


class SpiderVerification:
    """
    搜索引擎蜘蛛IP验证服务（https://4759.cn/tool/spider/）。

    通过调用 4759.cn 的蜘蛛验证接口，判断指定 IP 是否属于
    百度、谷歌、必应、360、搜狗、头条、神马、雅虎等搜索引擎爬虫。

    工作原理:
        - 接口地址: GET https://4759.cn/tool/spider/?ip={ip}
        - 页面返回一个包含验证结果的表格
        - 系统通过反向 DNS 解析 + 官方域名白名单匹配来判断
    """

    # 验证接口地址
    VERIFY_URL = "https://4759.cn/tool/spider/"

    def __init__(self):
        """初始化验证会话。"""
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9",
        })

    def verify(self, ip):
        """
        验证指定 IP 是否属于搜索引擎爬虫。

        :param ip: 要验证的 IP 地址（支持 IPv4 和 IPv6）
        :return: dict 含:
            - ip: 被验证的 IP 地址
            - is_spider: True/False，是否为蜘蛛
            - spider_type: 蜘蛛类型名称（如 "谷歌蜘蛛"、"百度蜘蛛"），非蜘蛛时为 "非蜘蛛"
            - ptr_domain: 反向解析域名（PTR 记录），若无法解析则直接返回 IP 本身
            - matched_domain: 匹配的官方域名后缀，未匹配时为 "未匹配"
            - verify_method: 验证方式（通常为 "反向DNS验证"）
            - result: 最终结果描述（"查询成功" 等）
        :raises ValueError: IP 格式无效时抛出
        :raises RuntimeError: 请求失败或解析异常时抛出
        """
        if not ip or not isinstance(ip, str):
            raise ValueError("IP 地址不能为空")

        try:
            resp = self.session.get(
                self.VERIFY_URL,
                params={"ip": ip.strip()},
                timeout=15,
            )
            resp.raise_for_status()
        except requests.RequestException as e:
            raise RuntimeError(f"验证请求失败: {e}")

        return self._parse_result(resp.text)

    def _parse_result(self, html_text):
        """
        从返回的 HTML 页面中解析验证结果。

        HTML 结构: div.result-area > table.result-table > tr > td
        <table class="result-table">
            <tr> <th>验证IP</th> <th>蜘蛛类型</th> <th>反向解析域名</th> ... </tr>
            <tr>
                <td>{ip}</td>
                <td class="text-success">{spider_type}</td>
                <td class="text-success">{ptr_domain}</td>
                <td class="text-success">{matched_domain}</td>
                <td>{verify_method}</td>
                <td>{result}</td>
            </tr>
        </table>

        :param html_text: 页面 HTML 文本
        :return: dict 同 verify() 方法返回结构
        """
        tree = etree.HTML(html_text)

        # 定位结果表格
        table = tree.xpath('//div[contains(@class,"result-area")]//table[contains(@class,"result-table")]')
        if not table:
            # 可能是页面加载失败或页面结构变了
            # 检查页面是否包含"请输入IP"之类的提示
            body = "".join(tree.xpath('//body//text()')).strip()
            if "验证IP" not in body:
                raise RuntimeError(f"无法解析验证结果，页面内容异常: {body[:200]}")
            # 页面无结果表格说明是首次访问（未输入IP），此时直接返回空值
            return {
                "ip": None,
                "is_spider": False,
                "spider_type": None,
                "ptr_domain": None,
                "matched_domain": None,
                "verify_method": None,
                "result": None,
            }

        # 提取数据行（第2个 tr 是数据，第1个是表头）
        data_row = table[0].xpath(".//tr[2]")
        if not data_row:
            raise RuntimeError("无法定位验证结果数据行")

        cells = data_row[0].xpath(".//td")
        if len(cells) < 6:
            raise RuntimeError(f"结果表格格式异常，单元格数={len(cells)}")

        ip = cells[0].text.strip() if cells[0].text else ""
        spider_type = "".join(cells[1].itertext()).strip()
        ptr_domain = "".join(cells[2].itertext()).strip()
        matched_domain = "".join(cells[3].itertext()).strip()
        verify_method = "".join(cells[4].itertext()).strip()
        result = "".join(cells[5].itertext()).strip()

        # 判断是否为蜘蛛：
        # 1. spider_type 不等于 "非蜘蛛"
        # 2. spider_type 所在 td 的 class 包含 "text-success"（有 spider class）
        # 两者取其一，但用 "非蜘蛛" 文本更直观可靠
        is_spider = (spider_type != "非蜘蛛")

        return {
            "ip": ip,
            "is_spider": is_spider,
            "spider_type": spider_type,
            "ptr_domain": ptr_domain,
            "matched_domain": matched_domain,
            "verify_method": verify_method,
            "result": result,
        }


# ---------- 使用示例 ----------
if __name__ == "__main__":
    v = SpiderVerification()

    # 已知的蜘蛛 IP（从页面近期查询记录获取）
    test_ips = {
        "66.249.72.39": "谷歌蜘蛛",
        "116.179.32.28": "百度蜘蛛",
        "207.46.13.155": "必应蜘蛛",
        "180.153.236.206": "360蜘蛛",
        "202.165.111.0": "雅虎蜘蛛",
        # 非蜘蛛 IP
        "143.92.32.92": "非蜘蛛",
        "120.48.32.130": "非蜘蛛",
    }

    print(f"{'IP':<20} {'期望':<10} {'结果':<10} {'蜘蛛类型':<10} {'反向解析域名':<40} {'匹配域名':<20}")
    print("-" * 120)

    for ip, expected in test_ips.items():
        result = v.verify(ip)
        status = "✓" if result["is_spider"] == (expected != "非蜘蛛") else "✗"
        spider_label = result["spider_type"] or "—"
        ptr = result["ptr_domain"] or "—"
        matched = result["matched_domain"] or "—"
        print(f"{ip:<20} {expected:<10} {status:<10} {spider_label:<10} {ptr:<40} {matched:<20}")
