"""超管控制台 - 海角社区自动注册

鉴权：仅 Django is_superuser（见 admin_auth.py）；匿名与普通用户会被重定向到 /login/。

页面：
    /console/haijiao/register/                自动注册面板（进度条 + 实时日志 + 结果表）
    /console/haijiao/register/ticket/         领一次性运行票据（每次点「开始」现领）
    /console/haijiao/register/refresh-domain/ 「更新今日域名」按钮（POST，业务探活后切换）
    /console/haijiao/register/stream/         自动注册进度流（SSE，页面用 EventSource 订阅）

为什么用 SSE 而不是轮询：一个账号要「取码 → 打码 → 提交」好几步、单条数秒到数十秒，
轮询只能给一个粗略百分比；SSE 能把每一步实时推给页面。项目里 AI 流式对话与文档页代调
已用同一套（StreamingHttpResponse + text/event-stream + `X-Accel-Buffering: no`）。

为什么要有「一次性票据」：EventSource 在连接意外断开时会**自动重连同一个 URL**，
而本页面的 URL 一旦被执行就会真的去源站注册账号、消耗超级鹰题分。故每次点「开始」时
先向本页领一张**一次性票据**，SSE 首次连接时核销，重连（票据已用掉）会被直接拒绝，
不会因为一次网络抖动重复注册一整批（也顺带挡住连点两次）。

票据**每次点击现领**（而不是页面渲染时下发一张用完就没）：这样跑完一批可以接着再跑，
不必刷新页面 —— 这正是「每次完成后都要手动刷新」那个毛病的解法。

票据放**文件缓存**（caches['haijiao']）而不是 default——default 是 LocMemCache，只在单进程
内有效，uwsgi prefork 多 worker 下换个 worker 就查不到，票据会被误判成失效。

本页不提供对外接口（与红果短剧的外链登记同一口径）：直接调服务层
API/apis/haijiao/utils.py 的 iter_auto_register()。
"""
import json
import logging
import secrets

from django.core.cache import caches
from django.http import JsonResponse, StreamingHttpResponse
from django.shortcuts import render

from API.apis.haijiao import utils as haijiao_utils
from SpiderServices.Chaojiying.utils import CODETYPES
from SpiderServices.haijiao import utils as haijiao_spider_utils
from SpiderServices.haijiao.main import PROXY_PROVIDERS

from .admin_auth import superadmin_required

logger = logging.getLogger(__name__)

# 一次性票据（跨进程共享，见文件头说明）：TTL 1 小时，页面开着不动也能点「开始」
_TICKET_CACHE = caches['haijiao']
_TICKET_PREFIX = 'auto_register_ticket:'
_TICKET_TTL = 3600

# 单条账号的验证码重试上限（页面输入框与该范围一致）
MAX_RETRY_LIMIT = 5

# 出口下拉的取值：直连 + 爬虫层支持的代理线路；label 由模板 {% trans %} 翻译
_PROXY_LABELS = {
    'direct': '直连',
    '51daili': '代理（51代理）',
    'juliang': '代理（巨量）',
    'relay': '代理（51代理·经国内中转）',
}
_PROXY_VALUES = ('direct',) + tuple(PROXY_PROVIDERS)


def _issue_ticket():
    """签发一张一次性票据（页面渲染时下发到前端）"""
    token = secrets.token_urlsafe(16)
    _TICKET_CACHE.set(_TICKET_PREFIX + token, 1, _TICKET_TTL)
    return token


def _consume_ticket(token):
    """核销票据：存在且首次使用返回 True（delete 的返回值即「键存在并被删除」）"""
    return bool(token) and _TICKET_CACHE.delete(_TICKET_PREFIX + token)


def _parse_params(request):
    """解析并校验运行参数

    :return: (params dict, 错误提示)；错误提示非空时直接推送错误帧结束
    """
    max_batch = haijiao_utils.MAX_BATCH_SIZE

    raw = (request.GET.get('count') or '').strip()
    try:
        count = int(raw)
    except (TypeError, ValueError):
        return None, f'参数格式错误: count 必须为整数（收到 {raw!r}）'
    if not 1 <= count <= max_batch:
        return None, f'参数值非法: count 必须在 1~{max_batch} 之间'

    raw = (request.GET.get('max_retry') or '').strip() or str(haijiao_utils.MAX_CAPTCHA_RETRY)
    try:
        max_retry = int(raw)
    except (TypeError, ValueError):
        return None, f'参数格式错误: max_retry 必须为整数（收到 {raw!r}）'
    if not 1 <= max_retry <= MAX_RETRY_LIMIT:
        return None, f'参数值非法: max_retry 必须在 1~{MAX_RETRY_LIMIT} 之间'

    provider = (request.GET.get('provider') or '').strip() or haijiao_utils.DEFAULT_PROXY_PROVIDER
    if provider not in _PROXY_VALUES:
        return None, (f'参数值非法: provider 仅支持 {" / ".join(_PROXY_VALUES)}'
                      f'（收到 {provider!r}）')

    # 识别类型：留空用默认值；非法值直接拒绝（下拉本身就是按官方类型表生成的，正常选不出非法值）
    codetype = (request.GET.get('codetype') or '').strip() or haijiao_utils.OCR_CODETYPE
    if codetype not in CODETYPES:
        return None, f'参数值非法: codetype 不在超级鹰支持的识别类型内（收到 {codetype!r}）'

    return {'count': count, 'max_retry': max_retry, 'provider': provider,
            'codetype': codetype}, None


def _codetype_options():
    """识别类型下拉项：直接由超级鹰官方类型表生成，不另抄一份（否则加类型时会对不上）

    label 形如 `1006 · 1~6位英文数字 · 15`，末尾那段是该类型的题分单价。
    """
    return [{'value': code, 'label': f'{code} · {name} · {price}'}
            for code, (name, price) in CODETYPES.items()]


def _proxy_options():
    """出口下拉项：直连 + 爬虫层支持的代理线路（线路清单来自爬虫层，加线路只改那一处）"""
    return [{'value': value, 'label': _PROXY_LABELS[value]}
            for value in _PROXY_VALUES]


def _sse(payload):
    """把一帧数据序列化成 SSE 帧"""
    return f'data: {json.dumps(payload, ensure_ascii=False)}\n\n'


@superadmin_required
def haijiao_register_view(request):
    """海角自动注册页（纯展示；注册动作走下面的 SSE 流）"""
    return render(request, 'console/haijiao_register.html', {
        'ocr_codetype': haijiao_utils.OCR_CODETYPE,
        'ocr_codetype_label': CODETYPES.get(haijiao_utils.OCR_CODETYPE, ('',))[0],
        'codetypes': _codetype_options(),
        'proxies': _proxy_options(),
        'default_proxy': haijiao_utils.DEFAULT_PROXY_PROVIDER,
        'max_batch': haijiao_utils.MAX_BATCH_SIZE,
        'default_retry': haijiao_utils.MAX_CAPTCHA_RETRY,
        'max_retry_limit': MAX_RETRY_LIMIT,
        # 展示用：本进程当前的海角域名（不触发探测；点「更新今日域名」会强制重探）
        'current_domain': haijiao_spider_utils.BASE_URL,
    })


@superadmin_required
def haijiao_register_ticket_view(request):
    """领一张运行票据（每次点「开始」现领，跑完可接着再跑、无需刷新页面）"""
    return JsonResponse({'ticket': _issue_ticket()})


@superadmin_required
def haijiao_register_domain_refresh_view(request):
    """「更新今日域名」按钮：强制重探今日真正可用的域名并立即切换

    为什么按钮要走业务探活而不是只重探 conf：conf 接口在旧域名上也会返回成功
    （甚至自称今日域名，2026-10-02 线上实测），只信 conf 会把注册切回一个业务端点
    已死的域名。口径见 SpiderServices/haijiao/utils.py 的 refresh_domain_config()。
    成功后本 worker 立即生效；其它 worker 下次建会话经共享缓存自动跟上。
    """
    if request.method != 'POST':
        return JsonResponse({'ok': False, 'msg': '仅支持 POST'}, status=405)
    try:
        config = haijiao_spider_utils.refresh_domain_config()
    except RuntimeError as e:
        logger.warning('手动更新海角今日域名失败: %s', e)
        return JsonResponse({'ok': False, 'msg': str(e)}, status=502)
    return JsonResponse({'ok': True, 'domain': config['domain'],
                         'backup_domain': config.get('backup_domain', ''),
                         'abroad_domain': config.get('abroad_domain', '')})


@superadmin_required
def haijiao_register_stream_view(request):
    """自动注册进度流（SSE）

    查询参数:
        token     (必填): 页面渲染时下发的一次性票据
        count     (必填): 要注册的账号数（1 ~ MAX_BATCH_SIZE）
        provider  (选填): 出口线路 direct / 51daili / juliang，默认见 DEFAULT_PROXY_PROVIDER
        codetype  (选填): 超级鹰识别类型，默认见 OCR_CODETYPE
        max_retry (选填): 单个账号最多尝试几次验证码，默认见 MAX_CAPTCHA_RETRY

    帧为 `data: {...}`，结束标记 `data: [DONE]`；帧结构见 iter_auto_register() 的说明。
    """
    token = request.GET.get('token', '')
    params, error = _parse_params(request)

    def sse():
        try:
            if error:
                yield _sse({'type': 'error', 'msg': error})
            elif not _consume_ticket(token):
                yield _sse({'type': 'error',
                            'msg': '本次运行票据无效或已被使用（重复触发 / 断线重连），'
                                   '请重新点「开始自动注册」'})
            else:
                for frame in haijiao_utils.iter_auto_register(**params):
                    yield _sse(frame)
        except Exception as e:      # noqa: BLE001 - 流断了前端只能看到「连接中断」，故把原因推给页面
            logger.exception('海角自动注册中断')
            yield _sse({'type': 'error', 'msg': f'自动注册中断: {e}'})
        yield 'data: [DONE]\n\n'

    response = StreamingHttpResponse(sse(), content_type='text/event-stream')
    response['Cache-Control'] = 'no-cache'
    response['X-Accel-Buffering'] = 'no'    # 禁用 nginx 缓冲，保证逐块推送
    return response
