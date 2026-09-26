"""
555电影 爬虫 - Movie555Spider

站点为苹果CMS10（MacCMS）模板的影视站，服务端渲染，需模拟浏览器 TLS 指纹
（curl_cffi）才能访问（纯 requests/httpx 会在 TLS 握手阶段被拒）。

提供能力（对应电影站完整流程）:
    get_categories()  分类列表（主分类 + 子分类）
    get_filters()     某分类可用的筛选条件（子分类 / 地区 / 题材 / 语言 / 年份 / 排序）
    get_home()        首页聚合（轮播 + 各推荐区块）
    get_list()        分类列表（分页 + 排序 + 年份 / 地区 / 题材 / 语言 组合筛选）
    get_detail()      详情（简介 / 导演演员 / 播放源 / 选集）
    get_play()        播放地址（m3u8）
    search()          关键词搜索

使用示例:
    spider = Movie555Spider()
    spider.get_home()
    spider.get_filters(1)                                        # 电影可选哪些筛选值
    spider.get_list(1, page=1, area="大陆", lang="国语", year=2025, order="score")
    spider.get_detail("812640")
    spider.get_play("812640", 3, 1)
    spider.search("交锋")
"""

import json
import re
import time

from curl_cffi import requests as creq
from lxml import etree

from . import utils as U
from .cache import DATA_TTL, MEDIA_TTL, get_or_fetch


class Movie555Spider:
    """555电影 线路爬虫"""

    def __init__(self):
        # impersonate="chrome" 模拟 Chrome 的 TLS 指纹，绕过站点的指纹防护
        self.session = creq.Session(impersonate="chrome")
        self.session.headers.update({
            "User-Agent": U.UA_STRING,
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Referer": f"{U.BASE_URL}/",
        })

    # ==================== 基础请求 ====================

    def _get_html(self, url: str) -> str:
        """
        带重试的 GET 请求，返回 HTML 文本。

        站点为多 IP 轮询，偶发连接中断，故做重试。
        """
        last_err = None
        for _ in range(U.MAX_RETRIES):
            try:
                resp = self.session.get(url, timeout=U.REQUEST_TIMEOUT)
                if resp.status_code == 200:
                    return resp.text
                last_err = RuntimeError(f"HTTP {resp.status_code}")
            except Exception as e:          # noqa: BLE001 - 网络类异常统一重试
                last_err = e
            time.sleep(U.RETRY_DELAY)
        raise RuntimeError(f"请求失败（已重试 {U.MAX_RETRIES} 次）: {url} -> {last_err}")

    # ==================== 解析工具 ====================

    @staticmethod
    def _full_url(path: str) -> str:
        """补全相对地址为完整 URL"""
        if not path:
            return ""
        if path.startswith("http"):
            return path
        return U.BASE_URL + path

    @staticmethod
    def _vod_id(href: str):
        """从详情页链接中提取影片 id"""
        m = re.search(r"/voddetail/(\d+)\.html", href or "")
        return m.group(1) if m else None

    @staticmethod
    def _parse_play_link(href: str):
        """从播放页链接中提取 (sid, nid)"""
        m = re.search(r"/vodplay/\d+-(\d+)-(\d+)\.html", href or "")
        return (m.group(1), m.group(2)) if m else (None, None)

    def _parse_poster(self, node) -> dict:
        """
        解析列表条目（a.module-poster-item）。

        :param node: 列表项 a 元素
        :return: {id, name, url, cover, note, douban}
        """
        href = node.get("href", "")
        pics = node.xpath('.//img/@data-original') or node.xpath('.//img/@src')
        return {
            "id": self._vod_id(href),
            "name": (node.get("title") or "").strip() or "".join(
                node.xpath('.//div[contains(@class,"module-poster-item-title")]//text()')).strip(),
            "url": self._full_url(href),
            "cover": self._full_url(pics[0] if pics else ""),
            "note": "".join(node.xpath('.//div[contains(@class,"module-item-note")]/text()')).strip(),
            "douban": "".join(node.xpath('.//div[contains(@class,"module-item-douban")]/text()')).strip(),
        }

    @staticmethod
    def _parse_total_page(tree):
        """
        解析列表页总页数。

        分页链接形如 /vodshow/1--------44---.html，从「尾页」或最大页码取总分页数。
        当前页由调用方传入，无需从 HTML 推断。
        """
        total = None
        for a in tree.xpath(U.XP_PAGE_LINK):
            href = a.get("href", "")
            txt = "".join(a.itertext()).strip()
            m = re.search(r"-(\d+)---\.html", href)
            if m and ("尾页" in txt or "page-next" in a.get("class", "")):
                total = max(total or 0, int(m.group(1)))
            elif txt.isdigit():
                total = max(total or 0, int(txt))
        return total

    def _parse_list_page(self, tree) -> dict:
        """解析列表页：条目 + 总页数"""
        items = [self._parse_poster(a) for a in tree.xpath(U.XP_LIST_ITEM)]
        return {"items": items, "total_page": self._parse_total_page(tree)}

    @staticmethod
    def _parse_filters(tree, type_id: int) -> dict:
        """
        解析分类页的筛选条件（子分类 + 地区 / 题材 / 语言 / 年份 / 排序）。

        站点把筛选选项渲染成指向 /vodshow/… 的链接：在「未加任何筛选」的分类页上，
        每个选项相对基础 URL 只差 12 段中的一段，所以按「差异段」即可归类 ——
        不依赖站点的分组文案，站点换皮也不需要跟着改选择器。
        分页链接（page-link）、跨分类链接（差异段不止一处）会自动跳过。
        """
        base_parts = U.split_list_url(U.build_list_url(type_id))
        sub_types = []
        options = {key: [] for _, key, _ in U.FILTER_GROUPS}
        seen = set()

        for a in tree.xpath(U.XP_FILTER_LINK):
            if "page-link" in (a.get("class") or ""):        # 分页器不是筛选条件
                continue
            parts = U.split_list_url(a.get("href", ""))
            if not parts:
                continue
            diff = [i for i in range(U.URL_FIELD_COUNT) if parts[i] != base_parts[i]]
            if len(diff) != 1:
                continue
            key = U.FIELD_KEYS.get(diff[0] + 1)
            name = re.sub(r"\s+", " ", "".join(a.itertext())).strip()
            if not key or not name:
                continue
            value = U.decode_value(parts[diff[0]])
            if (key, value) in seen:
                continue
            seen.add((key, value))
            (sub_types if key == "type" else options[key]).append({"name": name, "value": value})

        return {
            "type_id": type_id,
            "sub_types": sub_types,
            "groups": [
                {"key": key, "name": U.FIELD_LABELS[key], "options": options[key]}
                for _, key, _ in U.FILTER_GROUPS if key != "type" and options[key]
            ],
        }

    @staticmethod
    def _extract_player(html: str) -> dict:
        """
        从播放页 HTML 中提取内嵌的 player_aaaa 播放配置（含 m3u8 地址）。

        该 JSON 后紧跟 </script>（无分号），故以 </script> 作为结束边界，
        避免非贪婪匹配越界到后续脚本。
        """
        m = re.search(r"player_aaaa\s*=\s*(\{.*?\})\s*</script>", html, re.S)
        if not m:
            raise RuntimeError("播放页未找到播放配置（player_aaaa）")
        return json.loads(m.group(1))

    # ==================== 公开能力 ====================

    def get_categories(self) -> dict:
        """
        获取分类列表（主分类 + 子分类）。

        :return: {
            main: [{id, name}],      # 主分类（电影 / 连续剧 / 综艺纪录 / 动漫 / 福利 / 擦边短剧）
            sub:  [{id, name}],      # 连续剧的子分类，取值同样可直接传给列表接口的 type_id
            labels: [{key, name}],   # 首页 label 专题页
        }
        """
        def fetch():
            return {
                "main": [{"id": k, "name": v} for k, v in U.MAIN_CATEGORIES.items()],
                "sub": [{"id": k, "name": v} for k, v in U.SUB_CATEGORIES.items()],
                "labels": [{"key": k, "name": v} for k, v in U.LABELS.items()],
            }

        return get_or_fetch("categories", fetch, DATA_TTL)

    def get_filters(self, type_id: int) -> dict:
        """
        获取某分类可用的筛选条件（该分类独有的取值集合，随年份推移自动更新）。

        :param type_id: 分类 id
        :return: {
            type_id,
            sub_types: [{name, value}],                        # 子分类，value 回传给 type_id
            groups: [{key, name, options: [{name, value}]}],   # 其余筛选组，value 回传给同名参数
        }
        """
        key = f"filters:{type_id}"

        def fetch():
            tree = etree.HTML(self._get_html(U.build_list_url(type_id)))
            return self._parse_filters(tree, type_id)

        return get_or_fetch(key, fetch, DATA_TTL)

    def get_home(self) -> dict:
        """
        获取首页聚合数据。

        :return: {
            carousel: [{id, name, url, cover, note, intro}],   # 轮播
            blocks: [{title, items: [{id, name, url, cover, note, douban}]}],  # 各推荐区块
        }
        """
        def fetch():
            html = self._get_html(f"{U.BASE_URL}/index/home.html")
            tree = etree.HTML(html)

            # 轮播：.swiper-big 内的 slide
            carousel = []
            for slide in tree.xpath('//div[contains(@class,"swiper-big")]//div[contains(@class,"swiper-slide")]'):
                a = slide.xpath('.//a[contains(@class,"banner")]')
                if not a:
                    continue
                href = a[0].get("href", "")
                bg = a[0].get("data-bg", "")
                carousel.append({
                    "id": self._vod_id(href),
                    "name": "".join(slide.xpath('.//div[contains(@class,"v-title")]//text()')).strip(),
                    "url": self._full_url(href),
                    "cover": bg,
                    "note": "".join(slide.xpath('.//div[contains(@class,"v-ins")]/p[1]//text()')).strip(),
                    "intro": "".join(slide.xpath('.//div[contains(@class,"v-ins")]/p[2]//text()')).strip(),
                })

            # 各推荐区块：标题在 .module-heading，条目在其兄弟容器内
            blocks = []
            for hd in tree.xpath('//div[contains(@class,"module-heading")]'):
                title = "".join(hd.xpath('.//*[contains(@class,"module-title")]//text()')).strip()
                if not title or "资讯" in title:      # 排除影视资讯
                    continue
                nodes = hd.xpath('following-sibling::*[1]//a[contains(@class,"module-poster-item")]')
                if not nodes:
                    continue
                blocks.append({
                    "title": title,
                    "items": [self._parse_poster(a) for a in nodes],
                })

            return {"carousel": carousel, "blocks": blocks}

        return get_or_fetch("home", fetch, DATA_TTL)

    def get_list(self, type_id: int, page: int = 1, order: str = None, year=None,
                 area: str = None, genre: str = None, lang: str = None) -> dict:
        """
        获取分类列表（分页 + 组合筛选）。

        :param type_id: 分类 id（1=电影 2=连续剧 3=综艺纪录 4=动漫 124=福利 126=擦边短剧，
                        或 13/125 这类子分类 id）
        :param page: 页码，从 1 开始
        :param order: 排序方式，可选 time(时间) / hits(人气) / score(评分)
        :param year: 年份，如 2026
        :param area: 地区，如 大陆（取值见 get_filters）
        :param genre: 题材，如 动作（取值见 get_filters）
        :param lang: 语言，如 国语（取值见 get_filters）
        :return: {type_id, page, items: [...], pagination: {current, total}}
        """
        key = f"list:{type_id}:{page}:{order}:{year}:{area}:{genre}:{lang}"

        def fetch():
            url = U.build_list_url(type_id, page=page, order=order, year=year,
                                   area=area, genre=genre, lang=lang)
            data = self._parse_list_page(etree.HTML(self._get_html(url)))
            return {
                "type_id": type_id,
                "page": page,
                "items": data["items"],
                "pagination": {"current": page, "total": data["total_page"]},
            }

        return get_or_fetch(key, fetch, DATA_TTL)

    def get_detail(self, vod_id) -> dict:
        """
        获取影片详情（含播放源与选集）。

        :param vod_id: 影片 id（详情页链接中的数字）
        :return: {
            id, name, cover, intro,
            info: {导演, 编剧, 主演, 上映, 更新, 集数, ...},
            sources: [{sid, name, episodes: [{nid, name, url}]}],
        }
        """
        vod_id = str(vod_id)
        key = f"detail:{vod_id}"

        def fetch():
            html = self._get_html(U.build_detail_url(vod_id))
            tree = etree.HTML(html)

            name = "".join(tree.xpath(U.XP_DETAIL_TITLE)).strip()
            intro = "".join(tree.xpath(U.XP_DETAIL_INTRO)).strip()
            cover_nodes = tree.xpath('//div[contains(@class,"module-info-poster")]//img/@data-original') \
                or tree.xpath('//div[contains(@class,"module-info-pic")]//img/@data-original')

            # 元数据行：每行形如 "导演：xxx"（跳过简介块）
            info = {}
            for node in tree.xpath(U.XP_DETAIL_INFO_ITEM):
                if "module-info-introduction" in (node.get("class") or ""):
                    continue
                text = re.sub(r"\s+", " ", "".join(node.itertext())).strip().replace("\xa0", " ")
                if "：" in text:
                    k, v = text.split("：", 1)
                    info[k.strip()] = v.strip()

            # 播放源名称（tab 的 data-dropdown-value）
            tab_names = []
            for t in tree.xpath('//div[contains(@class,"module-tab-items-box")]'
                                '//div[contains(@class,"module-tab-item")]'):
                nm = t.get("data-dropdown-value") or "".join(t.itertext()).strip()
                tab_names.append(nm)

            # 选集：每个播放源一个容器（桌面/移动各一份，按首集链接去重）
            sources = []
            seen = set()
            for content in tree.xpath(U.XP_PLAY_SOURCES):
                links = content.xpath(U.XP_PLAY_LINK)
                if not links:
                    continue
                first_href = links[0].get("href", "")
                if first_href in seen:
                    continue
                seen.add(first_href)
                sid, _ = self._parse_play_link(first_href)
                episodes = []
                for a in links:
                    s, n = self._parse_play_link(a.get("href", ""))
                    episodes.append({
                        "nid": n,
                        "name": "".join(a.itertext()).strip(),
                        "url": self._full_url(a.get("href", "")),
                    })
                sources.append({"sid": sid, "name": "", "episodes": episodes})

            # 按顺序把播放源名称填入（tab 与选集容器顺序一致）
            for i, src in enumerate(sources):
                if i < len(tab_names):
                    src["name"] = tab_names[i]

            return {
                "id": vod_id,
                "name": name,
                "cover": self._full_url(cover_nodes[0] if cover_nodes else ""),
                "intro": intro,
                "info": info,
                "sources": sources,
            }

        return get_or_fetch(key, fetch, DATA_TTL)

    def get_play(self, vod_id, sid, nid) -> dict:
        """
        获取某集/某播放源的 m3u8 播放地址。

        :param vod_id: 影片 id
        :param sid: 播放源序号（来自 get_detail 的 sources[].sid）
        :param nid: 集数序号（来自 episodes[].nid）
        :return: {id, sid, nid, name, episode, m3u8, from, encrypt}
        """
        vod_id = str(vod_id)
        key = f"play:{vod_id}:{sid}:{nid}"

        def fetch():
            html = self._get_html(U.build_play_url(vod_id, sid, nid))
            cfg = self._extract_player(html)
            vod_data = cfg.get("vod_data") or {}
            return {
                "id": vod_id,
                "sid": sid,
                "nid": nid,
                "name": vod_data.get("vod_name", ""),
                "episode": cfg.get("note", ""),
                "m3u8": cfg.get("url", ""),
                "from": cfg.get("from", ""),
                "encrypt": cfg.get("encrypt", 0),
            }

        # 播放地址带时效，使用较短的媒体缓存 TTL
        return get_or_fetch(key, fetch, MEDIA_TTL)

    def search(self, keyword: str) -> dict:
        """
        搜索影片。

        :param keyword: 搜索关键词
        :return: {keyword, results: [{id, name, url, cover, note, category}]}
        """
        keyword = (keyword or "").strip()
        key = f"search:{keyword}"

        def fetch():
            tree = etree.HTML(self._get_html(U.build_search_url(keyword)))
            results = []
            for card in tree.xpath(U.XP_SEARCH_ITEM):
                a = card.xpath(U.XP_SEARCH_LINK)
                if not a:
                    continue
                category = "".join(card.xpath(U.XP_SEARCH_CLASS + '/text()')).strip()
                href = a[0].get("href", "")
                pics = card.xpath('.//img/@data-original') or card.xpath('.//img/@src')
                results.append({
                    "id": self._vod_id(href),
                    "name": "".join(
                        card.xpath('.//div[contains(@class,"module-card-item-title")]//a[1]//text()')).strip(),
                    "url": self._full_url(href),
                    "cover": self._full_url(pics[0] if pics else ""),
                    "note": "".join(card.xpath('.//div[contains(@class,"module-item-note")]/text()')).strip(),
                    "category": category,
                })
            return {"keyword": keyword, "results": results}

        return get_or_fetch(key, fetch, DATA_TTL)
