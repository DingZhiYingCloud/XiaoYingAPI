"""
抖音视频/图文解析服务 - DouyinVideoAnalysis

自研级别解析（不调用第三方解析 API），直接与抖音官方接口交互：
    分享文本/短链 → 302 重定向提取 aweme_id
    → ttwid 注册接口获取 cookie
    → 请求 web detail API（无签名 + 失败重试）获取无水印数据

返回统一结构:
    {title, cover, duration, medias: [{format, url, file_size}], images: [...]}

使用示例:
    spider = DouyinVideoAnalysis()
    result = spider.parse(share_text)  # share_text 为抖音完整分享文本或链接

注意:
    抖音反爬频繁改版。2026-09 实测旧 a_bogus 签名已失效（携带即 403
    "Uifid Not Found"），当前采用无签名请求 + 刷新 ttwid 间隔重试策略
    （见 _fetch_detail）。若抖音日后强制签名，需逆向新版算法更新 abogus.py
    后恢复签名请求。
"""

import re
import time

import requests
from urllib.parse import urlencode

from .utils import (
    UA_STRING,
    BASE_PARAMS,
    API_DETAIL,
    TTWID_URL,
    HOME_URL,
    REQUEST_TIMEOUT,
)

# 分享文本中的 URL 提取规则（按优先级排列）
_URL_PATTERNS = [
    r"https?://v\.douyin\.com/[^\s]+",
    r"https?://www\.iesdouyin\.com/[^\s]+",
    r"https?://www\.douyin\.com/[^\s]+",
    r"https?://\S+",  # 兜底：任意 URL
]

# 画质映射：quality_type -> 画质描述
_QUALITY_MAP = {
    1: "1080P",
    2: "1080P",
    3: "1080P (H265)",
    10: "720P",
    20: "540P",
    25: "原画",
}

# 图文类型 aweme_type
_IMAGE_TYPES = (2, 68)

# detail 请求策略（抖音反爬现状，2026-09 实测）：
# 旧版 a_bogus 签名已失效（携带即 403 "Uifid Not Found"），无签名请求有概率性风控。
# 改为无签名请求 + 遇 403/空响应/异常刷新 ttwid 并间隔重试，规避临时风控。
_DETAIL_MAX_RETRY = 3          # 失败后最多重试次数（含首次共 4 次请求）
_DETAIL_RETRY_INTERVAL = 2.0   # 重试间隔（秒），避开连续请求触发风控
_DETAIL_TIMEOUT = 8.0          # 单次 detail 请求超时（秒）——需小于客户端网关超时(15s)，
                               # 避免多次重试累计超过调用方等待上限


class DouyinVideoAnalysis:
    """抖音视频/图文解析服务"""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": UA_STRING})
        # ttwid cookie 是否已就绪（ttwid 有效期较长，会话内复用）
        self._ttwid_ready = False
        # ttwid 所在域（ttwid.bytedance.com）与请求域（douyin.com）不同，
        # session 自动携带 cookie 时不会带上 ttwid，需手动拼 Cookie 头。
        self._cookies_str = ""

    # ---------- 公开接口 ----------

    def parse(self, share_text) -> dict:
        """
        解析抖音分享文本，返回无水印下载信息。

        :param share_text: 抖音分享文本（完整复制内容）或链接。
            示例: "5.89 dAT:/ ... https://v.douyin.com/xxxxx/ 复制此链接，打开Dou音搜索，直接观看视频！"
            也支持直接传 aweme_id 纯数字、完整视频页链接。
        :return: dict 含:
            - title: 视频/图文标题
            - cover: 封面图 URL
            - duration: 时长（秒，图文为 None）
            - medias: 视频下载列表 [{format, url, file_size}]，图文时为空列表
            - images: 图片下载列表 [{format, url, file_size}]，视频时为空列表
        :raises RuntimeError: 请求失败或解析失败时抛出
        """
        try:
            share_url = self._extract_share_url(share_text)
            video_id = self._resolve_video_id(share_url)
            detail = self._fetch_detail(video_id)
            return self._build_result(detail)
        except requests.RequestException as e:
            raise RuntimeError(f"请求抖音接口失败: {e}")
        except ValueError as e:
            raise RuntimeError(str(e))

    # 兼容命名（parse_video 与 parse 等价）
    def parse_video(self, share_text):
        return self.parse(share_text)

    # ---------- 链接解析 ----------

    @staticmethod
    def _extract_share_url(share_text) -> str:
        """
        从分享文本中提取抖音链接。

        支持三种输入:
            1. 纯数字 aweme_id（如 "7679639856579107746"）
            2. 完整链接（如 https://www.douyin.com/video/xxx）
            3. 完整分享文本（含描述、短链、提示语）

        :param share_text: 分享文本
        :return: 提取出的 URL 或 aweme_id
        :raises ValueError: 无法提取时抛出
        """
        text = (share_text or "").strip()
        if not text:
            raise ValueError("分享内容为空")

        # 纯数字 → 直接作为 aweme_id
        if text.isdigit():
            return text

        for pattern in _URL_PATTERNS:
            m = re.search(pattern, text)
            if m:
                # 去除 URL 末尾的标点
                url = m.group(0).rstrip("，。；：！？、,.;:!?）)>】\"'")
                return url

        raise ValueError(f"未能从分享内容中提取到抖音链接: {text[:50]}...")

    def _resolve_video_id(self, share_url: str) -> str:
        """
        从分享链接解析出 aweme_id。

        - 完整链接直接提取；短链则跟随 302 重定向后提取。

        :param share_url: 分享 URL 或 aweme_id
        :return: aweme_id 字符串
        :raises ValueError: 无法解析时抛出
        """
        # 已是纯数字 aweme_id
        if share_url.isdigit():
            return share_url

        # 完整链接中直接提取
        m = re.search(r"/video/(\d+)", share_url)
        if m:
            return m.group(1)

        # 短链：跟随重定向获取真实 URL
        resp = self.session.get(share_url, timeout=REQUEST_TIMEOUT, allow_redirects=True)
        m = re.search(r"/video/(\d+)", resp.url)
        if m:
            return m.group(1)

        # 兜底：从页面 HTML 提取 aweme_id
        m = re.search(r'"aweme_id":"(\d+)"', resp.text)
        if m:
            return m.group(1)

        raise ValueError(f"无法从链接解析出视频 ID: {share_url}")

    # ---------- 数据获取 ----------

    def _ensure_ttwid(self):
        """确保 ttwid cookie 就绪（访问主站 + 调用 ttwid 注册接口）"""
        if self._ttwid_ready:
            return
        # 访问主站获取 __ac_nonce
        self.session.get(HOME_URL, timeout=_DETAIL_TIMEOUT)
        # 注册 ttwid
        self.session.post(
            TTWID_URL,
            json={
                "region": "cn",
                "aid": 1768,
                "needFid": False,
                "service": "www.ixigua.com",
                "migrate_info": {"ticket": "", "source": "node"},
                "cbUrlProtocol": "https",
                "union": True,
            },
            timeout=_DETAIL_TIMEOUT,
        )
        # ttwid 域与 douyin.com 不同，session 不会自动携带，需手动拼 Cookie 头
        self._cookies_str = "; ".join(
            f"{k}={v}" for k, v in self.session.cookies.items()
        )
        self._ttwid_ready = True

    def _fetch_detail(self, video_id: str) -> dict:
        """
        请求 web detail API 获取视频详情。

        反爬现状（2026-09）：旧 a_bogus 签名已失效（携带即 403），
        无签名请求存在概率性风控（实测约 50% 命中）。策略：无签名请求，
        遇 403 / 空响应 / 异常响应时刷新 ttwid 并间隔重试，直至成功或重试耗尽。

        :param video_id: aweme_id
        :return: aweme_detail 字段 dict
        :raises RuntimeError: 重试耗尽仍失败时抛出
        """
        self._ensure_ttwid()
        last_err = "未知原因"
        for attempt in range(_DETAIL_MAX_RETRY + 1):
            api_url = self._build_detail_url(video_id)
            resp = self.session.get(
                api_url,
                headers=self._build_api_headers(video_id),
                timeout=_DETAIL_TIMEOUT,
            )

            # 非 200 或空响应 → 风控拦截/ttwid 失效；仅首次失败刷新 ttwid，
            # 其余重试只做间隔避让（403 多为 IP 级临时风控，重注册 ttwid 无益且耗时）
            if resp.status_code != 200 or not resp.content:
                last_err = f"接口返回 {resp.status_code} / 空响应（可能触发风控）"
                if attempt == 0:
                    self._ttwid_ready = False
                    self._ensure_ttwid()
                if attempt < _DETAIL_MAX_RETRY:
                    time.sleep(_DETAIL_RETRY_INTERVAL)
                continue

            try:
                data = resp.json()
            except ValueError:
                last_err = "接口返回非 JSON 数据"
                if attempt < _DETAIL_MAX_RETRY:
                    time.sleep(_DETAIL_RETRY_INTERVAL)
                continue

            detail = data.get("aweme_detail")
            if not detail:
                last_err = f"接口未返回视频数据: {data.get('status_msg') or data.get('message') or '未知原因'}"
                if attempt < _DETAIL_MAX_RETRY:
                    time.sleep(_DETAIL_RETRY_INTERVAL)
                continue
            return detail

        raise RuntimeError(f"抖音接口多次请求失败: {last_err}")

    def _build_api_headers(self, video_id: str) -> dict:
        """构造 detail API 请求头（含手动拼接的 Cookie）"""
        return {
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Referer": f"https://www.douyin.com/video/{video_id}",
            "Origin": "https://www.douyin.com",
            "Cookie": self._cookies_str,
        }

    def _build_detail_url(self, video_id: str) -> str:
        """
        构造 detail API URL（无 a_bogus 签名）。

        抖音反爬升级后，旧版 a_bogus 签名携带即返回 403（ArgusSecurityPlugin），
        因此直接以明文参数请求，靠重试 + 刷新 ttwid 规避概率性风控。
        注：abogus.py 实现保留，待新版签名算法逆向完成后可恢复签名请求。
        """
        params = BASE_PARAMS.copy()
        params["aweme_id"] = video_id
        return f"{API_DETAIL}?{urlencode(params)}"

    # ---------- 数据组装 ----------

    def _build_result(self, detail: dict) -> dict:
        """
        将 aweme_detail 组装为统一返回结构。

        :param detail: aweme_detail dict
        :return: {title, cover, duration, medias, images}
        """
        video = detail.get("video") or {}
        is_image = detail.get("aweme_type") in _IMAGE_TYPES or bool(detail.get("images"))

        # 封面：优先原图 origin_cover，回退 cover
        cover_urls = (video.get("origin_cover") or {}).get("url_list") or \
                     (video.get("cover") or {}).get("url_list") or []
        cover = cover_urls[0] if cover_urls else ""

        # 时长：detail.duration 为毫秒，转为秒
        duration_ms = detail.get("duration")
        duration = round(duration_ms / 1000, 1) if duration_ms else None

        return {
            "title": detail.get("desc", ""),
            "cover": cover,
            "duration": None if is_image else duration,
            "medias": [] if is_image else self._build_medias(video),
            "images": self._build_images(detail) if is_image else [],
        }

    @staticmethod
    def _build_medias(video: dict) -> list:
        """
        从 video.bit_rate 构建多画质视频下载列表。

        bit_rate 每项含不同清晰度的 play_addr，取各画质 url_list[0]（无水印）。
        同一画质保留一条（bit_rate 中高清档排前，取第一条即最高码率），
        避免返回过多重复链接。
        """
        quality_map = _QUALITY_MAP
        items = []
        seen_format = set()
        for br in video.get("bit_rate") or []:
            play_addr = br.get("play_addr") or {}
            urls = play_addr.get("url_list") or []
            if not urls:
                continue

            qtype = br.get("quality_type")
            fmt = quality_map.get(qtype)
            if not fmt:
                # 兜底：从 gear_name 提取分辨率，如 normal_1080_0 -> 1080P
                gear = br.get("gear_name") or ""
                m = re.search(r"(\d{3,4})", gear)
                if m:
                    res = m.group(1)
                    prefix = "低清 " if "low" in gear else ""
                    suffix = " (H265)" if ("h265" in gear or "_1_1" in gear) else ""
                    fmt = f"{prefix}{res}P{suffix}"
                else:
                    fmt = f"画质{qtype}" if qtype else "未知画质"

            # 同一画质只保留第一条（最高码率档）
            if fmt in seen_format:
                continue
            seen_format.add(fmt)

            items.append({
                "format": fmt,
                "url": urls[0],
                "file_size": play_addr.get("data_size"),
            })
        return items

    @staticmethod
    def _build_images(detail: dict) -> list:
        """从 detail.images 构建图片下载列表"""
        items = []
        for i, img in enumerate(detail.get("images") or [], start=1):
            urls = img.get("url_list") or []
            if not urls:
                continue
            items.append({
                "format": f"图片{i}" + (f" ({img.get('width')}x{img.get('height')})" if img.get("width") else ""),
                "url": urls[0],
                "file_size": None,
            })
        return items


# ---------- 使用示例 ----------
if __name__ == "__main__":
    spider = DouyinVideoAnalysis()

    test_cases = [
        "和7.43 zTy:/ G@v.FH 02/17 :9pm 2026惊悚新片《鲨笼绝境》 # 惊悚电影 # 动作片 # 好看电影分享 https://v.douyin.com/m0ObKweP8EU/ 复制此链接，打开Dou音搜索，直接观看视频！",
        "0.76 05/05 R@x.Fh :3pm JVL:/ 化妆简直邪术 https://v.douyin.com/1dXKn1FcqEQ/ 复制此链接，打开Dou音搜索，直接观看视频！",
    ]

    for text in test_cases:
        print(f"===== {text[:30]}... =====")
        result = spider.parse(text)
        print(f"标题: {result['title']}")
        print(f"封面: {result['cover'][:80]}...")
        print(f"时长: {result['duration']}s")
        print(f"视频链接数: {len(result['medias'])}")
        for m in result["medias"]:
            print(f"  - {m['format']} | {m['file_size']} 字节")
        print(f"图片链接数: {len(result['images'])}")
        print()
