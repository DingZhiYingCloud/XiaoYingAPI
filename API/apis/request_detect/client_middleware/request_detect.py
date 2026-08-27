"""请求身份识别 - 客户端 Django 中间件（单文件版）

作用:
    在 Django 请求处理前，提取请求头并调用小影API的 /api/request_detect/detect 接口，
    获取判定结果（type/confidence/referer 来源等），并 exec 执行服务端返回的
    「该类型」对应的全部 Python 代码片段。

判定类型 type:
    human   - 真人浏览器访问
    spider  - 搜索引擎蜘蛛（Googlebot/bingbot 等）
    unknown - 脚本爬虫 / 无法识别的来源

接入步骤:
    1. 安装依赖: pip install requests
    2. 将本文件放入项目根目录的 middlewares/ 文件夹:
        your_project/
        ├── middlewares/
        │   └── request_detect.py      # 本文件
        ├── manage.py
        └── ...
    3. 确保 .env 中有小影API基础地址（可选，中间件有兜底默认值）:
        XIAOYING_API_BASE=https://xiaoyingapi.com
    4. 在项目 settings.py 中配置（推荐模板）:
        # ── 请求身份识别中间件配置 ──
        REQUEST_DETECT_API_URL   = f'{os.getenv("XIAOYING_API_BASE", "https://xiaoyingapi.com")}/api/request_detect/detect'  # 小影API地址
        REQUEST_DETECT_ENABLED   = True    # 是否启用本中间件（默认 False）
        REQUEST_DETECT_FAIL_OPEN = True    # 检测接口不可用时: True=放行, False=拒绝(403)
        REQUEST_DETECT_TIMEOUT   = 5       # 调用 detect 接口的超时秒数（默认 5）
    5. 将中间件加入 MIDDLEWARE（建议放在 CommonMiddleware 之前）:
        MIDDLEWARE = [
            'django.middleware.security.SecurityMiddleware',
            ...
            'middlewares.request_detect.RequestDetectMiddleware',
            'django.middleware.common.CommonMiddleware',
            ...
        ]
    6. 在服务端 code_snippets/<type>/ 目录放置你的 Python 代码

安全警告（重要）:
    ⚠️ 本中间件会 exec 执行 detect 接口返回的 Python 代码，属于远程代码执行（RCE）风险。
    仅建议在以下前提同时满足时使用:
    - 内网或完全可信环境
    - API 服务地址使用 HTTPS
    - 服务端 code_snippets 目录的代码来自可信来源且经过评审
"""
import json
import logging
import os

import requests
from django.conf import settings
from django.http import HttpResponseForbidden

logger = logging.getLogger('request_detect')

# 默认 API 地址兜底：优先取环境变量 XIAOYING_API_BASE，未配置时用官方默认域名。
# 项目 settings.py 中已配置 REQUEST_DETECT_API_URL 时，以 settings 为准。
DEFAULT_API_URL = f'{os.getenv("XIAOYING_API_BASE", "https://xiaoyingapi.com")}/api/request_detect/detect'


def extract_headers(request):
    """从 Django HttpRequest 提取请求头字典

    将 request.META 中 HTTP_* 前缀还原为原始头名（如 HTTP_USER_AGENT -> User-Agent），
    便于上报给 detect 接口做特征分析。
    """
    headers = {}
    for key, value in request.META.items():
        if key.startswith('HTTP_'):
            header_name = key[5:].replace('_', '-').title()
            headers[header_name] = value
        elif key in ('CONTENT_TYPE', 'CONTENT_LENGTH'):
            headers[key.replace('_', '-').title()] = value
    return headers


class RequestDetectMiddleware:
    """调用小影API识别请求身份，并 exec 执行对应类型的代码"""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # 未启用则直接放行
        if not getattr(settings, 'REQUEST_DETECT_ENABLED', False):
            return self.get_response(request)

        # 检测并执行代码；返回非 None 表示已拦截（fail-open=False 且检测失败时）
        response = self._detect_and_execute(request)
        if response is not None:
            return response
        return self.get_response(request)

    def _detect_and_execute(self, request):
        """调用 detect 接口并执行代码

        :return: None=继续处理请求；HttpResponse=拦截（仅 fail-open=False 时）
        """
        api_url = getattr(settings, 'REQUEST_DETECT_API_URL', DEFAULT_API_URL)
        timeout = getattr(settings, 'REQUEST_DETECT_TIMEOUT', 5)
        fail_open = getattr(settings, 'REQUEST_DETECT_FAIL_OPEN', True)

        try:
            resp = requests.post(
                api_url,
                data={'headers': json.dumps(extract_headers(request))},
                timeout=timeout,
            )
            resp.raise_for_status()
            payload = resp.json()
        except Exception as e:
            logger.error('request_detect 调用失败: %s', e)
            return None if fail_open else self._forbidden()

        # 服务端返回非成功状态码（如参数错误/内部错误），按 fail-open 策略处理
        if payload.get('code') != 10000:
            logger.warning('request_detect 返回非成功状态码: %s', payload)
            return None if fail_open else self._forbidden()

        self._execute_code(request, payload.get('data') or {})
        return None

    def _execute_code(self, request, data):
        """exec 执行该类型下的全部代码文件

        代码按文件名排序依次执行；单个文件执行失败不影响其余文件，
        失败会记录日志（不阻断请求，代码内部如需阻断请自行抛出并处理）。
        """
        code_files = data.get('code_files') or []
        if not code_files:
            logger.info('request_detect type=%s 无代码可执行', data.get('type'))
            return

        exec_globals = {
            'request': request,
            'detect_result': data,
            'logger': logger,
        }
        for cf in code_files:
            try:
                code = compile(cf['content'], cf['filename'], 'exec')
                exec(code, exec_globals)
            except Exception as e:
                logger.error('执行代码 %s 失败: %s', cf.get('filename'), e)

    def _forbidden(self):
        """fail-open=False 时，检测失败返回 403 拒绝请求"""
        return HttpResponseForbidden('request detect service unavailable')
