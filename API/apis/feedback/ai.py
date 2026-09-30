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

AI 不可用的情形一律「跳过审核」而不是「卡住」：

    - 后台关闭了 AI 审核开关                      → 直接进入「待处理」
    - 平台没配置可用模型 / 没配 Key                → 直接进入「待处理」
    - 模型调用失败（网络 / 额度 / 返回不是 JSON）   → 记为「审核失败」，条目留在「待审核」，
                                                    管理员可手动重审
"""
import json
import logging
import os
import sys
import threading
import time

from django.db import close_old_connections
from django.utils import timezone

from API.apis.ai.BuiltInModel import utils as ai_utils
from API.models import (
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


def _call_ai(target, system_prompt, user_content):
    """把「提示词 + 正文」发给 AI 并解析出结构化结论

    :return: (True, dict) / (False, 错误文案)
    """
    try:
        messages = ai_utils.build_messages(
            user_content,
            system_prompt=json.dumps([{'role': 'system', 'content': system_prompt}],
                                     ensure_ascii=False),
        )
    except ValueError as exc:
        return False, f'构建审核请求失败: {exc}'

    # 采样参数沿用该模型在后台的配置（与对外对话接口同一口径，调用方不额外干预）
    ok, result = ai_utils.chat_completion(
        target, messages,
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


def review_submission(feedback):
    """审核一条反馈的提交内容（审核线程与后台「立即送审」共用）

    :return: (ok, 说明文案)；ok 只表示流程跑完，不代表审核通过
    """
    setting = FeedbackSetting.get_solo()
    target, reason = resolve_review_target(setting)
    if target is None:
        return _skip(feedback, reason)

    ok, data = _call_ai(target, review_prompt(setting, 'submit'), _render_submit_input(feedback))
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
    """管理员回复的语气审查（同步调用）

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

    抢占用条件更新（`WHERE id=? AND ai_status='pending'`）：多进程 / 多线程下只有一个
    能把状态改成「审核中」，抢不到的进程直接进入下一轮，不会重复调用 AI。
    """
    feedback = Feedback.pending_ai_queryset().first()
    if feedback is None:
        return False

    claimed = Feedback.objects.filter(
        pk=feedback.pk, ai_status=Feedback.AiStatus.PENDING,
    ).update(ai_status=Feedback.AiStatus.RUNNING, updated_time=timezone.now())
    if not claimed:
        return False

    try:
        review_submission(feedback)
    except Exception:
        logger.exception('反馈 %s 审核过程中异常', feedback.pk)
        Feedback.objects.filter(pk=feedback.pk, ai_status=Feedback.AiStatus.RUNNING).update(
            ai_status=Feedback.AiStatus.FAILED, updated_time=timezone.now())
    return True
