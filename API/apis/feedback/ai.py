"""问题反馈中心 · AI 审核引擎

两个场景，两套提示词（都在后台「反馈中心设置」里维护）：

    submit —— 用户提交的反馈**内容审核**。异步：提交先入库为「待审核」，由后台审核线程
              逐条慢慢审（一次一条、每条之间歇一会，不抢占资源）；管理员也可对单条
              「立即送审」插队。
    reply  —— 管理员**回复的语气审查**。同步：后台点「发送」时即时给意见。
              AI 只提醒、不阻断，管理员可以坚持发送（强制发送会留痕）。

**规则就是提示词**：判定完全交给 AI（需求确认：后台写的规则以提示词形式一起发给 AI，
即便触发了规则表述，最终也以 AI 的处理结果为准）。因此这里**不做任何关键词 / 正则硬规则**，
只把「提示词 + 反馈正文 + 用户信息」一起发过去，要求 AI 返回结构化结论。
提交审核时若该反馈带了图片 / 视频，且**审核模型勾了对应的多模态能力**，还会一并把附件内容
发给模型 —— 让 AI 能连附件一起判断，而不仅看文字（见 `_review_media`；附件从本地读出后内联，
不依赖站点公网地址）。

AI 不可用的情形一律「跳过审核」而不是「卡住」：

    - 后台关闭了 AI 审核开关                      → 直接进入「待处理」
    - 平台没配置可用模型 / 没配 Key                → 直接进入「待处理」
    - 模型调用失败（网络 / 额度 / 返回不是 JSON）   → 记为「审核失败」，条目留在「待审核」，
                                                    管理员可手动重审
"""
import base64
import io
import json
import logging
import os
import sys
import threading
import time

from datetime import timedelta

from django.conf import settings
from django.db import close_old_connections
from django.db.models import Q
from django.utils import timezone

from API.apis.ai.BuiltInModel import utils as ai_utils
from API.models import (
    AI_RUNNING_STALE_MINUTES,
    AiModel,
    Feedback,
    FeedbackAuditLog,
    FeedbackReply,
    FeedbackReplyAttachment,
    FeedbackSetting,
)

from .image import render_reject_card

logger = logging.getLogger('api.feedback')

# 送审正文的截断长度：太长的反馈截断即可，审核只看是否违规
REVIEW_INPUT_MAX_LEN = 4000

# 审核线程节奏（秒）：有空闲就不急着轮询，有活干时快一点
WORKER_IDLE_INTERVAL = 8
WORKER_BUSY_INTERVAL = 2

# 驳回理由要点最多渲染几条
MAX_REJECT_POINTS = 4

DEFAULT_SUBMIT_PROMPT = """你是「问题反馈中心」的内容审核员，负责判断用户提交的反馈是否适合进入平台处理流程。

应当判定为「驳回」的情形：
1. 主要内容不是中文（英文或其它外语），无法确认诉求；
2. 语气恶劣：辱骂、人身攻击、歧视、威胁、恶意嘲讽；
3. 广告或引流：推广、拉群、二维码、与产品无关的营销内容；
4. 违法违规：色情、暴力、赌博、政治敏感等；
5. 无意义内容：纯符号、刷屏、与产品或技术完全无关。

如果本次一并提供了用户上传的图片或视频，必须**逐张看完再下结论**（看过才判，不许只看文字就放过）。
画面或声音里出现下面任何一类，一律判定为「驳回」，并在 reason 与 points 里点明是附件的问题：

1. 色情低俗：裸露、性暗示，泳装 / 内衣 / 情趣服饰的贴身特写，私密部位，床上场景，色情文字或水印；
2. 暴力血腥：打斗、伤口、血迹、尸体、虐待动物、自残，以及刀枪棍棒等器械的威胁性展示；
3. 恐怖惊悚：鬼怪、惊悚妆容、恐怖画面、灵异或尸骸场景；
4. 违法违规：毒品、赌博、诈骗二维码、他人隐私信息（身份证、手机号、聊天记录等截图）；
5. 与反馈无关：附件与本次反馈的问题看不出任何关系（纯自拍、风景、表情包、无关截图等）。

附件判定从严：只要**有合理理由怀疑**属于上述任一类就判驳回，宁可驳回也不要放过。
反过来，与问题相关的正常素材应当通过，例如报错截图、界面截图、作品效果图、证件之外的商品图。

以下情形应当「通过」，不要因为这些驳回：
- 描述不清、信息不全、情绪激动但仍在讨论问题；
- 对产品提出批评、抱怨、要求退款或索赔；
- 提出的功能建议看起来不现实。

只输出一个 JSON 对象，不要输出任何其它文字：
{"verdict": "pass" 或 "reject", "reason": "一句话结论，驳回时必填且不超过 20 字", "points": ["驳回理由要点，每条不超过 20 字，最多 4 条"]}
判定为 pass 时 reason 与 points 可以是空字符串与空数组。"""

DEFAULT_REPLY_PROMPT = """你是「问题反馈中心」的回复审查员，负责在管理员发送回复前提醒其中不合适的表达。

应当判定为「提醒」的情形：
1. 语气强硬、嘲讽、指责用户；
2. 明显的不耐烦、敷衍、甩锅；
3. 泄露内部信息（密钥、服务器地址、其它用户信息）；
4. 与用户问题无关的内容。

你只负责提醒、不负责阻断——管理员有最终决定权。

只输出一个 JSON 对象，不要输出任何其它文字：
{"verdict": "pass" 或 "warn", "reason": "一句话提醒，warn 时必填且不超过 40 字"}"""


# ==================== 提示词 / 模型解析 ====================
def resolve_review_target(setting):
    """解析本次审核要用的模型

    优先后台指定的「审核专用模型」；它被停用 / 删除 / 未配 Key 时回落到平台默认模型。

    :return: (target, None) 或 (None, 不可用原因)
    """
    if not setting.ai_review_enabled:
        return None, '后台已关闭 AI 审核'

    model_key = None
    if setting.review_model_id:
        model_key = (AiModel.objects.filter(pk=setting.review_model_id)
                     .values_list('key', flat=True).first())

    target, error = ai_utils.resolve_target(model_key=model_key)
    if target is None and model_key:
        # 指定的审核模型已不可用：回落默认模型，避免整个审核能力被一条记录卡死
        logger.warning('审核模型 %s 不可用，回落默认模型：%s', model_key, error)
        target, error = ai_utils.resolve_target()
    if target is None:
        return None, (error[1] if error else '平台未配置可用的 AI 模型')
    return target, None


def review_prompt(setting, kind) -> str:
    """取对应场景的提示词（后台没填则用内置的通用规则）"""
    if kind == 'reply':
        return (setting.reply_prompt or '').strip() or DEFAULT_REPLY_PROMPT
    return (setting.submit_prompt or '').strip() or DEFAULT_SUBMIT_PROMPT


# ==================== 与 AI 交互 ====================
def _extract_json(text):
    """从模型回复里抠出第一个 JSON 对象（容忍 ```json 围栏与前后废话）"""
    raw = (text or '').strip()
    if not raw:
        return None
    raw = '\n'.join(line for line in raw.splitlines()
                    if not line.strip().startswith('```'))
    start, end = raw.find('{'), raw.rfind('}')
    if start < 0 or end <= start:
        return None
    try:
        data = json.loads(raw[start:end + 1])
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _normalize_verdict(data, reject_words, warn_words=()):
    """把模型给的 verdict 归一成 'pass' / 'reject' / 'warn'；识别不出来返回空串

    模型偶尔会返回中文或大小写混写，这里做一层容错，但**不猜**：
    完全识别不出时返回空串，由调用方按「审核失败」处理（宁可让管理员手动重审，
    也不要把一条内容按错误结论放行或驳回）。

    `warn_words` 必须先于 `reject_words` 判定：两个场景对同一个词的语义不同 ——
    提交审核里 `warn` 视同驳回，而回复审查里 `warn` 是「只提醒」（见 `review_reply_text`）。
    """
    value = str(data.get('verdict') or '').strip().lower()
    if not value:
        return ''
    if value in ('pass', 'ok', 'true', '通过', '允许') or 'pass' in value or '通过' in value:
        return 'pass'
    if any(word in value for word in warn_words):
        return 'warn'
    if any(word in value for word in reject_words) or value in ('false', '驳回', '拒绝'):
        return 'reject'
    return ''


# ==================== 送审媒体（图片 / 视频） ====================
MAX_INLINE_MEDIA_BYTES = 8 * 1024 * 1024
"""单个附件内联进请求体的体积上限（字节）

附件一律**从本地读出内容内联**（图片压成 JPEG、视频原样 base64），不依赖上游能否回访我们的
站点 —— 本地开发没有公网地址、线上媒体目录若未直服，走公网地址都会变成「审了个寂寞」。
超过这个体积的（大多是手机拍的视频，反馈页上限 50MB）不再内联：base64 会让请求体膨胀约 1/3，
上游会直接拒绝，此时回落到公网地址（见 `_media_absolute_url`）。
"""

REVIEW_IMAGE_MAX_EDGE = 1280
"""送审图片的长边上限（像素）：审核只需看清画面，不需要原图，压小能省流量与上游开销"""

REVIEW_IMAGE_QUALITY = 85
"""送审图片转 JPEG 的质量"""

_VIDEO_MIME = {
    'mp4': 'video/mp4', 'm4v': 'video/x-m4v', 'mov': 'video/quicktime',
    'webm': 'video/webm', 'avi': 'video/x-msvideo', 'mkv': 'video/x-matroska',
    'flv': 'video/x-flv', 'wmv': 'video/x-ms-wmv', '3gp': 'video/3gpp',
}
"""视频扩展名 → data URI 的 MIME（反馈页允许的上传格式，见 FileUploader.TYPE_CONFIG）"""


def _media_absolute_url(path) -> str:
    """把附件的相对路径拼成公网可访问的绝对地址（供上游模型抓取）

    站点地址来自 .env 的 `XYAPI_SITE_URL`（见 settings.SITE_URL）。未配置时返回空串 ——
    宁可少审一个超大的视频，也不要拼出一个上游抓不到的地址白等一轮超时。
    """
    base = (getattr(settings, 'SITE_URL', '') or '').strip().rstrip('/')
    if not base or not path:
        return ''
    return f'{base}{settings.MEDIA_URL}{path}'


def _read_attachment(att) -> str:
    """读一条附件并转成可内联的 data URI；读不出来或体积过大返回空串

    - 图片：先等比压到长边 `REVIEW_IMAGE_MAX_EDGE`、转 JPEG 再 base64
      （用户上传的图片上限 10MB，手机直出照片动辄数 MB，不压缩很可能超出上游对 base64 的限制；
      动态 GIF 只送出第一帧）；
    - 视频：不压缩，原样 base64（仅在不超过 `MAX_INLINE_MEDIA_BYTES` 时内联）。
    """
    abs_path = os.path.join(settings.MEDIA_ROOT, att.path)
    try:
        if att.is_image:
            from PIL import Image
            with Image.open(abs_path) as img:
                # 统一转 RGB：PNG / GIF 的调色板或透明通道无法直接存 JPEG
                img = img.convert('RGB')
                img.thumbnail((REVIEW_IMAGE_MAX_EDGE, REVIEW_IMAGE_MAX_EDGE))
                buf = io.BytesIO()
                img.save(buf, format='JPEG', quality=REVIEW_IMAGE_QUALITY)
            payload = buf.getvalue()
            return 'data:image/jpeg;base64,' + base64.b64encode(payload).decode('ascii')

        if os.path.getsize(abs_path) > MAX_INLINE_MEDIA_BYTES:
            return ''
        mime = _VIDEO_MIME.get((att.ext or '').lower(), 'video/mp4')
        with open(abs_path, 'rb') as f:
            payload = f.read()
        return f'data:{mime};base64,' + base64.b64encode(payload).decode('ascii')
    except Exception:
        logger.warning('反馈附件 %s 读取失败，本次送审跳过该附件', att.pk, exc_info=True)
        return ''


def _review_media(feedback, target):
    """挑出这次送审要一并带给模型的附件

    只带图片与视频（反馈中心不支持音频上传），且**按审核模型的能力与上限**过滤：
    模型没勾「支持视觉 / 支持视频理解」时就别带，否则上游会直接报参数非法。

    附件优先内联（见 `_read_attachment`）；过大 / 读不出来时才回落到公网地址。

    :return: (images, videos) —— 两个可直接放进 content 块的地址列表，可能为空
    """
    attachments = list(feedback.attachments.all())
    if not (target['supports_vision'] or target['supports_video']):
        if attachments:
            # 静默丢掉附件等于「带图 / 视频的反馈只审了文字」，色情图照样能过 —— 必须留痕
            logger.warning('反馈 %s 带 %d 个附件，但审核模型 %s 未勾选视觉 / 视频理解能力，'
                           '附件将不会被审核', feedback.pk, len(attachments), target['key'])
        return [], []

    images, videos = [], []
    for att in attachments:
        if att.is_image:
            if not target['supports_vision'] or len(images) >= target['max_images']:
                continue
        elif not target['supports_video'] or len(videos) >= target['max_videos']:
            continue

        url = _read_attachment(att)
        if not url:
            url = _media_absolute_url(att.path)
            if url:
                logger.info('反馈附件 %s 体积过大，回落公网地址送审', att.pk)
        if not url:
            logger.warning('反馈附件 %s 无法送审（未配置 XYAPI_SITE_URL 且体积超限），本次跳过', att.pk)
            continue

        (images if att.is_image else videos).append(url)
    return images, videos


def _call_ai(target, system_prompt, user_content, background=False, images=None, videos=None):
    """把「提示词 + 正文（+ 图片 / 视频附件）」发给 AI 并解析出结构化结论

    :param background: True=后台审核线程在调（保留重试与长假）；
        False=控制台在请求线程里同步调（只发一次、超时更短，避免占住 worker）。
        口径见 `API.apis.ai.BuiltInModel.utils.SYNC_MAX_ATTEMPTS`。
    :return: (True, dict) / (False, 错误文案)
    """
    try:
        messages = ai_utils.build_messages(
            user_content,
            system_prompt=json.dumps([{'role': 'system', 'content': system_prompt}],
                                     ensure_ascii=False),
            images=images, videos=videos,
        )
    except ValueError as exc:
        return False, f'构建审核请求失败: {exc}'

    # 采样参数沿用该模型在后台的配置（与对外对话接口同一口径，调用方不额外干预）
    ok, result = ai_utils.chat_completion(
        target, messages, background=background,
        temperature=target['temperature'], max_tokens=target['max_tokens'],
        stop=target['stop_list'],
    )
    if not ok:
        return False, f'调用审核模型失败: {result}'

    data = _extract_json(result.get('reply'))
    if data is None:
        return False, '审核模型没有返回合法的 JSON 结论'
    return True, data


# ==================== 送审内容组装 ====================
def _render_submit_input(feedback) -> str:
    """把反馈内容 + 用户信息组装成送审文本（需求要求「问题和用户信息一起发给 AI」）"""
    identity = '游客（匿名）' if feedback.is_guest else f'登录用户 {feedback.submitter_name}'
    return '\n'.join([
        f'【项目】{feedback.app.name}',
        f'【反馈类型】{feedback.type_name}',
        f'【提交者】{identity}',
        '【反馈内容】',
        feedback.content or '',
    ])[:REVIEW_INPUT_MAX_LEN]


def _render_reply_input(feedback, content) -> str:
    """组装管理员回复的审查文本（带上原反馈，便于判断回复是否切题）"""
    return '\n'.join([
        f'【项目】{feedback.app.name}',
        '【用户反馈原文】',
        (feedback.content or '')[:2000],
        '【待审查的管理员回复】',
        content or '',
    ])[:REVIEW_INPUT_MAX_LEN]


# ==================== 结果落地 ====================
def _apply_result(feedback, ai_status, status=None, target=None):
    """把审核结论写回反馈

    `status` 只在反馈仍是「待审核」时才改写 —— 审核期间管理员可能已经回复了，
    那种情况下不能把业务状态倒推回去。
    """
    feedback.refresh_from_db(fields=['status', 'ai_status'])
    feedback.ai_status = ai_status
    feedback.ai_checked_time = timezone.now()
    update_fields = ['ai_status', 'ai_checked_time', 'updated_time']
    if target is not None:
        feedback.ai_model_key = target['key']
        update_fields.append('ai_model_key')
    if status is not None and feedback.status == Feedback.Status.PENDING:
        feedback.status = status
        update_fields.append('status')
    feedback.save(update_fields=update_fields)


def _log(feedback, verdict, reason='', target=None, reply=None, forced=False, operator=''):
    """写一条审核留痕（AI 调用失败也留痕，便于排查）"""
    FeedbackAuditLog.objects.create(
        feedback=feedback, reply=reply, kind=FeedbackAuditLog.Kind.SUBMIT,
        verdict=verdict, reason=(reason or '')[:4000],
        model_key=(target['key'] if target else ''), forced=forced, operator=operator,
    )


def _skip(feedback, why):
    """跳过审核：直接进入「待处理」，让管理员正常处理"""
    _apply_result(feedback, Feedback.AiStatus.SKIPPED, Feedback.Status.PROCESSING)
    logger.info('反馈 %s 跳过 AI 审核：%s', feedback.pk, why)
    return True, f'已跳过审核（{why}）'


def _fail(feedback, message, target=None):
    """审核失败：状态留在「待审核」，后台可手动重审"""
    _apply_result(feedback, Feedback.AiStatus.FAILED, None, target)
    _log(feedback, FeedbackAuditLog.Verdict.ERROR, message, target)
    logger.warning('反馈 %s 审核失败：%s', feedback.pk, message)
    return False, message


def _reject_text(reason) -> str:
    """AI 驳回时落到回复里的正文（用户/管理员在详情页看到的就是这段）"""
    return ('本条反馈未通过 AI 内容审核，已被驳回。\n\n'
            f'驳回理由：{reason}\n\n'
            '如有疑问，可通过下方开发者联系方式沟通；请勿重复提交同类内容。')


def review_submission(feedback, background=False):
    """审核一条反馈的提交内容（审核线程与后台「立即送审」共用）

    :param background: 见 _call_ai —— 审核线程传 True（可重试），
        控制台「立即送审」保持默认（同步、不重试）
    :return: (ok, 说明文案)；ok 只表示流程跑完，不代表审核通过
    """
    setting = FeedbackSetting.get_solo()
    target, reason = resolve_review_target(setting)
    if target is None:
        return _skip(feedback, reason)

    images, videos = _review_media(feedback, target)
    ok, data = _call_ai(target, review_prompt(setting, 'submit'),
                        _render_submit_input(feedback), background=background,
                        images=images, videos=videos)
    if not ok:
        return _fail(feedback, data, target)

    verdict = _normalize_verdict(data, reject_words=('reject', 'warn', '驳回', '提醒', '拒绝'))
    if not verdict:
        return _fail(feedback, f'无法识别审核结论: {data}', target)

    conclusion = str(data.get('reason') or '').strip()
    if verdict == 'pass':
        _apply_result(feedback, Feedback.AiStatus.PASSED, Feedback.Status.PROCESSING, target)
        _log(feedback, FeedbackAuditLog.Verdict.PASS, conclusion, target)
        return True, '审核通过'

    points = [str(p).strip() for p in (data.get('points') or []) if str(p).strip()]
    points = points[:MAX_REJECT_POINTS]
    _apply_result(feedback, Feedback.AiStatus.REJECTED, Feedback.Status.REJECTED, target)
    _log(feedback, FeedbackAuditLog.Verdict.REJECT, conclusion or '内容不符合平台规范', target)

    reply = FeedbackReply.objects.create(
        feedback=feedback, author_role=FeedbackReply.AuthorRole.AI,
        content=_reject_text(conclusion or '内容不符合平台规范'),
    )
    if setting.ai_reject_image:
        _attach_reject_image(feedback, reply, conclusion, points)
    feedback.last_reply_time = timezone.now()
    feedback.save(update_fields=['last_reply_time', 'updated_time'])
    return True, '审核驳回'


def _attach_reject_image(feedback, reply, reason, points):
    """渲染并挂上「驳回说明图」（画图失败不影响驳回本身，只记日志）"""
    try:
        rel_path, size = render_reject_card(
            app_name=feedback.app.name,
            submitter=feedback.submitter_name,
            submit_time=timezone.localtime(feedback.create_time).strftime('%Y-%m-%d %H:%M'),
            reason=reason or '内容不符合平台规范',
            points=points,
        )
    except Exception:
        logger.exception('反馈 %s 渲染驳回说明图失败', feedback.pk)
        return
    FeedbackReplyAttachment.objects.create(
        reply=reply, kind=FeedbackReplyAttachment.Kind.IMAGE,
        path=rel_path, original_name='驳回说明.png', size=size, ext='png',
    )


def review_reply_text(feedback, content):
    """管理员回复的语气审查（**只在控制台同步调用**，故走同步口径：只发一次）

    :return: (True, {verdict, reason, model_key}) —— 审查跑完
             (False, 不可用/失败原因)          —— 调用方应当直接放行（AI 只提醒不阻断）
    """
    setting = FeedbackSetting.get_solo()
    target, reason = resolve_review_target(setting)
    if target is None:
        return False, reason

    ok, data = _call_ai(target, review_prompt(setting, 'reply'),
                        _render_reply_input(feedback, content))
    if not ok:
        return False, data

    verdict = _normalize_verdict(data, reject_words=(), warn_words=('warn', '提醒', 'reject', '驳回'))
    if not verdict:
        return False, f'无法识别审查结论: {data}'
    if verdict == 'reject':
        # 回复审查只有「通过 / 提醒」两种结论（提示词也只让模型回这两个）：
        # 模型若回 reject，按「提醒」处理 —— AI 只提醒、不阻断，由管理员决定是否强制发送
        verdict = 'warn'
    return True, {
        'verdict': verdict,
        'reason': str(data.get('reason') or '').strip(),
        'model_key': target['key'],
    }


# ==================== 后台审核线程 ====================
_WORKER_STARTED = False
_WORKER_LOCK = threading.Lock()


def is_serving_process() -> bool:
    """当前进程是否「对外提供服务」（决定要不要起审核线程）

    - `manage.py` 的其它命令（makemigrations / migrate / shell / test…）一律不起，
      否则跑一次迁移就多一个线程、还可能误消费待审数据
    - `runserver` 的自动重载会 fork 子进程：只有子进程（RUN_MAIN=true）起线程，
      避免父进程与子进程各起一份
    - **直接执行的 .py 脚本**（`scripts/*.py`、一次性运维脚本等）同样不起：它们只是
      跑一次就退出，起了线程反而会去消费待审数据、消耗 AI 额度，还会让回归脚本不确定
    - **测试 / REPL 入口**（pytest、`python -c` / `python -m`）也一样不起：它们会触发
      `apps.ready()`，而入口名不以 `.py` 结尾（原先会落到「视为服务进程」），起了线程
      就会去消费待审数据、发告警邮件，让测试结果变得不确定
    - 其余（uwsgi / gunicorn 等）视为服务进程；多 worker 时每个 worker 都有自己的线程，
      靠行级抢占保证同一条不会被审两次
    """
    argv = sys.argv or []
    entry = os.path.basename(argv[0]) if argv else ''
    if entry == 'manage.py':
        command = argv[1] if len(argv) > 1 else ''
        if command != 'runserver':
            return False
        if os.environ.get('RUN_MAIN') != 'true' and '--noreload' not in argv:
            return False
        return True
    if entry.startswith('pytest') or (len(argv) > 1 and argv[1] in ('-c', '-m')):
        return False
    if entry.endswith('.py'):
        return False
    return True


def start_review_worker():
    """启动后台审核线程（幂等；由 API/apps.py 在服务进程里调用一次）"""
    global _WORKER_STARTED
    with _WORKER_LOCK:
        if _WORKER_STARTED:
            return
        _WORKER_STARTED = True
    thread = threading.Thread(target=_worker_loop, name='feedback-ai-review', daemon=True)
    thread.start()
    logger.info('反馈中心 AI 审核线程已启动')


def _worker_loop():
    """审核线程主循环：一次一条、慢慢来（不占满资源）"""
    while True:
        worked = False
        try:
            close_old_connections()
            worked = review_one_pending()
        except Exception:
            logger.exception('反馈中心 AI 审核线程异常')
        time.sleep(WORKER_BUSY_INTERVAL if worked else WORKER_IDLE_INTERVAL)


def review_one_pending():
    """取一条「待审核」的反馈并审掉；返回是否真的处理了一条

    抢占用条件更新：多进程 / 多线程下只有一个能把状态改成「审核中」，抢不到的进程直接进入
    下一轮，不会重复调用 AI。可抢的条件与 `pending_ai_queryset()` 一致 ——
    「待审核」或「审核中但已超时」（进程被 kill 后留下的僵尸标记）。
    """
    feedback = Feedback.pending_ai_queryset().first()
    if feedback is None:
        return False

    stale = timezone.now() - timedelta(minutes=AI_RUNNING_STALE_MINUTES)
    claimed = Feedback.objects.filter(pk=feedback.pk).filter(
        Q(ai_status=Feedback.AiStatus.PENDING)
        | Q(ai_status=Feedback.AiStatus.RUNNING, updated_time__lt=stale)
    ).update(ai_status=Feedback.AiStatus.RUNNING, updated_time=timezone.now())
    if not claimed:
        return False

    try:
        review_submission(feedback, background=True)   # 后台线程：允许重试（同步路径不重试）
    except Exception:
        logger.exception('反馈 %s 审核过程中异常', feedback.pk)
        Feedback.objects.filter(pk=feedback.pk, ai_status=Feedback.AiStatus.RUNNING).update(
            ai_status=Feedback.AiStatus.FAILED, updated_time=timezone.now())
    return True
