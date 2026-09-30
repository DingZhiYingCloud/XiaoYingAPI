"""问题反馈中心 · 对外反馈页（我们托管，子项目零代码接入）

子项目只需在页面上放一个指向 `/feedback/<app_id>/` 的链接或 iframe：

- **已登录用户**：子项目前端先用用户的 UAC Token 调 `POST /api/feedback/ticket`
  换一张一次性票据，再把票据拼进反馈页地址（`?ticket=xxx`）；本模块消费票据后
  建立「反馈页会话」，并把地址 303 重定向到不带票据的干净地址
  （票据 5 分钟过期、只能用一次，Token 因此不会落在 URL / 浏览器历史 / 访问日志里）。
- **游客**：直接打开即可提交；受图形验证码与同 IP 频率限制约束，且不支持跟帖。

四个页面：

    /feedback/<app_id>/                 提交反馈（含开发者联系方式）
    /feedback/<app_id>/public/          公开区（游客提交且过审的反馈，可关键词搜索）
    /feedback/<app_id>/my/              我的反馈（登录用户）
    /feedback/<app_id>/detail/<id>/     详情（正文 / 附件 / 回复，登录用户本人可跟帖）

另有一条 **本站自用入口** `/feedback/`（`feedback_self`）：官网自己也是一个接入项目
（`settings.WEB_APP_NAME`，见 `views._web_app`），但模板里不该硬编码 APPID，
故用它做一次重定向；查询只发生在点击时，不在每次页面渲染时。

提交与跟帖一律走普通表单 POST（带附件必须 multipart），成功后重定向，
避免刷新导致重复提交。

**官网登录态直通**：官网与反馈页在同一个域名下、共用同一个 Django 会话，
用户中心的登录态就存在 `session['website_user']`。因此 `_current_user` 在「票据会话」
之外额外认这份身份 —— 小影API 本站用户进反馈页无需再换一次性票据
（票据那套是给第三方域名 / iframe 场景准备的）。
"""
import logging
from datetime import timedelta

from django.contrib import messages
from django.core.paginator import Paginator
from django.http import Http404, HttpResponseRedirect
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _

from API.apis.captcha_self import utils as captcha_utils
from API.apis.feedback.ai import resolve_review_target
from API.apis.feedback.utils import client_ip, save_attachments, serialize_contacts
from API.models import (Feedback, FeedbackAttachment, FeedbackReply, FeedbackSetting,
                        FeedbackTicket, FeedbackType, User, UserApp)

logger = logging.getLogger('api.feedback')

# 反馈页会话：{app_id: {user_id, account, username}}，按项目分别记录（同一用户可接入多个项目）
SESSION_KEY = 'feedback_session'

# 官网登录态在会话里的 key（与 API/website/views.py 的 _SESSION_USER_KEY 一致）
WEBSITE_SESSION_KEY = 'website_user'

# 列表每页条数
PAGE_SIZE = 20

# 单条正文长度上限（提交与跟帖共用）
MAX_CONTENT_LEN = 5000

# 允许用户继续追问的业务状态：待审核期间也允许补充信息，
# 只有 AI 驳回 / 已关闭 这类终态才关掉入口。
_REPLYABLE_STATUSES = (Feedback.Status.PENDING, Feedback.Status.PROCESSING, Feedback.Status.REPLIED)


# ==================== 通用工具 ====================

def _get_app(app_id):
    """按 APPID 取启用中的接入项目（不存在返回 None，由调用方转 404）"""
    return UserApp.objects.filter(app_id=(app_id or '').strip(), status=True).first()


def _see_other(url):
    """303 重定向：明确让浏览器改用 GET 访问目标地址

    票据消费后必须重定向（地址上不能留票据），用 303 而不是 302：
    万一票据出现在 POST 请求里，302 会让浏览器按原方法重发，303 则统一降级为 GET。
    """
    response = HttpResponseRedirect(url)
    response.status_code = 303
    return response


def _session_map(request):
    return request.session.get(SESSION_KEY) or {}


def _current_user(request, app):
    """反馈页当前登录用户；游客（无票据 / 用户已失效）返回 None

    身份有两个来源，票据优先：

    1. `session['feedback_session'][app_id]` —— 子项目用 UAC Token 换票据建立的反馈页会话；
    2. `session['website_user']` —— **官网自己的登录态**（同一域名同一会话），
       让本站用户直接以登录身份使用反馈页，不必再走一次票据换取。

    兜底对**任意项目的反馈页**都生效：官网会话里的 `user_id` 就是用户中心的用户，
    与子项目票据换取的是同一个身份，因此不存在越权（取用户时仍校验 `status=True`）。

    票据签发时已校验过用户有效，但票据到消费之间用户可能被删或封禁，
    故取用户时再查一次（查不到即按游客处理，不让提交因外键失败而 500）。
    """
    info = _session_map(request).get(app.app_id) or {}
    user_id = info.get('user_id') or (request.session.get(WEBSITE_SESSION_KEY) or {}).get('user_id')
    if not user_id:
        return None
    return User.objects.filter(pk=user_id, status=True).first()


def _bind_user(request, app, user):
    """把票据对应的用户写进反馈页会话"""
    session = _session_map(request)
    session[app.app_id] = {
        'user_id': str(user.pk),
        'account': user.account or '',
        'username': user.username or '',
    }
    request.session[SESSION_KEY] = session
    request.session.modified = True


def _consume_ticket(request, app):
    """消费地址上的 `?ticket=xxx`，成功则建立反馈页会话

    :return: True 表示消费了一张有效票据（调用方应重定向到干净地址）
    """
    token = (request.GET.get('ticket') or '').strip()
    if not token:
        return False

    ticket = FeedbackTicket.objects.select_related('user').filter(token=token).first()
    if ticket is None or ticket.app_id != app.pk:
        logger.info('反馈页票据无效: app=%s token=%s…', app.app_id, token[:8])
        return False
    # consume() 内部用条件更新同时完成「未使用 + 未过期」判定与标记，
    # 并发下同一张票据只有一个请求能抢到（见 FeedbackTicket.consume）
    if not ticket.consume():
        logger.info('反馈页票据已被使用或已过期: app=%s token=%s…', app.app_id, token[:8])
        return False

    _bind_user(request, app, ticket.user)
    return True


# ==================== 游客防刷 ====================

def _rate_limited(ip, setting):
    """同一 IP 的提交频率是否超限（小时 / 天两档，均针对游客）"""
    if not ip:
        return False
    now = timezone.now()
    recent = Feedback.objects.filter(ip=ip, create_time__gte=now - timedelta(days=1))
    if setting.rate_limit_day and recent.count() >= setting.rate_limit_day:
        return True
    if setting.rate_limit_hour:
        hour_ago = now - timedelta(hours=1)
        if recent.filter(create_time__gte=hour_ago).count() >= setting.rate_limit_hour:
            return True
    return False


# ==================== 本站自用入口 ====================

def feedback_self(request):
    """`/feedback/` → 官网自己那条反馈页 `/feedback/<APPID>/`

    官网自身就是一个接入项目，APPID 由 `views._web_app()` 惰性维护
    （名称取 `settings.WEB_APP_NAME`），不在模板 / 配置里重复声明。
    """
    from .views import _web_app     # 局部导入：官网接入项目的唯一来源就在这里
    return redirect('website:feedback', app_id=_web_app().app_id)


# ==================== 提交页 ====================

def _submit_context(request, app, setting, form=None):
    user = _current_user(request, app)
    return {
        'fb_app': app,
        'fb_tab': 'submit',
        'fb_setting': setting,
        'contacts': serialize_contacts(app),
        'types': FeedbackType.objects.filter(enabled=True),
        'form': form or {},
        'fb_user': user,
        # 游客才需要图形验证；登录用户身份可追溯，不受验证码约束
        'captcha_required': setting.captcha_required and user is None,
    }


def feedback_home(request, app_id):
    """提交页（同时是票据消费入口）"""
    app = _get_app(app_id)
    if app is None:
        raise Http404('接入项目不存在或已停用')

    if _consume_ticket(request, app):
        return _see_other(reverse('website:feedback', args=[app.app_id]))

    setting = FeedbackSetting.get_solo()
    if not setting.enabled:
        return render(request, 'feedback/submit.html',
                      {'fb_app': app, 'fb_tab': 'submit', 'closed': True})

    if request.method == 'POST':
        return _handle_submit(request, app, setting)
    return render(request, 'feedback/submit.html', _submit_context(request, app, setting))


def _handle_submit(request, app, setting):
    """处理提交：校验 → 落附件 → 建反馈"""
    errors = []
    content = (request.POST.get('content') or '').strip()
    type_id = (request.POST.get('type_id') or '').strip()
    contact_email = (request.POST.get('contact_email') or '').strip()
    form = {'type_id': type_id, 'content': content, 'contact_email': contact_email}

    if not content:
        errors.append(_('请填写反馈内容'))
    elif len(content) > MAX_CONTENT_LEN:
        errors.append(_('反馈内容过长（最多 %d 字）') % MAX_CONTENT_LEN)

    feedback_type = None
    if type_id.isdigit():
        feedback_type = FeedbackType.objects.filter(pk=int(type_id), enabled=True).first()
    if feedback_type is None:
        errors.append(_('请选择反馈类型'))

    user = _current_user(request, app)
    ip = client_ip(request)

    if user is None:
        # 游客：图形验证码（服务端二次校验，与官网其它表单同一口径）
        if setting.captcha_required:
            ok, err = captcha_utils.verify_challenge(
                request.POST.get('captcha_id'), request.POST.get('answer'))
            if not ok:
                errors.append(_('图形验证未通过：%s') % err)
        if _rate_limited(ip, setting):
            errors.append(_('提交过于频繁，请稍后再试'))

    attachments = []
    if not errors:
        for kind, field, max_count, max_mb in (
            (FeedbackAttachment.Kind.IMAGE, 'images', setting.max_images, setting.max_image_mb),
            (FeedbackAttachment.Kind.VIDEO, 'videos', setting.max_videos, setting.max_video_mb),
        ):
            saved, upload_errors = save_attachments(
                request.FILES.getlist(field), kind, max_count, max_mb)
            attachments += saved
            errors += upload_errors

    if errors:
        for err in errors:
            messages.error(request, err)
        return render(request, 'feedback/submit.html', _submit_context(request, app, setting, form))

    # 开启 AI 审核且平台确有可用模型 → 先入「待审核」，由后台审核线程逐条慢慢审；
    # 否则直接进「待处理」（与 Feedback 模型文档的状态联动口径一致）
    target, _reason = resolve_review_target(setting)
    need_ai = target is not None

    feedback = Feedback.objects.create(
        app=app, type=feedback_type, user=user,
        contact_email=contact_email, content=content,
        status=Feedback.Status.PENDING if need_ai else Feedback.Status.PROCESSING,
        ai_status=Feedback.AiStatus.PENDING if need_ai else Feedback.AiStatus.SKIPPED,
        ip=ip, user_agent=(request.META.get('HTTP_USER_AGENT') or '')[:255],
    )
    for index, item in enumerate(attachments):
        FeedbackAttachment.objects.create(feedback=feedback, sort=index, **item)

    messages.success(request, _('反馈已提交，正在等待审核') if need_ai
                     else _('反馈已提交，我们会尽快处理'))
    if user is not None:
        return redirect('website:feedback_detail', app_id=app.app_id, feedback_id=feedback.pk)
    return redirect('website:feedback', app_id=app.app_id)


# ==================== 公开区 / 我的反馈 ====================

def feedback_public(request, app_id):
    """公开区：游客提交且已过 AI 审核的反馈，支持关键词搜索"""
    app = _get_app(app_id)
    if app is None:
        raise Http404('接入项目不存在或已停用')

    keyword = (request.GET.get('q') or '').strip()
    queryset = Feedback.public_queryset().filter(app=app).order_by('-create_time')
    if keyword:
        queryset = queryset.filter(content__icontains=keyword)

    return render(request, 'feedback/public.html', {
        'fb_app': app,
        'fb_tab': 'public',
        'contacts': serialize_contacts(app),
        'page_obj': Paginator(queryset, PAGE_SIZE).get_page(request.GET.get('page')),
        'keyword': keyword,
    })


def feedback_mine(request, app_id):
    """我的反馈：登录用户在**本项目**下提交过的全部反馈"""
    app = _get_app(app_id)
    if app is None:
        raise Http404('接入项目不存在或已停用')

    user = _current_user(request, app)
    if user is None:
        messages.info(request, _('登录后即可查看你提交的反馈'))
        return redirect('website:feedback', app_id=app.app_id)

    queryset = Feedback.objects.filter(app=app, user=user).order_by('-create_time')
    return render(request, 'feedback/mine.html', {
        'fb_app': app,
        'fb_tab': 'mine',
        'contacts': serialize_contacts(app),
        'fb_user': user,
        'page_obj': Paginator(queryset, PAGE_SIZE).get_page(request.GET.get('page')),
    })


# ==================== 详情 / 跟帖 ====================

def feedback_detail(request, app_id, feedback_id):
    """反馈详情：正文 + 附件 + 全部回复；登录用户本人可跟帖

    可见性：本人提交的（登录态）或已进公开区的（游客 + 过审 + 未隐藏）可看；
    其余一律 404（不泄露「存在这样一条反馈」的信息）。
    附件只对本人展示——公开区口径是「不展示任何附件」。
    """
    app = _get_app(app_id)
    if app is None:
        raise Http404('接入项目不存在或已停用')

    feedback = (Feedback.objects
                .select_related('type', 'user')
                .filter(pk=feedback_id, app=app).first())
    if feedback is None:
        raise Http404('反馈不存在')

    user = _current_user(request, app)
    is_owner = user is not None and feedback.user_id == user.pk
    if not is_owner and not feedback.in_public_area:
        raise Http404('反馈不存在')

    if request.method == 'POST':
        return _handle_followup(request, feedback, is_owner)

    return render(request, 'feedback/detail.html', {
        'fb_app': app,
        'fb_tab': 'mine' if is_owner else 'public',
        'contacts': serialize_contacts(app),
        'fb': feedback,
        'replies': feedback.replies.select_related('user').prefetch_related('attachments'),
        'is_owner': is_owner,
        'can_reply': is_owner and feedback.status in _REPLYABLE_STATUSES,
        'show_attachments': is_owner,
    })


def _handle_followup(request, feedback, is_owner):
    """用户跟帖（仅本人提交的反馈；AI 驳回 / 已关闭 的终态不允许再追问）"""
    if not is_owner:
        raise Http404('反馈不存在')

    back = redirect('website:feedback_detail',
                    app_id=feedback.app.app_id, feedback_id=feedback.pk)
    if feedback.status not in _REPLYABLE_STATUSES:
        messages.error(request, _('当前状态不支持继续追问'))
        return back

    content = (request.POST.get('content') or '').strip()
    if not content:
        messages.error(request, _('请填写内容'))
        return back
    if len(content) > MAX_CONTENT_LEN:
        messages.error(request, _('内容过长（最多 %d 字）') % MAX_CONTENT_LEN)
        return back

    FeedbackReply.objects.create(
        feedback=feedback, author_role=FeedbackReply.AuthorRole.USER,
        user_id=feedback.user_id, content=content,
    )
    feedback.admin_unread = True
    feedback.last_reply_time = timezone.now()
    update_fields = ['admin_unread', 'last_reply_time', 'updated_time']
    if feedback.status == Feedback.Status.REPLIED:
        # 已回复后用户又追问：回到「待处理」，让后台重新看到这条需要回应
        feedback.status = Feedback.Status.PROCESSING
        update_fields.append('status')
    feedback.save(update_fields=update_fields)

    messages.success(request, _('已提交，请等待管理员回复'))
    return back
