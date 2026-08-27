"""请求身份识别 - 判定逻辑封装

本模块对外提供 detect() 核心函数，基于请求头特征判定请求来源，输出三分类:
    type=human   - 真人浏览器访问
    type=spider  - 搜索引擎蜘蛛（Googlebot/bingbot 等）
    type=unknown - 脚本爬虫 / 无法识别的来源

判定依据:
    - UA 特征库（ua_patterns.py，独立维护）：浏览器 / 搜索引擎蜘蛛 / 脚本爬虫
    - 浏览器特征头：Sec-Fetch-* 系列、Accept、Accept-Language 等现代浏览器信号
    - Referer 来源分析：无/搜索引擎/外部站/同站导航，来源库见 sources.json
    - IP：仅作信息记录输出，不参与判定（暂不做 IP 信誉）

代码片段联动:
    判定出 type 后，自动加载 code_snippets/<type>/ 目录下的全部 .py 代码文件
    （列表形式返回），供客户端中间件 exec 执行。见 client_middleware 目录说明。
"""
import json
import os
import re
from urllib.parse import urlparse

from .ua_patterns import BROWSER_UA_PATTERNS, SPIDER_UA_PATTERNS, SCRIPT_UA_PATTERNS

# ── 来源库加载 ──
_SOURCES_PATH = os.path.join(os.path.dirname(__file__), 'sources.json')


def _load_sources():
    """加载来源库配置（域名 -> {name, type}），失败时返回空字典"""
    try:
        with open(_SOURCES_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


_SOURCES = _load_sources()


def _match_ua(user_agent):
    """判定 UA 归属（三分类）

    匹配顺序: 搜索引擎蜘蛛 -> 脚本爬虫 -> 浏览器，命中即停。

    :param user_agent: User-Agent 字符串（可能为空）
    :return: dict{has_ua, is_spider, spider_name, is_script, script_name,
                  is_browser, browser_name}
    """
    result = {
        'has_ua': bool(user_agent),
        'is_spider': False,
        'spider_name': None,
        'is_script': False,
        'script_name': None,
        'is_browser': False,
        'browser_name': None,
    }
    if not user_agent:
        return result

    for name, pattern in SPIDER_UA_PATTERNS:
        if re.search(pattern, user_agent, re.IGNORECASE):
            result['is_spider'] = True
            result['spider_name'] = name
            return result

    for name, pattern in SCRIPT_UA_PATTERNS:
        if re.search(pattern, user_agent, re.IGNORECASE):
            result['is_script'] = True
            result['script_name'] = name
            return result

    for name, pattern in BROWSER_UA_PATTERNS:
        if re.search(pattern, user_agent, re.IGNORECASE):
            result['is_browser'] = True
            result['browser_name'] = name
            return result

    return result


def _get_header(headers, *names):
    """从请求头字典中按名称（不区分大小写）取值，返回第一个命中的值"""
    if not isinstance(headers, dict):
        return None
    lower_map = {k.lower(): v for k, v in headers.items()}
    for name in names:
        value = lower_map.get(name.lower())
        if value:
            return str(value).strip()
    return None


def _extract_referer_info(referer, site):
    """分析 Referer 来源归属

    :param referer: Referer 完整 URL 或域名（可能为空）
    :param site: 调用方域名（可选），用于同站导航判断
    :return: dict{present, raw, host, type, source_name, source_type}
    """
    info = {
        'present': bool(referer),
        'raw': referer or None,
        'host': None,
        'type': 'direct',       # direct / search_engine / external / same_site
        'source_name': None,    # 来源名称（命中来源库时）
        'source_type': None,    # 来源类型（来源库中的 type，如 search_engine）
    }
    if not referer:
        return info

    # 提取 host：允许传完整 URL，也允许直接传域名
    referer = referer.strip()
    host = None
    if '://' in referer:
        parsed = urlparse(referer)
        host = parsed.hostname
    elif '/' not in referer:
        host = referer.split(':', 1)[0]  # 去掉可能带的端口
    if not host:
        return info
    host = host.lower().lstrip('www.')
    info['host'] = host

    # 1. 命中来源库（按域名后缀匹配，如 www.bing.com -> bing.com）
    for domain, meta in _SOURCES.items():
        if host == domain or host.endswith('.' + domain):
            info['type'] = meta.get('type', 'external')
            info['source_name'] = meta.get('name', domain)
            info['source_type'] = meta.get('type', 'external')
            return info

    # 2. 同站导航判断（site 参数存在且同域时）
    if site:
        site_host = site.strip().lower().lstrip('www.')
        if host == site_host or host.endswith('.' + site_host):
            info['type'] = 'same_site'
            return info

    # 3. 其他外部域名
    info['type'] = 'external'
    return info


def _load_code_files(request_type):
    """加载指定类型目录下的全部 Python 代码文件

    :param request_type: human / spider / unknown
    :return: list[{filename, content}]，目录不存在或无文件时返回空列表
    """
    base = os.path.join(os.path.dirname(__file__), 'code_snippets', request_type)
    files = []
    try:
        names = sorted(os.listdir(base))
    except OSError:
        return files
    for name in names:
        if name.endswith('.py'):
            path = os.path.join(base, name)
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    files.append({'filename': name, 'content': f.read()})
            except OSError:
                continue
    return files


# ── 置信度加权打分（阈值与权重集中在此，便于调参）──
BASE_SCORE = 50                 # 基础分
SCORE_BROWSER_UA = 25           # UA 为浏览器
SCORE_SEC_FETCH = 15            # 存在 Sec-Fetch-* 系列头
SCORE_SEC_FETCH_SITE = 10       # Sec-Fetch-Site 值合法
SCORE_ACCEPT_LANG = 5           # Accept-Language 非通配
SCORE_ACCEPT_HTML = 5           # Accept 包含 text/html
SCORE_HAS_REFERER = 10          # 有来源（更可能是用户点击进入）
ROBOT_FLOOR_SCORE = 15          # 判定为蜘蛛/脚本时的置信度上限
HUMAN_THRESHOLD = 60            # 真人判定阈值
SEC_FETCH_SITE_VALUES = {'none', 'same-origin', 'same-site', 'cross-site'}


def _calc_confidence(ua_result, sec_fetch_site, has_sec_fetch, accept_lang, accept_html, has_referer):
    """加权打分计算人类置信度（0-100）"""
    # 命中蜘蛛/脚本特征：直接压低分并锁定为机器人
    if ua_result['is_spider'] or ua_result['is_script']:
        return ROBOT_FLOOR_SCORE

    score = BASE_SCORE
    if ua_result['is_browser']:
        score += SCORE_BROWSER_UA
    if has_sec_fetch:
        score += SCORE_SEC_FETCH
        if sec_fetch_site in SEC_FETCH_SITE_VALUES:
            score += SCORE_SEC_FETCH_SITE
    if accept_lang and accept_lang != '*':
        score += SCORE_ACCEPT_LANG
    if accept_html:
        score += SCORE_ACCEPT_HTML
    if has_referer:
        score += SCORE_HAS_REFERER

    return max(0, min(99, score))


def detect(headers=None, user_agent=None, referer=None, ip=None, site=None):
    """请求身份识别（核心入口）

    所有参数均可选，未提供的按「没有」处理：
    :param headers: 原请求头 JSON 字典（推荐，自动提取 UA/Referer/Sec-Fetch-* 等）
    :param user_agent: User-Agent 字符串（与 headers 二选一，headers 优先）
    :param referer: Referer 字符串（与 headers 二选一，headers 优先）
    :param ip: 客户端 IP（仅记录输出，不参与判定）
    :param site: 调用方域名（可选），用于判断 referer 是否为同站导航
    :return: dict 判定结果（type + 多标签布尔 + 置信度 + 命中原因 + 来源分析 + 代码片段）
    """
    # ── 1. 参数归一化：headers 优先，单字段兜底 ──
    ua = _get_header(headers, 'user-agent') or user_agent
    ref = _get_header(headers, 'referer') or referer
    sec_fetch_site = _get_header(headers, 'sec-fetch-site')
    has_sec_fetch = any(_get_header(headers, f'sec-fetch-{k}') for k in ('site', 'mode', 'dest'))
    accept_lang = _get_header(headers, 'accept-language')
    accept_html = bool(_get_header(headers, 'accept')) and 'text/html' in _get_header(headers, 'accept')

    # ── 2. UA 判定（三分类） ──
    ua_result = _match_ua(ua)

    # ── 3. Referer 来源分析 ──
    referer_info = _extract_referer_info(ref, site)

    # ── 4. 置信度打分 ──
    confidence = _calc_confidence(
        ua_result,
        sec_fetch_site,
        has_sec_fetch,
        accept_lang,
        accept_html,
        referer_info['present'],
    )

    # ── 5. 类型判定（human / spider / unknown） ──
    if ua_result['is_spider']:
        request_type = 'spider'
    elif ua_result['is_script']:
        request_type = 'unknown'
    elif ua_result['is_browser'] and confidence >= HUMAN_THRESHOLD:
        request_type = 'human'
    else:
        request_type = 'unknown'

    is_spider = ua_result['is_spider'] or ua_result['is_script']
    is_human = request_type == 'human'
    is_direct_access = not referer_info['present']

    # ── 6. 命中原因 ──
    reasons = []
    if ua_result['is_spider']:
        reasons.append(f'UA 命中搜索引擎蜘蛛: {ua_result["spider_name"]}')
    elif ua_result['is_script']:
        reasons.append(f'UA 命中脚本爬虫特征: {ua_result["script_name"]}')
    elif ua_result['is_browser']:
        reasons.append(f'UA 为浏览器: {ua_result["browser_name"]}')
    elif not ua:
        reasons.append('未提供 User-Agent')
    else:
        reasons.append('UA 无法识别为已知浏览器、蜘蛛或脚本')
    if has_sec_fetch:
        reasons.append('存在 Sec-Fetch-* 系列头（浏览器特征）')
    else:
        reasons.append('缺少 Sec-Fetch-* 系列头')
    if referer_info['present']:
        if referer_info['type'] == 'search_engine':
            reasons.append(f'来自搜索引擎: {referer_info["source_name"]}')
        elif referer_info['type'] == 'same_site':
            reasons.append('来自同站导航')
        elif referer_info['type'] == 'external':
            reasons.append(f'来自外部站点: {referer_info["host"]}')
    else:
        reasons.append('无 Referer（直接访问）')

    # ── 7. 代码片段联动：加载该类型全部 .py 代码 ──
    code_files = _load_code_files(request_type)

    return {
        'type': request_type,
        'is_spider': is_spider,
        'is_human': is_human,
        'is_direct_access': is_direct_access,
        'confidence': confidence,
        'reasons': reasons,
        'referer': referer_info,
        'code_files': code_files,
        'ip': ip,           # 仅记录
        'ua': ua,           # 仅记录
    }
