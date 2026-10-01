"""
红果短剧 爬虫 - HongguoDramaSpider

站点为服务端渲染（SSR）的短剧 H5 站点，无对外 API，数据以 JSON 内嵌在 HTML 中
（详见 utils.py 顶部的实测结论）。需模拟浏览器 TLS 指纹（curl_cffi）访问。

提供能力:
    get_rank()       榜单（热播榜 / 真人剧榜 / AI剧榜 / 漫剧榜，分页）
    get_categories() 分类树（一级 -> 二级题材）
    get_list()       分类列表（分页；一级取全部，二级取该题材）
    get_search()     关键词搜索（站点不支持分页，仅返回单页）
    get_detail()     详情（全量集号 vid_list + 可播集数）
    get_play()       播放直链（仅前 3 集可播，超过则返回 need_app 占位）

注意：这里的「可播」只代表**源站 H5 直链**。对外接口在第 4 集及以后还有两条出路
（已登记外链 / 本站网页直出），由服务层 `API/apis/dramas/hongguo/utils.py` 补齐 ——
改本层时务必同步那里的 `get_detail()` / `get_play()`，别让「详情说不能播、播放说能播」重演。

使用示例:
    spider = HongguoDramaSpider()
    spider.get_rank("hot-drama")
    spider.get_categories()
    spider.get_list("real-drama", page=2)
    spider.get_list("real-drama/romance")        # 二级题材：爱情
    spider.get_search("保姆")
    spider.get_detail("7686894628578020414")
    spider.get_play("7686894628578020414", 2)

约定：各方法返回可 JSON 序列化的 dict/list；网络/解析等异常向上抛出，由上层捕获。
"""

import re
import time

from curl_cffi import requests as creq
from lxml import etree

from . import utils as U
from .cache import DATA_TTL, MEDIA_TTL, get_or_fetch


class HongguoDramaSpider:
    """红果短剧 线路爬虫"""

    def __init__(self):
        # impersonate="chrome" 模拟 Chrome 的 TLS 指纹
        self.session = creq.Session(impersonate="chrome")
        self.session.headers.update({
            "User-Agent": U.UA_STRING,
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Referer": f"{U.BASE_URL}/",
        })

    # ==================== 基础请求 ====================

    def _get_html(self, url: str, missing_ok: bool = False):
        """
        带重试的 GET 请求，返回 HTML 文本。

        站点偶发在响应中插入 NUL 字节（\\x00，实测位于个别剧名字符间），
        libxml2 会把 NUL 当作缓冲区结束符从而截断整个文档解析，故统一清除。

        :param missing_ok: 为 True 时把 404 视为「不存在」并返回 None（如无效 series_id），
                           其余非 200 仍按失败处理。
        """
        last_err = None
        for _ in range(U.MAX_RETRIES):
            try:
                resp = self.session.get(url, timeout=U.REQUEST_TIMEOUT)
                if resp.status_code == 200:
                    return resp.text.replace("\x00", "")
                if missing_ok and resp.status_code == 404:
                    return None
                last_err = RuntimeError(f"HTTP {resp.status_code}")
            except Exception as e:          # noqa: BLE001 - 网络类异常统一重试
                last_err = e
            time.sleep(U.RETRY_DELAY)
        raise RuntimeError(f"请求失败（已重试 {U.MAX_RETRIES} 次）: {url} -> {last_err}")

    # ==================== 解析工具 ====================

    @staticmethod
    def _normalize(text: str) -> str:
        """压缩空白并去首尾空白"""
        return re.sub(r"\s+", " ", text or "").strip()

    @classmethod
    def _parse_rank_item(cls, li, index: int) -> dict:
        """
        解析榜单条目（ol.pc-list 下的 li）。

        :param li: 榜单 li 元素
        :param index: 该 li 在列表中的下标（0 基），用于排名兜底
        :return: {rank, series_id, name, cover, url, heat, score, favorite, like, tags, intro}
        """
        links = li.xpath(U.XP_RANK_LINK)
        href = links[0].get("href", "") if links else ""
        m = U.RE_SERIES_ID.search(href)
        series_id = m.group(1) if m else None

        covers = li.xpath(U.XP_RANK_COVER)
        # 排名优先取页面渲染的序号（第 2 页起为 21/22…），缺失时按列表下标兜底
        numbers = li.xpath('.//span[contains(@class,"pc-badge-number")]//text()')
        rank = int(numbers[0]) if numbers and str(numbers[0]).strip().isdigit() else index + 1

        heat = cls._normalize("".join(li.xpath(U.XP_RANK_HEAT)))
        score = favorite = like = None
        for node in li.xpath(U.XP_RANK_ENGAGEMENT):
            text = cls._normalize("".join(node.itertext()))
            if "评分" in text:
                score = text.replace("评分", "").strip()
            elif "收藏" in text:
                favorite = text.replace("收藏", "").strip()
            elif "点赞" in text:
                like = text.replace("点赞", "").strip()

        tags = [t.strip() for t in li.xpath(U.XP_RANK_TAG) if t.strip()]
        return {
            "rank": rank,
            "series_id": series_id,
            "name": cls._normalize("".join(li.xpath(U.XP_RANK_TITLE))),
            "cover": covers[0] if covers else "",
            "url": U.build_detail_url(series_id) if series_id else "",
            "heat": heat or None,
            "score": score,
            "favorite": favorite,
            "like": like,
            "tags": tags,
            "intro": cls._normalize("".join(li.xpath(U.XP_RANK_INTRO))),
        }

    @classmethod
    def _parse_json_list_item(cls, obj: dict) -> dict:
        """
        把 SSR JSON 里的剧集对象（recommendList / searchList 的 video_data）归一化为列表项。

        列表项字段与榜单条目保持一致；榜单专有的排名/热度/评分/收藏/点赞在列表页无对应数据，
        统一置空（None）。
        """
        series_id = obj.get("series_id")
        return {
            "rank": None,
            "series_id": str(series_id) if series_id else None,
            "name": obj.get("series_name") or obj.get("series_title") or "",
            "cover": obj.get("series_cover") or "",
            "url": U.build_detail_url(series_id) if series_id else "",
            "heat": None,
            "score": None,
            "favorite": None,
            "like": None,
            "tags": obj.get("tags") or [],
            "intro": obj.get("series_intro") or "",
        }

    # ==================== 公开能力 ====================

    def get_rank(self, rank_type: str = "hot-drama", page: int = 1) -> dict:
        """
        获取榜单。

        :param rank_type: 榜单类型，取值见 utils.RANK_TYPES（热播榜 / 真人剧榜 / AI剧榜 / 漫剧榜）
        :param page: 页码，从 1 开始（站点每页 20 条）
        :return: {type, page, total_page, results: [列表项]}
        """
        rank_type = rank_type or "hot-drama"
        # 缓存键带版本号：此前 XP_RANK_LIST 会连页面头部的面包屑一起选中，缓存里存的是
        # 「前 2 条字段全空的脏数据 + 20 条真实榜单」。解析已修，但旧缓存默认留 24 小时
        # （HONGGUO_DATA_CACHE_TTL），沿用旧键会继续下发脏数据 —— 换键即让旧缓存失效。
        key = f"rank:v2:{rank_type}:{page}"

        def fetch():
            html = self._get_html(U.build_rank_url(rank_type, page=page))
            tree = etree.HTML(html)
            lis = tree.xpath(U.XP_RANK_LIST)
            return {
                "type": rank_type,
                "page": page,
                "total_page": U.max_page(html),
                "results": [self._parse_rank_item(li, i) for i, li in enumerate(lis)],
            }

        return get_or_fetch(key, fetch, DATA_TTL)

    def get_categories(self) -> dict:
        """
        获取分类树（一级 -> 二级，由站点各级 /category/* 页面实际枚举所得）。

        站点是两级分类：一级是内容形态（真人剧 / 漫剧 / AI剧 / 漫画），二级是题材
        （爱情 / 年代 / 逆袭 …）。每个节点的 slug 都能直接传给 get_list ——
        一级取该一级全部，二级只取该题材。

        :return: {categories: [{slug, name, url, children: [{slug, name, url}]}]}
                 无二级的一级（如漫画）children 为空列表。
        """
        def fetch():
            return {
                "categories": [
                    {
                        "slug": slug,
                        "name": node["name"],
                        "url": U.build_category_url(slug),
                        "children": [
                            {
                                "slug": f"{slug}/{child}",
                                "name": child_name,
                                "url": U.build_category_url(f"{slug}/{child}"),
                            }
                            for child, child_name in node["children"].items()
                        ],
                    }
                    for slug, node in U.CATEGORIES.items()
                ],
            }

        # 缓存键带版本号：返回体由「扁平 4 项」改为「两级嵌套」是**破坏性变更**，
        # 而文件缓存默认保留 24 小时（HONGGUO_DATA_CACHE_TTL）—— 沿用旧键会在部署后
        # 继续下发旧结构。换键让旧缓存自然失效（老键随 TTL 过期，不必手工清缓存目录）。
        return get_or_fetch("categories:v2", fetch, DATA_TTL)

    def get_list(self, category: str, page: int = 1) -> dict:
        """
        获取分类列表（分页）。

        :param category: 分类取值（取值见 get_categories）：一级如 real-drama，
                         二级用「一级/二级」如 real-drama/romance
        :param page: 页码，从 1 开始
        :return: {category, page, results: [列表项], pagination: {current, total}}
        """
        key = f"list:{category}:{page}"

        def fetch():
            html = self._get_html(U.build_category_url(category, page=page))
            objs = U.extract_json_array(html, U.SSR_KEY_RECOMMEND_LIST) or []
            return {
                "category": category,
                "page": page,
                "results": [self._parse_json_list_item(o) for o in objs],
                "pagination": {"current": page, "total": U.max_page(html) or page},
            }

        return get_or_fetch(key, fetch, DATA_TTL)

    def get_search(self, keyword: str, page: int = 1) -> dict:
        """
        关键词搜索。

        实测站点搜索页不支持分页（?page=N 与第 1 页结果完全相同），故只返回单页，
        pagination.total 固定为 1。

        :param keyword: 搜索关键词
        :param page: 页码（站点无分页，仅回填入参）
        :return: {keyword, page, results: [列表项], pagination: {current, total}}
        """
        keyword = (keyword or "").strip()
        key = f"search:{keyword}:{page}"

        def fetch():
            html = self._get_html(U.build_search_url(keyword, page=page))
            items = U.extract_json_array(html, U.SSR_KEY_SEARCH_LIST) or []
            results = []
            for item in items:
                data = item.get("video_data") or {}
                if data.get("series_id"):
                    results.append(self._parse_json_list_item(data))
            return {
                "keyword": keyword,
                "page": page,
                "results": results,
                "pagination": {"current": page, "total": 1},
            }

        return get_or_fetch(key, fetch, DATA_TTL)

    def get_detail(self, series_id) -> dict:
        """
        获取剧集详情（全量集号 + 可播集数）。

        总集数取自 vid_list 长度；可播集数取页面的 accessible_episode_cnt，
        缺失时回退 PLAYABLE_LIMIT_FALLBACK（实测该站仅前 3 集可播）。

        :param series_id: 剧集 id（详情页链接中的 series_id）
        :return: {series_id, name, cover, intro, tags, episode_cnt, playable_cnt,
                  episodes: [{ep, episode_id, playable}]}；剧集不存在时返回 None
        """
        series_id = str(series_id)
        key = f"detail:{series_id}"

        def fetch():
            html = self._get_html(U.build_detail_url(series_id), missing_ok=True)
            if not html:
                return None
            obj = U.find_series_object(html, series_id)
            if not obj:
                return None
            vids = U.extract_vid_list(obj)
            episode_cnt = len(vids)
            limit = int(obj.get("accessible_episode_cnt") or U.PLAYABLE_LIMIT_FALLBACK)
            return {
                "series_id": series_id,
                "name": obj.get("series_name") or "",
                "cover": obj.get("series_cover") or "",
                "intro": obj.get("series_intro") or "",
                "tags": obj.get("tags") or [],
                "episode_cnt": episode_cnt,
                "playable_cnt": min(limit, episode_cnt),
                "episodes": [
                    {"ep": i + 1, "episode_id": vid, "playable": (i + 1) <= limit}
                    for i, vid in enumerate(vids)
                ],
            }

        return get_or_fetch(key, fetch, DATA_TTL)

    def get_play(self, series_id, ep) -> dict:
        """
        获取某集播放直链。

        站点仅前若干集（accessible_episode_cnt，实测为 3）可播，超过则返回 need_app 占位，
        不抛异常；ep 超出总集数时返回 None。可播结果按媒体类 TTL 缓存，
        need_app 占位结果不缓存。

        :param series_id: 剧集 id
        :param ep: 集数（从 1 开始）
        :return: 可播 -> {series_id, ep, episode_id, playable: True, url, duration, width,
                          height, poster}
                 不可播 -> {series_id, ep, playable: False, reason: "need_app"}
                 越界   -> None
        """
        series_id = str(series_id)
        ep = int(ep)

        detail = self.get_detail(series_id)
        if not detail:
            return None
        if ep < 1 or ep > detail["episode_cnt"]:
            return None
        if ep > detail["playable_cnt"]:
            return {"series_id": series_id, "ep": ep, "playable": False, "reason": "need_app"}

        episode_id = detail["episodes"][ep - 1]["episode_id"]
        key = f"play:{series_id}:{ep}"

        def fetch():
            html = self._get_html(U.build_player_url(series_id, episode_id))
            info = U.extract_json_object(html, U.SSR_KEY_PLAYER_INFO) or {}
            return {
                "series_id": series_id,
                "ep": ep,
                "episode_id": episode_id,
                "playable": True,
                "url": info.get("main_url") or "",
                "duration": info.get("duration"),
                "width": info.get("width"),
                "height": info.get("height"),
                "poster": info.get("poster_url") or "",
            }

        # 播放直链带签名时效，使用较短的媒体缓存 TTL
        return get_or_fetch(key, fetch, MEDIA_TTL)
