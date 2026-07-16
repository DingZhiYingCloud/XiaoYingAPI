"""必应搜索 & 网页抓取封装

本模块提供两个功能（对应 bing-cn MCP）:
    1. search_bing(query, count, offset) — 搜索必应中文站，返回结构化结果
    2. crawl_webpage(url) — 抓取网页纯文本内容（含黑名单过滤）

依赖: requests, lxml
"""
import os
import re
import uuid

import requests
from lxml import etree

# ==================== 代理配置 ====================
# 从 .env 读取 BING_PROXY_URL，留空/无值则不使用代理
_PROXY_URL = (os.environ.get('BING_PROXY_URL') or '').strip()

# ==================== 必应搜索配置 ====================
BING_SEARCH_URL = "https://cn.bing.com/search"
SEARCH_TIMEOUT = 15

# ==================== 网页抓取配置 ====================
CRAWL_TIMEOUT = 30
# 黑名单（参考 bing-cn-mcp 的 blacklist.ts）
CRAWL_BLACKLIST = [
    # 知乎
    "zhihu.com", "zhuanlan.zhihu.com",
    # 小红书
    "xiaohongshu.com", "xhs.com",
    # 微博
    "weibo.com", "m.weibo.com",
    # 微信
    "weixin.qq.com", "mp.weixin.qq.com",
    # 抖音 / TikTok
    "douyin.com", "tiktok.com",
    # B站
    "bilibili.com", "m.bilibili.com",
    # CSDN
    "csdn.net", "blog.csdn.net",
]
# 文章正文常见 CSS 选择器（按优先级排列）
# 格式: (description, xpath_expression) 二元组
# description 用于注释, xpath_expression 是完整的 XPath 表达式
ARTICLE_SELECTORS = [
    "//article",
    "//main",
    '//*[@role="main"]',
    '//*[contains(@class,"article-content")]',
    '//*[contains(@class,"post-content")]',
    '//*[contains(@class,"content")]',
    '//*[contains(@class,"main-content")]',
    '//*[@id="content"]',
]

# ==================== 通用 ====================
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Connection": "keep-alive",
}


def _get_session():
    """创建 requests Session，自动配置代理（若 .env 中配置了 BING_PROXY_URL）"""
    session = requests.Session()
    session.headers.update(_HEADERS)
    if _PROXY_URL:
        session.proxies.update({
            "http": _PROXY_URL,
            "https": _PROXY_URL,
        })
    return session


def _is_url_blacklisted(url):
    """检查 URL 是否在黑名单中（域名后缀匹配）"""
    try:
        # 简单正则提取 host
        m = re.search(r"https?://([^/]+)", url)
        if not m:
            return False
        host = m.group(1).lower()
        for domain in CRAWL_BLACKLIST:
            d = domain.lower()
            if host == d or host.endswith("." + d):
                return True
        return False
    except Exception:
        return False


# ==================== 必应搜索 ====================

def _parse_search_results(html, query):
    """解析必应搜索结果 HTML

    必应结果在 .b_algo 元素中:
        h2 > a(title+url)
        .b_caption p (摘要)
        .b_attribution cite (展示 URL)

    :param html: 必应搜索结果页 HTML
    :param query: 搜索词
    :return: dict{query, results:[{uuid, title, url, snippet, displayUrl}], totalResults}
    """
    tree = etree.HTML(html)
    results = []

    for algo in tree.xpath('//li[contains(@class,"b_algo")]'):
        try:
            # 标题 + 链接
            a_tag = algo.xpath('.//h2/a')[0]
            title = algo.xpath('string(.//h2/a)').strip()
            url = a_tag.get("href", "").strip()

            # 摘要
            snippet = algo.xpath('string(.//div[contains(@class,"b_caption")]/p)').strip()

            # 展示 URL
            display = algo.xpath('string(.//cite)').strip() or url

            if title and url:
                results.append({
                    "uuid": uuid.uuid4().hex,
                    "title": title,
                    "url": url,
                    "snippet": snippet,
                    "displayUrl": display,
                })
        except (IndexError, AttributeError):
            continue

    # 结果总数
    total = None
    count_el = tree.xpath('//span[contains(@class,"sb_count")]')
    if count_el:
        text = (count_el[0].text or "")
        nums = re.findall(r"[\d,]+", text)
        if nums:
            total = int(nums[0].replace(",", ""))

    return {
        "query": query,
        "results": results,
        "totalResults": total,
    }


def search_bing(query, count=10, offset=0):
    """执行必应中文搜索

    :param query: 搜索关键词
    :param count: 返回结果数量（1-50），默认 10
    :param offset: 结果偏移量，用于翻页，默认 0
    :return: tuple[bool, Any]
        - 成功: (True, dict{query, results, totalResults})
        - 失败: (False, error_msg)
    """
    try:
        session = _get_session()
        resp = session.get(
            BING_SEARCH_URL,
            params={"q": query, "first": offset + 1},
            timeout=SEARCH_TIMEOUT,
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        return False, f"必应搜索请求失败: {e}"

    try:
        data = _parse_search_results(resp.text, query)
        # 按 count 截断
        data["results"] = data["results"][:count]
        return True, data
    except Exception as e:
        return False, f"解析搜索结果失败: {e}"


# ==================== 网页抓取 ====================

def _crawl_one(url):
    """抓取单个网页的纯文本内容

    :param url: 网页 URL
    :return: tuple[bool, str] (成功/失败, 内容或错误信息)
    """
    if _is_url_blacklisted(url):
        return False, f"该网站在爬虫黑名单中，禁止抓取: {url}"

    try:
        session = _get_session()
        resp = session.get(
            url,
            timeout=CRAWL_TIMEOUT,
        )
        resp.raise_for_status()
        # 自动检测编码，避免 GB2312 等非 UTF-8 页面乱码
        resp.encoding = resp.apparent_encoding
    except requests.RequestException as e:
        return False, f"抓取网页失败: {e}"

    try:
        tree = etree.HTML(resp.text)
        # 移除 script / style / nav / footer / header / iframe / noscript
        for tag in ("script", "style", "nav", "footer", "header", "iframe", "noscript"):
            for el in tree.xpath(f"//{tag}"):
                el.getparent().remove(el)

        # 按选择器优先级提取正文（selectors 已为完整 XPath 表达式）
        content = ""
        for sel in ARTICLE_SELECTORS:
            nodes = tree.xpath(sel)
            if nodes:
                content = _element_text(nodes[0])
                break
        if not content:
            # fallback: body
            body = tree.xpath("//body")
            if body:
                content = _element_text(body[0])

        content = _clean_text(content)
        if len(content) < 50:
            return False, "提取的内容太少或为空"
        return True, content
    except Exception as e:
        return False, f"解析网页失败: {e}"


def _element_text(el):
    """提取元素及其子元素的所有文本"""
    return " ".join(el.xpath(".//text()"))


def _clean_text(text):
    """清理文本：压缩空白"""
    text = re.sub(r"\s+", " ", text)
    text = text.strip()
    return text


def crawl_webpage(url):
    """抓取网页纯文本内容（单入口）

    :param url: 网页 URL
    :return: tuple[bool, Any]
        - 成功: (True, str 文本内容)
        - 失败: (False, error_msg)
    """
    return _crawl_one(url)


def crawl_webpages_batch(urls):
    """批量抓取网页

    :param urls: list[str] URL 列表
    :return: list[dict] 每个元素 {url, content} 或 {url, error}
    """
    results = []
    for url in urls:
        ok, data = _crawl_one(url)
        results.append({"url": url, **({"content": data} if ok else {"error": data})})
    return results
