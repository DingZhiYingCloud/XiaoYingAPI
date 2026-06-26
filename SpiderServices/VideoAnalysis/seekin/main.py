import hashlib
import time

import requests


class SeekinVideoAnalysis:
    """
    Seekin 视频解析服务（https://www.seekin.ai）。

    通过调用 seekin.ai 的通用解析接口，将各平台分享文本解析为无水印下载链接。
    目前支持抖音、小红书、哔哩哔哩三个平台（共用同一接口）。

    工作原理:
        - 接口地址: POST https://api.seekin.ai/ikool/media/download
        - 请求需携带 timestamp 和 sign 签名头
        - 签名算法: SHA256(lang + timestamp + secretKey + "url=" + 分享文本)
        - secretKey 从前端 JS 中提取（混淆拼接后为 "3HT8hjE79L"）
        - 直接传入各平台分享的完整文本即可（包含描述、链接、提示语）
    """

    # ---------- 基础配置 ----------
    # 解析接口地址
    API_URL = "https://api.seekin.ai/ikool/media/download"
    # 签名密钥（从前端 JS chunk D7ORPZcC.js 的 q[0] 拼接得到）
    SECRET_KEY = "3HT8hjE79L"
    # 请求语言（影响返回的提示语，不影响解析结果）
    LANG = "zh"
    # 请求超时时间（秒），解析接口响应较慢，设为 30 秒
    TIMEOUT = 30
    # 通用请求头
    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Origin": "https://www.seekin.ai",
        "Referer": "https://www.seekin.ai/",
        "Accept": "*/*",
    }

    def __init__(self):
        """初始化解析会话。"""
        self.session = requests.Session()
        self.session.headers.update(self.HEADERS)

    def _generate_sign(self, share_text, timestamp):
        """
        生成请求签名。

        签名算法（与前端 generateSignature 一致）:
            sign = SHA256(lang + timestamp + secretKey + "url=" + 分享文本)

        :param share_text: 分享文本（完整的复制内容，含链接和描述）
        :param timestamp: 毫秒时间戳字符串
        :return: 64 位小写十六进制签名字符串
        """
        sign_str = f"{self.LANG}{timestamp}{self.SECRET_KEY}url={share_text}"
        return hashlib.sha256(sign_str.encode("utf-8")).hexdigest()

    def _dedup_by_url(self, items):
        """
        按 URL 去重，同一 URL 只保留第一次出现的项。

        不同平台接口返回差异较大:
            - 抖音会返回 format=None 的重复占位项（URL 与某个画质重复），需去重
            - 哔哩哔哩只返回一个 format=None 的有效项，不能按 format 过滤
        因此统一采用 URL 去重策略：仅丢弃 URL 为空或与前面重复的项。

        :param items: 接口返回的 medias 或 images 原始列表
        :return: 去重后的列表 [{format, url, file_size}]
        """
        seen = set()
        result = []
        for item in items or []:
            url = item.get("url", "")
            if not url or url in seen:
                continue
            seen.add(url)
            result.append({
                "format": item.get("format"),
                "url": url,
                "file_size": item.get("fileSize"),
            })
        return result

    def _parse(self, share_text):
        """
        通用解析方法（核心实现），各平台公开方法统一委托于此。

        :param share_text: 分享文本（完整复制内容）。
        :return: dict 含:
            - title: 标题
            - cover: 封面图 URL
            - duration: 时长（秒，可能为 None）
            - medias: 视频/音频下载列表 [{format, url, file_size}]，
                format 为画质描述（如 "1080p (96.75 MB) [.mp4]"），图文内容时为空列表
            - images: 图片下载列表 [{format, url, file_size}]，视频内容时可能为空
        :raises RuntimeError: 请求失败或接口返回错误时抛出
        """
        timestamp = str(int(time.time() * 1000))
        sign = self._generate_sign(share_text, timestamp)

        try:
            resp = self.session.post(
                self.API_URL,
                json={"url": share_text},
                headers={
                    "Content-Type": "application/json",
                    "lang": self.LANG,
                    "timestamp": timestamp,
                    "sign": sign,
                },
                timeout=self.TIMEOUT,
            )
            data = resp.json()
        except (requests.RequestException, ValueError) as e:
            raise RuntimeError(f"解析请求失败: {e}")

        if data.get("code") != "0000":
            raise RuntimeError(f"解析失败: {data.get('msg', '未知错误')}")

        result = data.get("data", {})
        return {
            "title": result.get("title", ""),
            "cover": result.get("imageUrl", ""),
            "duration": result.get("duration"),
            "medias": self._dedup_by_url(result.get("medias")),
            "images": self._dedup_by_url(result.get("images")),
        }

    def parse_video(self, share_text):
        """
        解析抖音视频，返回无水印下载链接。

        :param share_text: 抖音分享文本（完整复制内容）。
            示例: "5.89 dAT:/ ... https://v.douyin.com/xxxxx/ 复制此链接，打开Dou音搜索，直接观看视频！"
        :return: 见 _parse 返回结构
        """
        return self._parse(share_text)

    def parse_xiaohongshu(self, share_text):
        """
        解析小红书内容，返回视频或图文下载链接。

        支持视频笔记和图文笔记两种类型:
            - 视频笔记: medias 包含视频下载链接，images 为空
            - 图文笔记: medias 为空，images 包含图片下载链接

        :param share_text: 小红书分享文本（完整复制内容）。
            示例: "13 【标题 - 作者 | 小红书 - 你的生活兴趣社区】 😆 xxx 😆 https://www.xiaohongshu.com/..."
        :return: 见 _parse 返回结构
        """
        return self._parse(share_text)

    def parse_bilibili(self, share_text):
        """
        解析哔哩哔哩视频，返回下载链接。

        :param share_text: 哔哩哔哩分享文本（完整复制内容）。
            示例: "【标题】 https://www.bilibili.com/video/BVxxxx/?share_source=copy_web&..."
        :return: 见 _parse 返回结构
        """
        return self._parse(share_text)


# ---------- 使用示例 ----------
if __name__ == "__main__":
    spider = SeekinVideoAnalysis()

    # 抖音测试链接
    douyin_text = (
        "5.89 dAT:/ :7pm d@a.Nj 03/21 经典粤语30分钟合集# 经典粤语# 粤语# 粤语歌曲  "
        "https://v.douyin.com/2T5advcplsU/  复制此链接，打开Dou音搜索，直接观看视频！"
    )

    # 小红书测试链接 1: 图文笔记
    xhs_text_1 = (
        "13 【我愿称之为微胖的魅力！！ - 圆脸小王 | 小红书 - 你的生活兴趣社区】 "
        "😆 5CmmffZgueYSK7z 😆 "
        "https://www.xiaohongshu.com/discovery/item/6a3ca9bf00000000070220c6"
        "?source=webshare&xhsshare=pc_web"
        "&xsec_token=ABIzKQumYxOjTP92B6360_p0FtIwm3AYwbmpBGO3bVzf0=&xsec_source=pc_share"
    )
    # 小红书测试链接 2: 视频
    xhs_text_2 = (
        "11 【学中医的爷爷让我这个季节要多喝这些营养汤 - 虾仁煲汤记 | 小红书 - 你的生活兴趣社区】 "
        "😆 GrnArDCPeRQLgBl 😆 "
        "https://www.xiaohongshu.com/discovery/item/6a2b9b8b00000000210166b8"
        "?source=webshare&xhsshare=pc_web"
        "&xsec_token=ABWUJeIfguMuTZlxDstUUej7HvzG5BeCbuEccPPOdPgKw=&xsec_source=pc_share"
    )

    # 哔哩哔哩测试链接 1
    bili_text_1 = (
        "【又随便又好吃的面怎么做出来的...】 "
        "https://www.bilibili.com/video/BV1EEjz6HEwR/"
        "?share_source=copy_web&vd_source=1ec38498fe56f7c60b3e8091c71969c0"
    )
    # 哔哩哔哩测试链接 2
    bili_text_2 = (
        "【【可写进简历】15个Agent智能体实战项目，学完即可就业！从零基础到进阶，层层推进，建议认真学完！】 "
        "https://www.bilibili.com/video/BV1b7EE6EEWV/"
        "?share_source=copy_web&vd_source=1ec38498fe56f7c60b3e8091c71969c0"
    )

    # 逐个测试
    cases = [
        ("抖音", spider.parse_video, douyin_text),
        ("小红书1(图文)", spider.parse_xiaohongshu, xhs_text_1),
        ("小红书2(视频)", spider.parse_xiaohongshu, xhs_text_2),
        ("哔哩哔哩1", spider.parse_bilibili, bili_text_1),
        ("哔哩哔哩2", spider.parse_bilibili, bili_text_2),
    ]

    for name, method, text in cases:
        print(f"===== {name} =====")
        result = method(text)
        print(f"标题: {result['title']}")
        print(f"封面: {result['cover'][:80]}...")
        print(f"时长: {result['duration']}")
        print(f"视频/音频链接数: {len(result['medias'])}")
        for m in result["medias"]:
            print(f"  - {m['format']} | {m['file_size']} 字节")
        print(f"图片链接数: {len(result['images'])}")
        for img in result["images"]:
            print(f"  - {img['format']} | {img['file_size']} 字节")
        print()
