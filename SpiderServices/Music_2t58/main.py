import requests
import json
import re
import hashlib
import sys
import os
import importlib.util
from urllib.parse import quote
from lxml import etree
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad


# ── 静态代理加载（动态，每次调用重新读取 JSON） ──
def _get_static_proxy():
    """
    从 ProxyIP_Static 获取一个可用静态代理。

    使用 importlib.util 加载 ProxyIP 包（兼容 Python 3.14 的 PathFinder 问题），
    每次调用重新读取 JSON 文件，确保与 API 端增删操作实时同步。

    :return: {"http": proxy_url, "https": proxy_url} 或 None（无代理时直连）
    """
    try:
        _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # SpiderServices
        _init = os.path.join(_root, "ProxyIP", "__init__.py")
        if not os.path.exists(_init):
            return None

        spec = importlib.util.spec_from_file_location("ProxyIP", _init)
        if not spec:
            return None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        sys.modules["ProxyIP"] = mod

        from ProxyIP.ProxyIP_Static.home import StaticIPService
        static = StaticIPService()
        if static.count == 0:
            return None

        p = static.get_all()[0]
        if p.get("username") and p.get("password"):
            proxy_url = f"http://{p['username']}:{p['password']}@{p['ip']}:{p['port']}"
        else:
            proxy_url = f"http://{p['ip']}:{p['port']}"
        return {"http": proxy_url, "https": proxy_url}
    except Exception:
        return None


class Music2t58Spider:
    """
    爱听音乐网(2t58.com)数据爬虫。

    代理策略:
        每次 HTTP 请求前从 ProxyIP_Static 动态获取最新静态代理，
        确保与 API 端增删操作实时同步；无可用代理时直连。

    支持自定义代理或强制直连:
        spider = Music2t58Spider()              # 自动：有静态IP就用，没有就直连
        spider = Music2t58Spider(proxy=False)   # 强制直连
        spider = Music2t58Spider(proxy={"http": "http://127.0.0.1:8080", "https": "..."})
    """

    # ---------- 基础配置 ----------
    BASE_URL = "https://www.2t58.com"
    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Referer": "https://www.2t58.com/",
    }
    # 请求超时时间（秒）
    TIMEOUT = 15

    # ---------- 歌曲详情页相关配置 ----------
    # 播放链接/歌词接口
    PLAY_API = "https://www.2t58.com/js/play.php"
    LRC_API = "https://js.eev3.com/lrc.php"
    # AES 解密密钥（提取自 playen.js 的 decodeUrl 函数，经 SHA256 后用于 AES-ECB）
    # 说明: 网站通过 CryptoJS.SHA256(该明文) 生成 32 字节密钥，再用 AES-ECB/Pkcs7 解密 Hex 密文
    DECRYPT_KEY = "SklaBTy1aTSEEtMjAyNg"

    def __init__(self, proxy: dict = None):
        """
        :param proxy: 代理策略。
            None（默认）：自动，每次请求动态获取静态代理，无则直连；
            False：强制直连，不走任何代理；
            dict：自定义固定代理，如 {"http": "...", "https": "..."}。
        """
        self.session = requests.Session()
        self.session.headers.update(self.HEADERS)

        if proxy is None:
            self._proxy_mode = "auto"       # 每次请求动态决定
        elif proxy is False:
            self._proxy_mode = "direct"     # 强制直连
        else:
            self._proxy_mode = "custom"     # 自定义固定代理
            self.session.proxies = proxy

    def _refresh_proxy(self):
        """
        刷新 session 的代理配置。
        auto 模式：从 ProxyIP_Static 动态获取，无则移除代理用直连。
        direct/custom 模式：不操作。
        """
        if self._proxy_mode == "auto":
            proxy = _get_static_proxy()
            if proxy:
                self.session.proxies = proxy
            else:
                self.session.proxies = {}    # 移除代理，直连
        # direct 和 custom 模式不做任何操作

    # ---------- 内部方法 ----------

    def _pass_verification(self, html_text, verify_url):
        """
        通过网站的人机验证。
        首次访问会返回包含 csrf_token 的验证页，需要 POST 表单提交后才能拿到真实内容。

        :param html_text: 验证页 HTML 文本
        :param verify_url: 触发验证的原始 URL，表单提交至此地址
        :return: 通过验证后的页面 HTML 文本；验证页不匹配时返回 None
        """
        tree = etree.HTML(html_text)
        csrf_nodes = tree.xpath('//input[@name="csrf_token"]')
        if not csrf_nodes:
            return None

        csrf_token = csrf_nodes[0].get("value", "")
        # 提交验证表单（勾选"我不是人机"），session 会自动保存验证 Cookie
        self.session.post(
            verify_url,
            data={"csrf_token": csrf_token, "human_check": "on"},
            timeout=self.TIMEOUT,
        )
        # 带 Cookie 重新请求原页面，拿到真实内容
        resp = self.session.get(verify_url, timeout=self.TIMEOUT)
        return resp.text

    def _get_html(self, url):
        """
        获取指定 URL 的 HTML 文本，自动处理人机验证。

        :param url: 目标 URL
        :return: 页面 HTML 文本
        :raises requests.RequestException: 请求失败时抛出
        """
        self._refresh_proxy()
        resp = self.session.get(url, timeout=self.TIMEOUT)
        html_text = resp.text
        # 检测是否命中人机验证页
        if "安全人机验证" in html_text or 'name="csrf_token"' in html_text:
            verified = self._pass_verification(html_text, url)
            if verified:
                html_text = verified
        return html_text

    def _get_home_html(self):
        """
        获取首页 HTML 文本。

        :return: 首页 HTML 文本
        """
        return self._get_html(self.BASE_URL + "/")

    @staticmethod
    def _parse_song_title(title):
        """
        解析歌曲标题，拆分歌手列表与歌曲名。
        标题格式: "歌手1&歌手2&歌手3 - 歌曲名"
        示例: "王铮亮&谭松韵 - 小半 (Live)" -> (["王铮亮", "谭松韵"], "小半 (Live)")

        :param title: 原始标题字符串
        :return: (artists_list, song_name) 二元组
        """
        if " - " in title:
            artist_str, song_name = title.split(" - ", 1)
            artists = [a.strip() for a in artist_str.split("&") if a.strip()]
        else:
            # 极端情况：标题中没有 " - " 分隔符
            artists = []
            song_name = title
        return artists, song_name

    def _parse_hot_singers(self, tree):
        """
        解析"热门歌手"模块。
        结构: div.lktitle(h1) 的后续兄弟 div.lksinger_list > ul > li
        每个 li 包含: div.pic > a > img(图片)  +  div.name > a(名称/链接)

        :param tree: lxml etree 对象
        :return: list[dict] 每项含 name / image / singer_url
        """
        li_nodes = tree.xpath(
            '//h1[contains(text(), "热门歌手")]'
            '/ancestor::div[@class="lktitle"]'
            '/following-sibling::div[@class="lksinger_list"]'
            '//li'
        )
        result = []
        for li in li_nodes:
            pic_a = li.xpath('.//div[@class="pic"]/a')
            name_a = li.xpath('.//div[@class="name"]/a')
            if not pic_a or not name_a:
                continue
            img_nodes = pic_a[0].xpath('./img')
            result.append({
                "name": name_a[0].get("title", "").strip(),
                "image": img_nodes[0].get("src", "") if img_nodes else "",
                "singer_url": self.BASE_URL + pic_a[0].get("href", ""),
            })
        return result

    def _parse_song_chart(self, tree, chart_keyword):
        """
        解析歌曲榜单模块（歌曲飙升榜 / 流行趋势榜）。
        结构: div.lktitle(h1含关键词) 的后续兄弟 div.ilingkuplay_list > ul > li
        每个 li 包含: div.name > a[title][href]，title 格式 "歌手 - 歌名"

        :param tree: lxml etree 对象
        :param chart_keyword: 榜单标题关键词，如 "歌曲飙升榜" 或 "流行趋势榜"
        :return: list[dict] 每项含 song_name / artists / song_url
        """
        li_nodes = tree.xpath(
            f'//h1[contains(text(), "{chart_keyword}")]'
            '/ancestor::div[@class="lktitle"]'
            '/following-sibling::div[@class="ilingkuplay_list"]'
            '//li'
        )
        result = []
        for li in li_nodes:
            name_a = li.xpath('.//div[@class="name"]/a')
            if not name_a:
                continue
            title = name_a[0].get("title", "").strip()
            artists, song_name = self._parse_song_title(title)
            result.append({
                "song_name": song_name,
                "artists": artists,
                "song_url": self.BASE_URL + name_a[0].get("href", ""),
            })
        return result

    # ---------- 歌手详情页解析 ----------

    @staticmethod
    def _extract_page_num(href):
        """
        从分页链接中提取页码。
        链接格式: /singer/bm1z/2.html -> 2

        :param href: 相对路径链接
        :return: 页码整数；无法提取时返回 None
        """
        # 取最后一段文件名，如 "2.html"，去掉 ".html" 后转整数
        filename = href.rstrip("/").rsplit("/", 1)[-1]
        name = filename.replace(".html", "")
        return int(name) if name.isdigit() else None

    def _parse_singer_info(self, tree):
        """
        解析歌手基本信息（封面图、名称、简介）。
        结构: div.singer_info > div.pic > img  +  div.list_r > h1 / div.info > p

        :param tree: lxml etree 对象
        :return: dict 含 name / cover / intro；无数据时各字段为空字符串
        """
        # 封面图: div.singer_info > div.pic > img @src
        img_nodes = tree.xpath('//div[@class="singer_info"]//div[@class="pic"]//img')
        cover = img_nodes[0].get("src", "") if img_nodes else ""

        # 歌手名称: div.singer_info > div.list_r > h1
        name_nodes = tree.xpath('//div[@class="singer_info"]//div[@class="list_r"]/h1')
        name = name_nodes[0].text.strip() if name_nodes and name_nodes[0].text else ""

        # 简介: div.singer_info > div.list_r > div.info > p
        info_nodes = tree.xpath('//div[@class="singer_info"]//div[@class="info"]/p')
        intro = ""
        if info_nodes:
            # 获取 p 标签内完整文本（包含 <br> 产生的换行），保留原始换行
            intro = info_nodes[0].xpath("string(.)").strip()

        return {"name": name, "cover": cover, "intro": intro}

    def _parse_singer_songs(self, tree):
        """
        解析歌手详情页"最新歌曲"列表。
        结构: div.play_list > ul > li > div.name > a（a 标签文本即 "歌手 - 歌名"）

        :param tree: lxml etree 对象
        :return: list[dict] 每项含 song_name / artists / song_url
        """
        li_nodes = tree.xpath('//div[@class="play_list"]//ul/li')
        result = []
        for li in li_nodes:
            name_a = li.xpath('.//div[@class="name"]/a')
            if not name_a:
                continue
            # 歌手详情页的 a 标签无 title 属性，文本内容即标题
            title = name_a[0].text.strip() if name_a[0].text else ""
            if not title:
                continue
            artists, song_name = self._parse_song_title(title)
            result.append({
                "song_name": song_name,
                "artists": artists,
                "song_url": self.BASE_URL + name_a[0].get("href", ""),
            })
        return result

    def _parse_pagination(self, tree, current_url):
        """
        解析分页信息，返回当前页/首页/上一页/下一页/尾页。
        结构: div.page > a，通过文本("首页"/"上一页"/"下一页"/"尾页")与 class(current) 区分。
        边界: 第1页无"首页""上一页"；最后一页无"下一页""尾页"。

        :param tree: lxml etree 对象
        :param current_url: 当前请求的 URL（用于当前页 URL）
        :return: dict 含 current/first/prev/next/last，不存在的分页为 None；
                 每项为 {"page": int, "url": str}
        """
        page_div = tree.xpath('//div[@class="page"]')
        if not page_div:
            return None

        # 各分页节点，初始为 None
        current = first = prev = next_page = last = None

        for a in page_div[0].xpath('./a'):
            text = (a.text or "").strip()
            href = a.get("href", "")
            cls = a.get("class", "")

            def build_page(node_href, node_text):
                """根据 href 和文本构建分页条目"""
                page = None
                if node_text.isdigit():
                    page = int(node_text)
                else:
                    page = self._extract_page_num(node_href)
                url = self.BASE_URL + node_href if node_href else ""
                return {"page": page, "url": url}

            if cls == "current":
                # 当前页: a.current，文本是页码，无 href
                page = int(text) if text.isdigit() else None
                current = {"page": page, "url": current_url}
            elif text == "首页":
                first = build_page(href, text)
            elif text == "上一页":
                prev = build_page(href, text)
            elif text == "下一页":
                next_page = build_page(href, text)
            elif text == "尾页":
                last = build_page(href, text)

        return {
            "current": current,
            "first": first,
            "prev": prev,
            "next": next_page,
            "last": last,
        }

    # ---------- 歌曲详情页解析 ----------

    @staticmethod
    def _extract_song_id(url):
        """
        从歌曲详情页 URL 中提取歌曲 id。
        URL 格式: https://www.2t58.com/song/d3dkc2t3.html -> d3dkc2t3

        :param url: 歌曲详情页 URL
        :return: 歌曲 id 字符串；无法提取时返回 None
        """
        match = re.search(r"/song/([A-Za-z0-9]+)\.html", url)
        return match.group(1) if match else None

    def _decrypt_play_url(self, encrypted):
        """
        解密播放链接。
        网站使用 AES-ECB 模式加密播放 URL，密钥由固定明文经 SHA256 生成，
        密文为 Hex 编码。解密后得到原始播放链接。

        :param encrypted: Hex 编码的加密播放链接
        :return: 解密后的播放链接字符串；解密失败时返回空字符串
        """
        if not encrypted:
            return ""
        try:
            # SHA256 生成 32 字节 AES 密钥
            key = hashlib.sha256(self.DECRYPT_KEY.encode("utf-8")).digest()
            # Hex 解码密文
            ciphertext = bytes.fromhex(encrypted)
            # AES-ECB 解密并去除 Pkcs7 填充
            cipher = AES.new(key, AES.MODE_ECB)
            decrypted = unpad(cipher.decrypt(ciphertext), AES.block_size)
            return decrypted.decode("utf-8")
        except (ValueError, KeyError):
            # 解密失败（密文格式错误/密钥变更/填充错误）
            return ""

    def _fetch_play_info(self, song_id, page_url):
        """
        请求 play.php 接口获取播放信息（加密播放链接、封面图、歌词 cid）。

        :param song_id: 歌曲 id，如 "d3dkc2t3"
        :param page_url: 歌曲详情页 URL（用于 Referer 头）
        :return: dict 含:
            - play_url: 解密后的播放链接（解密失败为空字符串）
            - cover: 封面图 URL
            - cid: 歌词接口所需的 id（即 lkid）
            请求失败时各字段为空
        """
        # play.php 需要带 X-Requested-With 头以返回 JSON
        headers = {
            "X-Requested-With": "XMLHttpRequest",
            "Referer": page_url,
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        }
        try:
            self._refresh_proxy()
            resp = self.session.post(
                self.PLAY_API,
                data={"id": song_id, "type": "music"},
                headers=headers,
                timeout=self.TIMEOUT,
            )
            data = resp.json()
        except (requests.RequestException, ValueError):
            # 请求失败或 JSON 解析失败
            return {"play_url": "", "cover": "", "cid": ""}

        if data.get("msg") != 1:
            # 接口返回失败
            return {"play_url": "", "cover": "", "cid": ""}

        encrypted_url = data.get("url", "")
        return {
            "play_url": self._decrypt_play_url(encrypted_url),
            "cover": data.get("pic", ""),
            "cid": str(data.get("lkid", "")),
        }

    def _fetch_lyrics(self, cid):
        """
        请求 lrc.php 接口获取歌词文本。

        :param cid: 歌词接口 id（来自 play.php 返回的 lkid）
        :return: LRC 格式歌词字符串；请求失败时返回空字符串
        """
        if not cid:
            return ""
        try:
            self._refresh_proxy()
            resp = self.session.get(
                self.LRC_API, params={"cid": cid}, timeout=self.TIMEOUT
            )
            data = resp.json()
            return data.get("lrc", "")
        except (requests.RequestException, ValueError):
            return ""

    def _parse_song_info(self, tree):
        """
        解析歌曲基本信息（封面图、歌手名称、歌曲名称）。
        结构:
            - 歌名: div.djname > h1 文本，格式 "歌手 - 歌名"
            - 封面图: div.play_singer > div.pic > a > img @src
            - 歌手: div.play_singer > div.center > div.name > a @title

        :param tree: lxml etree 对象
        :return: dict 含 cover / artists / song_name
        """
        # 歌名: div.djname > h1 的直接文本节点（排除"刷新"按钮文本）
        h1_texts = tree.xpath('//div[@class="djname"]/h1/text()')
        title = "".join(h1_texts).strip()
        artists, song_name = self._parse_song_title(title)

        # 封面图: div.play_singer > div.pic > a > img @src
        img_nodes = tree.xpath(
            '//div[@class="play_singer"]//div[@class="pic"]//img'
        )
        cover = img_nodes[0].get("src", "") if img_nodes else ""

        # 歌手: div.play_singer > div.center > div.name > a @title
        name_a = tree.xpath(
            '//div[@class="play_singer"]//div[@class="name"]/a'
        )
        if name_a and not artists:
            # 歌名文本拆分失败时，从 name 标签取歌手
            artist_name = name_a[0].get("title", "") or name_a[0].text or ""
            artists = [artist_name.strip()] if artist_name.strip() else []

        return {"cover": cover, "artists": artists, "song_name": song_name}

    def _parse_daily_recommend(self, tree):
        """
        解析"每日推荐"歌曲列表。
        结构: div.play_list > div.title > h1(含"每日推荐") 的后续 ul > li
        每个 li: div.name > a，文本格式 "歌手 - 歌名"，href 为歌曲链接

        :param tree: lxml etree 对象
        :return: list[dict] 每项含 song_name / artists / song_url
        """
        li_nodes = tree.xpath(
            '//div[@class="play_list"]'
            '//div[@class="title"]/h1[contains(text(), "每日推荐")]'
            '/ancestor::div[@class="play_list"]//ul/li'
        )
        result = []
        for li in li_nodes:
            name_a = li.xpath('.//div[@class="name"]/a')
            if not name_a:
                continue
            # a 标签无 title 属性，文本内容即 "歌手 - 歌名"
            title = name_a[0].text.strip() if name_a[0].text else ""
            if not title:
                continue
            artists, song_name = self._parse_song_title(title)
            result.append({
                "song_name": song_name,
                "artists": artists,
                "song_url": self.BASE_URL + name_a[0].get("href", ""),
            })
        return result

    # ---------- 对外接口 ----------

    def get_home_data(self):
        """
        获取首页数据：热门歌手、歌曲飙升榜、流行趋势榜。

        :return: dict 包含三个模块的数据:
            - hot_singers: 热门歌手列表 [{name, image, singer_url}]
            - rising_chart: 歌曲飙升榜 [{song_name, artists, song_url}]
            - trend_chart: 流行趋势榜 [{song_name, artists, song_url}]
        :raises requests.RequestException: 请求失败时抛出
        """
        html_text = self._get_home_html()
        tree = etree.HTML(html_text)
        return {
            "hot_singers": self._parse_hot_singers(tree),
            "rising_chart": self._parse_song_chart(tree, "歌曲飙升榜"),
            "trend_chart": self._parse_song_chart(tree, "流行趋势榜"),
        }

    def get_singer_detail(self, url):
        """
        获取歌手详情页数据：基本信息、最新歌曲列表、分页信息。

        :param url: 歌手歌曲列表页 URL，如
            "https://www.2t58.com/singer/bm1z/1.html"
        :return: dict 含:
            - singer: 歌手基本信息 {name, cover, intro}
            - songs: 最新歌曲列表 [{song_name, artists, song_url}]
            - pagination: 分页 {current, first, prev, next, last}，
              每项为 {page, url}，不存在的分页为 None；无分页时为 None
        :raises requests.RequestException: 请求失败时抛出
        """
        html_text = self._get_html(url)
        tree = etree.HTML(html_text)
        return {
            "singer": self._parse_singer_info(tree),
            "songs": self._parse_singer_songs(tree),
            "pagination": self._parse_pagination(tree, url),
        }

    def get_song_detail(self, url):
        """
        获取音乐详情页数据：基本信息、播放链接、歌词、每日推荐。

        :param url: 歌曲详情页 URL，如
            "https://www.2t58.com/song/d3dkc2t3.html"
        :return: dict 含:
            - song: 基本信息 {cover, artists, song_name}
            - play_url: 在线播放链接（AES 解密后的直链，解密失败为空字符串）
            - lyrics: LRC 格式歌词文本（请求失败为空字符串）
            - daily_recommend: 每日推荐列表 [{song_name, artists, song_url}]
        :raises requests.RequestException: 请求页面失败时抛出
        """
        # 1. 获取页面 HTML（自动处理人机验证，建立 session）
        html_text = self._get_html(url)
        tree = etree.HTML(html_text)

        # 2. 解析基本信息（封面/歌手/歌名）和每日推荐
        song_info = self._parse_song_info(tree)
        daily = self._parse_daily_recommend(tree)

        # 3. 从 URL 提取歌曲 id
        song_id = self._extract_song_id(url)

        # 4. 请求 play.php 获取加密播放链接、封面图、歌词 cid
        play_info = self._fetch_play_info(song_id, url)

        # 5. 用 cid 请求 lrc.php 获取歌词
        lyrics = self._fetch_lyrics(play_info["cid"])

        # 封面图优先使用页面解析的，为空时用 play.php 返回的
        if not song_info["cover"]:
            song_info["cover"] = play_info["cover"]

        return {
            "song": song_info,
            "play_url": play_info["play_url"],
            "lyrics": lyrics,
            "daily_recommend": daily,
        }

    # ---------- 搜索页解析 ----------

    @staticmethod
    def _parse_search_total(tree):
        """
        解析搜索结果总条数。
        结构: div.pagedata > span，文本如 "698"（外层文字为"共有698首搜索结果"）

        :param tree: lxml etree 对象
        :return: 搜索结果总条数整数；无法提取时返回 0
        """
        span_nodes = tree.xpath('//div[@class="pagedata"]/span')
        if not span_nodes:
            return 0
        text = span_nodes[0].text or ""
        text = text.strip()
        return int(text) if text.isdigit() else 0

    def search_music(self, keyword, page=1):
        """
        搜索音乐：根据关键词获取歌曲列表、分页、总结果数。
        搜索 URL 格式: /so/{URL编码后的关键词}/{页码}.html
        示例: keyword="王小草", page=1 ->
            https://www.2t58.com/so/%E7%8E%8B%E5%B0%8F%E8%8D%89/1.html

        :param keyword: 搜索关键词，如 "王小草"
        :param page: 页码，从 1 开始，默认 1
        :return: dict 含:
            - songs: 歌曲列表 [{song_name, artists, song_url}]，
              artists 为多歌手数组（复用歌曲标题拆分逻辑）
            - pagination: 分页 {current, first, prev, next, last}，
              每项为 {page, url}，不存在的分页为 None；无分页时为 None
            - total: 搜索结果总条数（整数，无法提取时为 0）
        :raises requests.RequestException: 请求失败时抛出
        """
        # 关键词 URL 编码（中文转 %XX），构造搜索页 URL
        encoded = quote(keyword)
        url = f"{self.BASE_URL}/so/{encoded}/{page}.html"

        html_text = self._get_html(url)
        tree = etree.HTML(html_text)
        return {
            "songs": self._parse_singer_songs(tree),
            "pagination": self._parse_pagination(tree, url),
            "total": self._parse_search_total(tree),
        }


# ---------- 使用示例 ----------
if __name__ == "__main__":
    spider = Music2t58Spider()

    # 示例1: 获取首页数据（热门歌手 / 歌曲飙升榜 / 流行趋势榜）
    # home_data = spider.get_home_data()
    # print(json.dumps(home_data, ensure_ascii=False, indent=2))

    # 示例2: 获取歌手详情（基本信息 + 最新歌曲 + 分页）
    # url 参数说明: /singer/{歌手ID}/{页码}.html
    # singer_data = spider.get_singer_detail(
    #     "https://www.2t58.com/singer/bm1z/1.html"
    # )
    # print(json.dumps(singer_data, ensure_ascii=False, indent=2))

    # 示例3: 获取音乐详情（基本信息 + 播放链接 + 歌词 + 每日推荐）
    # url 参数说明: /song/{歌曲ID}.html
    # song_data = spider.get_song_detail(
    #     "https://www.2t58.com/song/d3dkc2t3.html"
    # )
    # print(json.dumps(song_data, ensure_ascii=False, indent=2))

    # 示例4: 搜索音乐（歌曲列表 + 分页 + 总条数）
    # keyword 为搜索关键词，page 为页码（默认1）
    search_data = spider.search_music("王小草", page=1)
    print(json.dumps(search_data, ensure_ascii=False, indent=2))
