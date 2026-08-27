"""动作执行器：按类型执行 pass / redirect / not_found / render

动作说明:
    pass       - 放行（返回 None，继续处理请求）
    redirect   - 302 跳转（配置需含 url）
    not_found  - 返回 404
    render     - 直接返回指定内容，内容来源（优先级从高到低）:
        html     - HTML 字符串
        template - Django 模板名（render_to_string 渲染）
        file     - 本地文件路径（绝对路径；相对路径基于 settings.BASE_DIR 解析）
        url      - http(s) 链接，拉取远程 HTML 内容返回（需 pip install requests）
        domain   - 域名，返回 iframe 页面直接渲染该域名网站

非法配置（redirect 缺 url / render 无任何内容来源 / 来源获取失败 / 未知动作）
一律回退为放行并记 warning。
"""
import logging
import os

import requests
from django.conf import settings
from django.http import HttpResponse, HttpResponseNotFound, HttpResponseRedirect
from django.template import TemplateDoesNotExist
from django.template.loader import render_to_string

logger = logging.getLogger('cloak_guard')

# 拉取远程 url 时的超时秒数与 UA（避免被目标站识别为默认 requests UA）
FETCH_TIMEOUT = 5
FETCH_UA = 'Mozilla/5.0 (compatible; cloak-guard/1.1; +local middleware)'

# 默认动作: {类型: (动作, 跳转URL)}
DEFAULT_ACTIONS = {
    'spider':  ('pass', None),       # 搜索引擎蜘蛛 → 默认放行
    'human':   ('pass', None),       # 真人浏览器 → 默认放行（保守）
    'direct':  ('not_found', None),  # 直接访问（无 Referer）→ 默认 404
    'unknown': ('not_found', None),  # 脚本爬虫/未知 → 默认 404
}

ALLOWED_ACTIONS = ('pass', 'redirect', 'not_found', 'render')


def resolve_action(req_type, actions_config):
    """解析该类型的动作配置；非法配置回退为 pass

    :return: (action, cfg)  action 为 'pass'/'redirect'/'not_found'/'render'
    """
    cfg = (actions_config or {}).get(req_type) or {}
    action = cfg.get('action') or DEFAULT_ACTIONS[req_type][0]
    if action not in ALLOWED_ACTIONS:
        logger.warning('cloak_guard type=%s 非法动作 %r，已回退为放行', req_type, action)
        return 'pass', {}
    return action, cfg


def build_response(action, cfg):
    """根据动作生成响应；pass 返回 None（由中间件继续处理请求）"""
    if action == 'redirect':
        url = cfg.get('url')
        if not url:
            logger.warning('cloak_guard redirect 缺少 url，已回退为放行')
            return None
        return HttpResponseRedirect(url)

    if action == 'not_found':
        return HttpResponseNotFound('Not Found')

    if action == 'render':
        return _build_render_response(cfg)

    return None  # pass


def _build_render_response(cfg):
    """根据 render 配置生成响应；内容来源优先级: html > template > file > url > domain"""
    html = cfg.get('html')
    template = cfg.get('template')
    file_path = cfg.get('file')
    url = cfg.get('url')
    domain = cfg.get('domain')

    # 1. HTML 字符串
    if html:
        return HttpResponse(html)

    # 2. Django 模板
    if template:
        try:
            return HttpResponse(render_to_string(template))
        except TemplateDoesNotExist:
            logger.warning('cloak_guard render 模板 %s 不存在，已回退为放行', template)
            return None

    # 3. 本地文件
    if file_path:
        try:
            with open(_resolve_path(file_path), 'r', encoding='utf-8') as f:
                return HttpResponse(f.read())
        except (OSError, IOError) as e:
            logger.warning('cloak_guard render 文件 %s 读取失败: %s，已回退为放行', file_path, e)
            return None

    # 4. 远程 http(s) 链接
    if url:
        try:
            resp = requests.get(url, timeout=FETCH_TIMEOUT, headers={'User-Agent': FETCH_UA})
            resp.raise_for_status()
            return HttpResponse(resp.text)
        except Exception as e:
            logger.warning('cloak_guard render 拉取 %s 失败: %s，已回退为放行', url, e)
            return None

    # 5. 域名 → iframe 页面
    if domain:
        iframe = '<iframe src="https://%s" style="width:100%%;height:100vh;border:none"></iframe>' % domain
        return HttpResponse(iframe)

    logger.warning('cloak_guard render 缺少内容来源(html/template/file/url/domain)，已回退为放行')
    return None


def _resolve_path(path):
    """绝对路径（含盘符）直接使用；相对路径基于 settings.BASE_DIR 解析"""
    p = path.replace('\\', '/')
    if os.path.isabs(p) or (len(p) >= 2 and p[1] == ':'):
        return path
    return os.path.join(str(settings.BASE_DIR), path)
