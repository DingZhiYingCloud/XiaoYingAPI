"""超管控制台 · 问题反馈中心管理

三页：

    /console/feedback/           反馈管理：按项目 / 状态 / 类型 / AI 审核状态筛选与关键词搜索；
                                 列表点开某条进入详情，可回复（带图 / 带视频）、立即送审、
                                 公开区显示隐藏、关闭 / 重开、删除
    /console/feedback/settings/  反馈中心设置：功能开关、AI 审核与两套提示词、审核模型、
                                 附件上限、限流；反馈类型字典
    /console/contacts/           开发者联系方式：联系方式平台字典 + 各项目联系方式

为什么「开发者联系方式」单独一页：平台字典决定**有哪些联系方式渠道、怎么拼跳转链接**，
各项目的值会展示在对应项目的反馈页与公开区底部（子项目也可调 `GET /api/feedback/contacts`
自己渲染）—— 它的用途不限于反馈中心，配置项也自成一套，故独立成模块页；
两端动作与长度常量仍共用本模块（同一 feature 家族，拆开只会重复定义），
只有 URL / 模板 / 侧边栏入口是分开的，两页之间也互相跳转。

各页表单都走普通 POST + `action` 分发（与 `console_ai.py` 同一套路），
唯一例外是「回复」——它要用 multipart 带上附件，且需要先让 AI 审一遍语气再决定是否发送，
因此返回 JSON 由页面脚本接管（见模板 `console/feedback.html` 的 js 块）：

    action=reply         回复；AI 判定为「提醒」且未带 force=1 时**不落库**，返回 30002
    action=review_reply  只做语气审查（不落库），用于脚本侧的独立预检

「AI 只提醒、不阻断」是需求明确的口径：管理员可以在提醒弹窗里选择「强制发送」，
强制发送会在 `FeedbackAuditLog` 里留下 `forced=True` 的痕迹。

鉴权：仅 Django is_superuser（见 admin_auth.superadmin_required）。
"""
import logging
import uuid
from urllib.parse import parse_qsl, urlencode, urlsplit

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.translation import gettext as _

from API.apis.feedback.ai import review_reply_text, review_submission
from API.apis.feedback.utils import save_attachments
from API.common import StatusCode
from API.models import (AiModel, ContactPlatform, Feedback, FeedbackAttachment,
                        FeedbackAuditLog, FeedbackReply, FeedbackReplyAttachment,
                        FeedbackSetting, FeedbackType, ProjectContact, UserApp)

from .admin_auth import notify_success, superadmin_required

logger = logging.getLogger('api.feedback')

# 列表每页可选条数
PAGE_SIZES = (20, 50, 100)
DEFAULT_PAGE_SIZE = 20

# 超管回复 / 设置页字段的长度上限
MAX_REPLY_LEN = 5000
MAX_NAME_LEN = 30
MAX_CODE_LEN = 30
MAX_URL_TEMPLATE_LEN = 200
MAX_CONTACT_VALUE_LEN = 200


# ==================== 通用工具 ====================

def _json(code, msg='', data=None):
    return JsonResponse({'code': code, 'msg': msg, 'data': data or {}})


def _int_or(raw, fallback, choices=None):
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError):
        return fallback
    if choices and value not in choices:
        return fallback
    return value


def _uuid_or_none(raw):
    try:
        return uuid.UUID(str(raw).strip())
    except (TypeError, ValueError, AttributeError):
        return None


def _filter_query(request):
    """当前筛选条件的查询串（剔除 `page` 与详情参数 `detail`）"""
    params = request.GET.copy()
    params.pop('page', None)
    params.pop('detail', None)
    return params.urlencode()


def _back(request, fallback_url):
    """动作执行后回跳：优先用表单里的站内相对地址（保留列表的筛选与展开的详情）"""
    target = (request.POST.get('next') or '').strip()
    if target.startswith('/') and not target.startswith('//'):
        return redirect(target)
    return redirect(fallback_url)


def _pending_review_hint(setting):
    """AI 审核不可用的原因（供页面提示管理员），可用时返回空串"""
    if not setting.ai_review_enabled:
        return _('后台已关闭「提交时先过 AI 审核」')
    if not AiModel.objects.filter(enabled=True).exists():
        return _('平台还没有上架任何 AI 模型')
    return ''


# ==================== 反馈管理（列表 + 详情） ====================

@superadmin_required
def feedback_view(request):
    if request.method == 'POST':
        return _handle_feedback_action(request)

    params = request.GET
    app_filter = (params.get('app') or '').strip()
    status_filter = (params.get('status') or '').strip()
    type_filter = (params.get('type') or '').strip()
    ai_filter = (params.get('ai') or '').strip()
    keyword = (params.get('q') or '').strip()
    page_size = _int_or(params.get('size'), DEFAULT_PAGE_SIZE, PAGE_SIZES)

    # 注意：annotate() 会带上 GROUP BY，此时 Meta.ordering 不再生成 ORDER BY，
    # 必须显式 order_by，否则分页结果无序且每次翻页都可能重复/漏条
    queryset = (Feedback.objects.select_related('app', 'type', 'user')
                .annotate(reply_count=Count('replies'))
                .order_by('-create_time'))
    if app_filter:
        queryset = queryset.filter(app__app_id=app_filter)
    if status_filter in dict(Feedback.Status.choices):
        queryset = queryset.filter(status=status_filter)
    type_id = _int_or(type_filter, 0)
    if type_id:
        queryset = queryset.filter(type_id=type_id)
    if ai_filter in dict(Feedback.AiStatus.choices):
        queryset = queryset.filter(ai_status=ai_filter)
    if keyword:
        queryset = queryset.filter(
            Q(content__icontains=keyword) | Q(contact_email__icontains=keyword))

    paginator = Paginator(queryset, page_size)
    setting = FeedbackSetting.get_solo()
    filter_query = _filter_query(request)

    return render(request, 'console/feedback.html', {
        'page_obj': paginator.get_page(params.get('page')),
        'paginator': paginator,
        'list_query': filter_query,
        'page_prefix': f'{filter_query}&' if filter_query else '',
        'apps': UserApp.objects.all(),
        'types': FeedbackType.objects.all(),
        'status_choices': Feedback.Status.choices,
        'ai_choices': Feedback.AiStatus.choices,
        'app_filter': app_filter,
        'status_filter': status_filter,
        'type_filter': type_filter,
        'ai_filter': ai_filter,
        'keyword': keyword,
        'page_sizes': PAGE_SIZES,
        'page_size': page_size,
        'setting': setting,
        'review_hint': _pending_review_hint(setting),
        'detail': _detail_context(params.get('detail')),
        'actions': ACTIONS,
    })


def _detail_context(raw_id):
    """详情抽屉的数据（顺带清掉「有新回复」标记）"""
    feedback_id = _uuid_or_none(raw_id)
    if feedback_id is None:
        return None
    feedback = (Feedback.objects.select_related('app', 'type', 'user')
                .filter(pk=feedback_id).first())
    if feedback is None:
        return None
    if feedback.admin_unread:
        feedback.admin_unread = False
        feedback.save(update_fields=['admin_unread', 'updated_time'])
    return {
        'feedback': feedback,
        'attachments': feedback.attachments.all(),
        'replies': feedback.replies.select_related('user').prefetch_related('attachments'),
        'audit_logs': feedback.audit_logs.all()[:20],
    }


# ==================== 反馈管理 · 动作 ====================

def _feedback_or_404(raw_id):
    feedback_id = _uuid_or_none(raw_id)
    return Feedback.objects.filter(pk=feedback_id).first() if feedback_id else None


def _detail_url(request, feedback):
    """回到列表并重新展开这条详情（剔除 next 里旧的 detail / page，保留其余筛选条件）"""
    raw = (request.POST.get('next') or '').strip()
    if not raw.startswith('/') or raw.startswith('//'):
        raw = '/console/feedback/'
    parts = urlsplit(raw)
    params = [(k, v) for k, v in parse_qsl(parts.query) if k not in ('detail', 'page')]
    params.append(('detail', str(feedback.pk)))
    return f'{parts.path}?{urlencode(params)}'


def _act_reply(request, feedback):
    """管理员回复：先审语气（AI 提醒不阻断），再落库并留痕

    返回 JSON（由页面脚本接管）。语气审查的来源分两种：

    - 页面脚本已预检（表单里带 `ai_verdict`）：直接采信，不再重复调用 AI；
    - 没有预检结果（未启用 JS / 直接 POST）：服务端补一次审查，判定为「提醒」且
      未强制发送时返回 30002 且**不落库**，让管理员确认后带 `force=1` 重新提交。

    强制发送只在 AI 确实提醒过时才记 `forced=True`，避免留痕失真。
    """
    setting = FeedbackSetting.get_solo()
    content = (request.POST.get('content') or '').strip()
    if not content:
        return _json(StatusCode.PARAM_MISSING, _('请填写回复内容'))
    if len(content) > MAX_REPLY_LEN:
        return _json(StatusCode.PARAM_VALUE_INVALID, _('回复过长（最多 %d 字）') % MAX_REPLY_LEN)

    force = request.POST.get('force') == '1'
    reviewed = (request.POST.get('ai_verdict') or '').strip()
    if reviewed in ('pass', 'warn', 'skip'):
        # skip = 脚本侧预检时 AI 不可用；不再重复调用，留痕记为「调用失败」
        verdict = '' if reviewed == 'skip' else reviewed
        reason = (request.POST.get('ai_reason') or '').strip()
        model_key = (request.POST.get('ai_model') or '').strip()
        if verdict == 'warn' and not force:
            # 与「服务端补审查」同一口径：提醒状态下必须显式强制才落库
            return _json(StatusCode.STATUS_NOT_ALLOWED, reason or _('AI 提醒：这条回复可能不妥'),
                         {'verdict': 'warn', 'reason': reason})
    else:
        ok, data = review_reply_text(feedback, content)
        if ok:
            verdict, reason, model_key = data['verdict'], data['reason'], data['model_key']
            if verdict == 'warn' and not force:
                # 只提醒、不阻断：内容与附件都不落库，等管理员在弹窗里决定
                return _json(StatusCode.STATUS_NOT_ALLOWED, reason or _('AI 提醒：这条回复可能不妥'),
                             {'verdict': 'warn', 'reason': reason})
        else:
            # AI 不可用不算失败：管理员照常发送，留痕记为「调用失败」
            verdict, reason, model_key = '', str(data), ''

    saved_images, errors = save_attachments(
        request.FILES.getlist('images'), FeedbackAttachment.Kind.IMAGE,
        setting.max_images, setting.max_image_mb)
    saved_videos, more_errors = save_attachments(
        request.FILES.getlist('videos'), FeedbackAttachment.Kind.VIDEO,
        setting.max_videos, setting.max_video_mb)
    errors += more_errors
    if errors:
        return _json(StatusCode.PARAM_VALUE_INVALID, '；'.join(errors))

    reply = FeedbackReply.objects.create(
        feedback=feedback, author_role=FeedbackReply.AuthorRole.ADMIN,
        admin_name=request.user.username, content=content,
    )
    for index, item in enumerate(saved_images + saved_videos):
        FeedbackReplyAttachment.objects.create(reply=reply, sort=index, **item)

    feedback.last_reply_time = timezone.now()
    update_fields = ['last_reply_time', 'updated_time']
    if feedback.status in (Feedback.Status.PENDING, Feedback.Status.PROCESSING):
        feedback.status = Feedback.Status.REPLIED
        update_fields.append('status')
    feedback.save(update_fields=update_fields)

    FeedbackAuditLog.objects.create(
        feedback=feedback, reply=reply, kind=FeedbackAuditLog.Kind.REPLY,
        verdict={'pass': FeedbackAuditLog.Verdict.PASS,
                 'warn': FeedbackAuditLog.Verdict.WARN}.get(
                     verdict, FeedbackAuditLog.Verdict.ERROR),
        model_key=model_key or '', reason=reason or '',
        forced=force and verdict == 'warn', operator=request.user.username,
    )
    return _json(StatusCode.SUCCESS, _('已回复'), {'verdict': verdict or 'pass',
                                                  'redirect': _detail_url(request, feedback)})


def _act_review_reply(request, feedback):
    """只做语气审查（脚本侧预检）：不落库、不留痕

    返回的 `verdict` 会被表单原样带回 `action=reply`（`pass` / `warn` / `skip`），
    这样一次回复只调用一次 AI，服务端也能据实留痕。
    """
    content = (request.POST.get('content') or '').strip()
    if not content:
        return _json(StatusCode.PARAM_MISSING, _('请填写回复内容'))
    ok, data = review_reply_text(feedback, content)
    if not ok:
        # AI 不可用不算失败：管理员照常发送，留痕记为「调用失败」
        return _json(StatusCode.SUCCESS, str(data),
                     {'verdict': 'skip', 'reason': str(data), 'model': ''})
    return _json(StatusCode.SUCCESS, data['reason'], {
        'verdict': data['verdict'], 'reason': data['reason'], 'model': data['model_key']})


def _act_resubmit(request, feedback):
    """立即送审：同步跑一遍提交内容审核（结果直接写回反馈）

    先做一次条件抢占（把「非审核中」置为「审核中」）：后台审核线程用的是同一套口径，
    这样管理员点按与线程同时命中同一条反馈时只有一方真的调用 AI —— 否则会写出两条
    AI 驳回回复、两份审核留痕，还白烧一次额度。
    """
    claimed = Feedback.objects.filter(pk=feedback.pk).exclude(
        ai_status=Feedback.AiStatus.RUNNING).update(
        ai_status=Feedback.AiStatus.RUNNING, updated_time=timezone.now())
    if not claimed:
        messages.error(request, _('该反馈正在审核中，请稍候'))
        return _back(request, '/console/feedback/')

    try:
        ok, message = review_submission(feedback)
        feedback.refresh_from_db(fields=['status', 'ai_status'])
    except Feedback.DoesNotExist:
        # 审核期间反馈被删除：给可读提示，而不是让它冒泡成 500
        messages.error(request, _('该反馈已被删除'))
        return _back(request, '/console/feedback/')
    except Exception:
        logger.exception('立即送审失败: feedback=%s', feedback.pk)
        Feedback.objects.filter(pk=feedback.pk).update(
            ai_status=Feedback.AiStatus.FAILED, updated_time=timezone.now())
        messages.error(request, _('审核过程出错，请稍后重试'))
        return _back(request, '/console/feedback/')

    text = _('审核结果：%(result)s（业务状态 %(status)s / 审核状态 %(ai)s）') % {
        'result': message, 'status': feedback.get_status_display(),
        'ai': feedback.get_ai_status_display()}
    if ok:
        notify_success(request, text)
    else:
        messages.error(request, text)
    return _back(request, '/console/feedback/')


def _act_toggle_public(request, feedback):
    feedback.public_hidden = not feedback.public_hidden
    feedback.save(update_fields=['public_hidden', 'updated_time'])
    notify_success(request, _('已从公开区撤下') if feedback.public_hidden
                     else _('已恢复到公开区'))
    return _back(request, '/console/feedback/')


def _act_close(request, feedback):
    if feedback.status == Feedback.Status.CLOSED:
        messages.error(request, _('该反馈已是「已关闭」'))
        return _back(request, '/console/feedback/')
    feedback.status = Feedback.Status.CLOSED
    feedback.save(update_fields=['status', 'updated_time'])
    notify_success(request, _('已关闭该反馈'))
    return _back(request, '/console/feedback/')


def _act_reopen(request, feedback):
    feedback.status = Feedback.Status.PROCESSING
    feedback.save(update_fields=['status', 'updated_time'])
    notify_success(request, _('已重新打开，状态改为「待处理」'))
    return _back(request, '/console/feedback/')


def _act_delete(request, feedback):
    feedback.delete()      # 回复 / 附件 / 审核留痕随外键级联删除
    notify_success(request, _('该反馈及其回复已删除'))
    return redirect('/console/feedback/')


_REPLY_ACTIONS = {'reply': _act_reply, 'review_reply': _act_review_reply}
_FEEDBACK_ACTIONS = {
    'resubmit': _act_resubmit,
    'toggle_public': _act_toggle_public,
    'close': _act_close,
    'reopen': _act_reopen,
    'delete': _act_delete,
}
ACTIONS = frozenset(_REPLY_ACTIONS) | frozenset(_FEEDBACK_ACTIONS)


def _handle_feedback_action(request):
    action = (request.POST.get('action') or '').strip()
    if action not in ACTIONS:
        messages.error(request, _('不支持的操作'))
        return _back(request, '/console/feedback/')

    feedback = _feedback_or_404(request.POST.get('id'))
    if feedback is None:
        if action in _REPLY_ACTIONS:
            return _json(StatusCode.NOT_FOUND, _('反馈不存在'))
        messages.error(request, _('反馈不存在'))
        return _back(request, '/console/feedback/')

    if action in _REPLY_ACTIONS:
        return _REPLY_ACTIONS[action](request, feedback)
    return _FEEDBACK_ACTIONS[action](request, feedback)


# ==================== 反馈中心设置 ====================

@superadmin_required
def feedback_settings_view(request):
    """设置页（开关与规则、AI 审核与提示词、附件上限、反馈类型）"""
    if request.method == 'POST':
        return _handle_setting_action(request)

    return render(request, 'console/feedback_settings.html', {
        'setting': FeedbackSetting.get_solo(),
        'models': AiModel.objects.filter(enabled=True),
        'types': FeedbackType.objects.all(),
        'actions': SETTING_ACTIONS,
    })


@superadmin_required
def contacts_view(request):
    """开发者联系方式：联系方式平台字典 + 各项目联系方式（见模块 docstring 的拆分说明）"""
    if request.method == 'POST':
        return _handle_contact_action(request)

    contact_app_id = (request.GET.get('capp') or '').strip()
    contact_app = UserApp.objects.filter(app_id=contact_app_id).first() if contact_app_id else None
    if contact_app is None:
        contact_app = UserApp.objects.first()

    values = {}
    if contact_app is not None:
        values = {row.platform_id: row.value
                  for row in ProjectContact.objects.filter(app=contact_app)}

    platforms = list(ContactPlatform.objects.all())
    return render(request, 'console/contacts.html', {
        'platforms': platforms,
        'apps': UserApp.objects.all(),
        'contact_app': contact_app,
        # 模板里按键取值不便，直接给出「平台 + 当前值」的行列表
        'contact_rows': [(p, values.get(p.pk, '')) for p in platforms],
        'actions': CONTACT_ACTIONS,
    })


# ==================== 设置 · 动作 ====================

def _act_save_setting(request):
    """保存第 1~3 节：功能开关 / AI 审核与提示词 / 附件上限与限流"""
    setting = FeedbackSetting.get_solo()
    setting.enabled = request.POST.get('enabled') == '1'
    setting.ai_review_enabled = request.POST.get('ai_review_enabled') == '1'
    setting.ai_reject_image = request.POST.get('ai_reject_image') == '1'
    setting.captcha_required = request.POST.get('captcha_required') == '1'
    setting.email_notify = request.POST.get('email_notify') == '1'
    setting.submit_prompt = (request.POST.get('submit_prompt') or '').strip()
    setting.reply_prompt = (request.POST.get('reply_prompt') or '').strip()

    model_id = _int_or(request.POST.get('review_model'), 0)
    setting.review_model = AiModel.objects.filter(pk=model_id).first() if model_id else None

    numbers = (
        ('max_images', _('图片张数上限'), 0, 20),
        ('max_videos', _('视频个数上限'), 0, 10),
        ('max_image_mb', _('单张图片大小上限'), 1, 100),
        ('max_video_mb', _('单个视频大小上限'), 1, 500),
        ('rate_limit_hour', _('同 IP 每小时上限'), 0, 1000),
        ('rate_limit_day', _('同 IP 每天上限'), 0, 10000),
    )
    for field, label, low, high in numbers:
        raw = (request.POST.get(field) or '').strip()
        if not raw.isdigit() or not low <= int(raw) <= high:
            messages.error(request, _('%(label)s需为 %(low)s ~ %(high)s 的整数')
                           % {'label': label, 'low': low, 'high': high})
            return redirect('website:console_feedback_settings')
        setattr(setting, field, int(raw))

    setting.save()
    notify_success(request, _('反馈中心设置已保存'))
    return redirect('website:console_feedback_settings')


def _type_form(request, feedback_type=None):
    """读取并校验反馈类型表单，返回 (data, error)"""
    code = (request.POST.get('code') or '').strip().lower()
    name = (request.POST.get('name') or '').strip()
    if not name:
        return None, _('请填写类型名称')
    if not code or len(code) > MAX_CODE_LEN or not code.isascii() or not code.replace('-', '').isalnum():
        return None, _('类型标识只能是小写字母、数字与短横线，且不超过 30 个字符')
    duplicated = FeedbackType.objects.filter(code=code)
    if feedback_type is not None:
        duplicated = duplicated.exclude(pk=feedback_type.pk)
    if duplicated.exists():
        return None, _('该类型标识已存在')
    return {
        'code': code,
        'name': name[:MAX_NAME_LEN],
        'desc': (request.POST.get('desc') or '').strip()[:100],
        'icon': (request.POST.get('icon') or '').strip()[:MAX_NAME_LEN],
        'sort': _int_or(request.POST.get('sort'), 0),
        'enabled': request.POST.get('enabled') == '1',
        'is_default': request.POST.get('is_default') == '1',
        'remark': (request.POST.get('remark') or '').strip()[:255],
    }, None


def _apply_type(data, feedback_type):
    if data['is_default']:
        FeedbackType.objects.filter(is_default=True).exclude(pk=feedback_type.pk).update(
            is_default=False)
    for field, value in data.items():
        setattr(feedback_type, field, value)


def _act_type_create(request):
    data, error = _type_form(request)
    if error:
        messages.error(request, error)
        return redirect('website:console_feedback_settings')
    feedback_type = FeedbackType()
    _apply_type(data, feedback_type)
    feedback_type.save()
    notify_success(request, _('反馈类型「%(name)s」已创建') % {'name': feedback_type.name})
    return redirect('website:console_feedback_settings')


def _act_type_edit(request, feedback_type):
    data, error = _type_form(request, feedback_type)
    if error:
        messages.error(request, error)
        return redirect('website:console_feedback_settings')
    _apply_type(data, feedback_type)
    feedback_type.save()
    notify_success(request, _('反馈类型「%(name)s」已保存') % {'name': feedback_type.name})
    return redirect('website:console_feedback_settings')


def _act_type_toggle(request, feedback_type):
    feedback_type.enabled = not feedback_type.enabled
    feedback_type.save(update_fields=['enabled', 'updated_time'])
    notify_success(request, _('反馈类型「%(name)s」已启用') % {'name': feedback_type.name}
                     if feedback_type.enabled
                     else _('反馈类型「%(name)s」已停用，提交页不再出现') % {'name': feedback_type.name})
    return redirect('website:console_feedback_settings')


def _act_type_delete(request, feedback_type):
    name = feedback_type.name
    feedback_type.delete()      # 历史反馈的类型外键置空 → 展示为「未分类」
    notify_success(request, _('反馈类型「%(name)s」已删除，历史反馈显示为「未分类」') % {'name': name})
    return redirect('website:console_feedback_settings')


def _platform_form(request, platform=None):
    """读取并校验联系方式平台表单，返回 (data, error)"""
    code = (request.POST.get('code') or '').strip().lower()
    name = (request.POST.get('name') or '').strip()
    url_template = (request.POST.get('url_template') or '').strip()
    if not name:
        return None, _('请填写平台名称')
    if not code or len(code) > MAX_CODE_LEN or not code.isascii() or not code.replace('-', '').isalnum():
        return None, _('平台标识只能是小写字母、数字与短横线，且不超过 30 个字符')
    if len(url_template) > MAX_URL_TEMPLATE_LEN:
        return None, _('跳转链接模板不超过 200 个字符')
    if url_template and not url_template.startswith(('http://', 'https://', 'mailto:', 'tel:')):
        return None, _('跳转链接模板必须以 http://、https://、mailto: 或 tel: 开头')
    duplicated = ContactPlatform.objects.filter(code=code)
    if platform is not None:
        duplicated = duplicated.exclude(pk=platform.pk)
    if duplicated.exists():
        return None, _('该平台标识已存在')
    return {
        'code': code,
        'name': name[:MAX_NAME_LEN],
        'icon': (request.POST.get('icon') or '').strip()[:MAX_NAME_LEN],
        'value_label': (request.POST.get('value_label') or '').strip()[:MAX_NAME_LEN],
        'url_template': url_template,
        'sort': _int_or(request.POST.get('sort'), 0),
        'enabled': request.POST.get('enabled') == '1',
        'remark': (request.POST.get('remark') or '').strip()[:255],
    }, None


def _act_platform_create(request):
    data, error = _platform_form(request)
    if error:
        messages.error(request, error)
        return redirect('website:console_contacts')
    platform = ContactPlatform(**data)
    platform.save()
    notify_success(request, _('联系方式平台「%(name)s」已创建') % {'name': platform.name})
    return redirect('website:console_contacts')


def _act_platform_edit(request, platform):
    data, error = _platform_form(request, platform)
    if error:
        messages.error(request, error)
        return redirect('website:console_contacts')
    for field, value in data.items():
        setattr(platform, field, value)
    platform.save()
    notify_success(request, _('联系方式平台「%(name)s」已保存') % {'name': platform.name})
    return redirect('website:console_contacts')


def _act_platform_toggle(request, platform):
    platform.enabled = not platform.enabled
    platform.save(update_fields=['enabled', 'updated_time'])
    notify_success(request, _('联系方式平台「%(name)s」已启用') % {'name': platform.name}
                     if platform.enabled
                     else _('联系方式平台「%(name)s」已停用，各项目前台不再展示') % {'name': platform.name})
    return redirect('website:console_contacts')


def _act_platform_delete(request, platform):
    name = platform.name
    if ProjectContact.objects.filter(platform=platform).exists():
        messages.error(request, _('平台「%(name)s」下还有项目已填联系方式，请先清空再删除') % {'name': name})
        return redirect('website:console_contacts')
    platform.delete()
    notify_success(request, _('联系方式平台「%(name)s」已删除') % {'name': name})
    return redirect('website:console_contacts')


def _act_contact_save(request):
    """保存某个项目在各平台上的联系方式（空值 = 清掉该平台的绑定）"""
    app = UserApp.objects.filter(app_id=(request.POST.get('app_id') or '').strip()).first()
    if app is None:
        messages.error(request, _('接入项目不存在'))
        return redirect('website:console_contacts')

    saved = cleared = 0
    for platform in ContactPlatform.objects.all():
        value = (request.POST.get(f'contact_{platform.pk}') or '').strip()
        if len(value) > MAX_CONTACT_VALUE_LEN:
            messages.error(request, _('「%(name)s」的联系方式过长（最多 %(n)d 个字符）')
                           % {'name': platform.name, 'n': MAX_CONTACT_VALUE_LEN})
            return redirect(f'/console/contacts/?capp={app.app_id}')
        if not value:
            cleared += ProjectContact.objects.filter(app=app, platform=platform).delete()[0]
            continue
        ProjectContact.objects.update_or_create(
            app=app, platform=platform, defaults={'value': value})
        saved += 1

    notify_success(request, _('「%(name)s」的联系方式已保存（%(saved)d 项）')
                     % {'name': app.name, 'saved': saved}
                     if not cleared else
                     _('「%(name)s」的联系方式已保存（%(saved)d 项，清空 %(cleared)d 项）')
                     % {'name': app.name, 'saved': saved, 'cleared': cleared})
    return redirect(f'/console/contacts/?capp={app.app_id}')


# 设置页动作：只含开关与规则、反馈类型
_SETTING_ACTIONS = {
    'save_setting': _act_save_setting,
    'type_create': _act_type_create,
}
_TYPE_ACTIONS = {
    'type_edit': _act_type_edit,
    'type_toggle': _act_type_toggle,
    'type_delete': _act_type_delete,
}
SETTING_ACTIONS = frozenset(_SETTING_ACTIONS) | frozenset(_TYPE_ACTIONS)

# 开发者联系方式页动作：平台字典 + 各项目联系方式
_PLATFORM_ACTIONS = {
    'platform_edit': _act_platform_edit,
    'platform_toggle': _act_platform_toggle,
    'platform_delete': _act_platform_delete,
}
CONTACT_ACTIONS = frozenset(_PLATFORM_ACTIONS) | {'platform_create', 'contact_save'}


def _handle_setting_action(request):
    """反馈中心设置页的动作分发"""
    action = (request.POST.get('action') or '').strip()
    back = redirect('website:console_feedback_settings')

    if action in _SETTING_ACTIONS:
        return _SETTING_ACTIONS[action](request)

    if action in _TYPE_ACTIONS:
        feedback_type = FeedbackType.objects.filter(
            pk=_int_or(request.POST.get('id'), 0)).first()
        if feedback_type is None:
            messages.error(request, _('反馈类型不存在'))
            return back
        return _TYPE_ACTIONS[action](request, feedback_type)

    messages.error(request, _('不支持的操作'))
    return back


def _handle_contact_action(request):
    """开发者联系方式页的动作分发（平台字典 + 各项目联系方式）"""
    action = (request.POST.get('action') or '').strip()
    back = redirect('website:console_contacts')

    if action == 'contact_save':
        return _act_contact_save(request)

    if action == 'platform_create':      # 新增无需先取实例
        return _act_platform_create(request)

    if action in _PLATFORM_ACTIONS:
        platform = ContactPlatform.objects.filter(
            pk=_int_or(request.POST.get('id'), 0)).first()
        if platform is None:
            messages.error(request, _('联系方式平台不存在'))
            return back
        return _PLATFORM_ACTIONS[action](request, platform)

    messages.error(request, _('不支持的操作'))
    return back

