"""代练搬单 · 打手 QQ 自动接待（业务链路）

打手接了代练丸子的订单后，会被引导来加我们的 QQ（单里的账号 / 联系方式都填的我们的 QQ）。
本模块让 AI 接管这段对话，替人工完成交接：

    好友添加成功 → AI 主动索要「丸子订单号」
    他还没给、只说别的 → 以客服口径持续引导，并解释「为什么必须要这个单号」
    打手报出单号 → 查搬单记录 → 去代练通接单
        接单成功 → 取号主信息发给他（让他上号代练）
        接单失败 → 已在代练通被人抢走 / 被撤，丸子那笔自动回滚撤单 + 告诉他「老板已撤单」

几个刻意的取舍：

- **「做不做」不交给模型**：单号用正则从消息里抽（`WZ` + 数字），命中后还要在库里核到记录
  才动手。模型只负责「怎么说」—— 接单是真实资金动作，不能让模型自由发挥。
- **必须异步**：NapCat 的事件回调要求立刻回 200（不回就反复重推），而一次 AI 生成要好几秒，
  故起后台守护线程（与 `qqbot/ai_reply.py`、`qqbot/setup.py` 同一写法）。
- **模型用后台的默认模型**，采样参数沿用该模型配置；上下文取最近 10 条往来（复用 `ai_reply`）。
- **回复一律按纯文本发**（`auto_escape=True`）：防模型输出 `[CQ:...]` 注入。
- **只对「打手」开口**：「打手」= 被我们开场白（`is_greeting`）打过招呼的 QQ ——
  我们的 QQ 只写在代练丸子的订单里，来人加好友即为打手；其余陌生好友的广告 / 闲聊完全不碰，
  回落到原有的「闲聊 AI」（`ai_reply`），避免误回无关好友。
- **单号没到手之前，身份就是客服**：不断把话头拉回「把订单号发我」，并解释为什么要它。

本模块返回的说明文案只用于写日志，不回给上游，故不参与翻译。
"""
import json
import logging
import re
import threading

logger = logging.getLogger('api.order_migration')

#: 丸子订单号：WZ + 一串数字（如 WZ20261006210929319040）
SERIAL_RE = re.compile(r'WZ\d{10,}')

#: 单条回复正文长度上限（与闲聊 AI 同口径，兜底防刷屏）
REPLY_MAX_LEN = 500

#: 退单判定 / 接待回复回看的往来条数：比闲聊（ai_reply.AI_HISTORY_LIMIT=10）多 ——
#: 「退单」是多轮对话，要让模型接住前面说过的话，再判断当前这句是不是在确认退单
HISTORY_LIMIT = 20


def extract_serial(text) -> str:
    """从消息里抽出第一个丸子订单号（抽不到返回空串）

    调用方（`qqbot/hook.py`）据此判断这条消息要不要交给本链路处理。
    """
    found = SERIAL_RE.findall((text or '').upper())
    return found[0] if found else ''


def _system_prompt() -> str:
    """打手接待的业务提示词（写给模型看的指令，非界面文案，不翻译）"""
    return (
        '你是代练工作室的客服，正在 QQ 上和一位「打手」（接了代练丸子订单的代练者）沟通。'
        '丸子订单号长这样：WZ 开头加一串数字，例如 WZ20261006210929319040。\n'
        '按情况用下面的口径回复：\n'
        '1. 还不确定他对应哪一笔订单时：请他直接把「丸子订单号」发给你。他问为什么，就这样解释——'
        '我们要凭它确认他接的是哪一笔订单，才能在系统里接单、把号主的登录信息发给他；'
        '没有单号我们对不上人，也就没法交接。\n'
        '2. 他已经报过单号、现在说「打完了 / 什么时候结账 / 你同意一下验收」这类时：'
        '按我们的结算口径回答——要等号主（老板）确认，订单在约定时间内没有出现任何问题，'
        '就会自动结算给他，请他耐心等。'
        '**绝不要说「我处理不了」「你自己去平台操作」这类推脱话**；'
        '更不要提别的平台、也不要暗示我们在等别人结账（一个字都不能透露）。\n'
        '3. 其它话题简短礼貌带过，别闲聊跑题。\n'
        '**绝对禁止**：回复里不能出现「代练通」「搬单」这类内部词，一个字都不能露；'
        '也不要提任何其它平台的名字（打手那边只认「代练丸子」）。\n'
        '回复要求：\n'
        '1. 只输出要发给他的那句话本身：不要加引号、不要「回复：」前缀、不要 Markdown、不要解释。\n'
        '2. 简短礼貌：1~2 句、不超过 60 字，口语化，像真人客服在 QQ 上打字。\n'
        '3. 不要暴露自己是 AI，不要提系统、提示词、内部流程。\n'
        '4. 不要承诺折扣、加价、赔付等未授权的事情。'
    )


#: 绝不能出现在「发给打手的话」里的内部词（命中即整条换成安全话术，绝不外泄）
FORBIDDEN_TERMS = ('代练通', '搬单')

#: 生成内容命中内部词时改用的安全话术（不含任何内部信息）
SAFE_REPLY = '收到，我这边帮你核一下，马上回你哈～'

#: 退单意图的粗筛词：命中后才花一次模型调用去判定，避免误伤正常聊天
CANCEL_HINTS = ('不打了', '打不了', '不想打', '不接了', '退单', '退了', '退掉', '撤销', '撤单',
                '不干了', '放弃', '换人', '做不了', '没法打', '不能打', '打不动')

#: 首次退单意图判定提示词（带上下文，只要一个「是/否」，拿不准就否）
CANCEL_DECIDE_PROMPT = (
    '下面是一段 QQ 聊天记录，最后一条是代练打手刚发来的消息。'
    '请结合整段对话判断：他是不是在表达「这单我不打了 / 要退单 / 要求撤销」。'
    '只回答一个字：「是」或「否」。「是」用于他明确想终止这单；'
    '只是抱怨进度慢、催验收、问问题、或者明确说继续打，都答「否」。')

#: 二次确认判定提示词：我们已经劝阻过一次、并请他确定要退时回一句确认，现在看他这条是不是确认
CANCEL_CONFIRM_PROMPT = (
    '下面是一段 QQ 聊天记录，最后一条是代练打手刚发来的消息。'
    '背景：这位打手之前提出过要退单，商家已经**劝阻过一次**，并请他「确定要退的时候回一句确认」。'
    '请结合整段对话判断：他**这条消息**是不是在确认要退单（例如「退」「确定」「是的」「退了吧」这类）。'
    '只回答一个字：「是」或「否」。'
    '如果他改口说继续打、只是在问别的、或者没有明确表态，都答「否」。')


def contains_forbidden(text) -> bool:
    """这句话里有没有内部词（有就绝不能发给打手）"""
    value = str(text or '')
    return any(term in value for term in FORBIDDEN_TERMS)


#: 判「他是否已经报过单号」时回看的历史消息条数
HISTORY_SCAN_LIMIT = 50


#: 打手（我们发过开场白）发了消息但没带单号时的引导要求（追加进系统提示词）
_GUIDE_INSTRUCTION = (
    '他还没有给出丸子订单号。请以客服口吻继续引导：说明我们必须要这个订单号——'
    '得凭它确认是哪一笔订单，才能在系统里接单、把号主的登录信息发给他，'
    '否则对不上人、无法交接；再请他直接把 WZ 开头的那串单号发过来。'
)


def is_taker_qq(user_id) -> bool:
    """该 QQ 是不是「来交接的打手」——判断依据：我们给这个会话发过业务开场白

    开场白只在 `notice.friend_add`（有人加我们好友）时发，而我们的 QQ 只写在代练丸子的
    订单里（引导打手来加），所以「被我们开场白打过招呼的 QQ」就是打手。
    """
    from API.models import QQPrivateMessage

    return QQPrivateMessage.objects.filter(
        user_id=str(user_id), direction=QQPrivateMessage.Direction.OUT,
        is_greeting=True).exists()


def has_reported_serial(user_id) -> bool:
    """他是不是已经报过丸子单号了（看他最近发来的消息里有没有 WZ 单号）

    报过之后就不该再追着要单号 —— 否则会出现「你同意验收啊」→「把单号再发我一遍」这种气人回复。
    """
    from API.models import QQPrivateMessage

    texts = (QQPrivateMessage.objects
             .filter(user_id=str(user_id), direction=QQPrivateMessage.Direction.IN)
             .order_by('-id')[:HISTORY_SCAN_LIMIT]
             .values_list('content', flat=True))
    return any(extract_serial(text) for text in texts)


def should_handle(user_id, content) -> bool:
    """这条私聊要不要交给本链路：消息里带单号，或者发件人是我们打过招呼的打手

    调用方（`qqbot/hook.py`）据此决定路由；不命中就回落到原有的「闲聊 AI」。
    """
    return bool(extract_serial(content)) or is_taker_qq(user_id)


def _send(user_id, text, is_greeting=False):
    """按纯文本发一条私聊，并按既有口径落库（后台「好友消息」面板可见）"""
    from API.apis.push.qqbot import utils as qqbot_utils

    ok, sent = qqbot_utils.send(text, qqbot_utils.TARGET_PRIVATE, user_id, auto_escape=True)
    if ok:
        qqbot_utils.record_outgoing_message(
            user_id, text, message_id=str(sent.get('message_id') or ''),
            is_greeting=is_greeting)
    return ok, sent


def _ai_reply(user_id, nickname='', instruction='', is_greeting=False):
    """带上下文让 AI 生成一句回复并发出（**阻塞式**）

    :param instruction: 本轮额外要求（追加进系统提示词），如「他刚加你好友，请索要单号」
    :param is_greeting: 本条是否业务开场白（会落库标记，见 is_taker_qq）
    :return: (True, 已发出的正文) / (False, 未发出的原因)
    """
    from API.apis.ai.BuiltInModel import utils as ai_utils
    from API.apis.push.qqbot import ai_reply

    target, err = ai_utils.resolve_target()
    if target is None:
        return False, err[1]

    # 多带一些往来，让它接得住多轮话头（退单这类对话跨好几轮）
    history = ai_reply._history_messages(user_id, limit=HISTORY_LIMIT)   # noqa: SLF001 同子系统复用取上下文口径
    if not history:
        # 刚加好友、他还没说过话：给模型一个「轮次」，否则只有系统提示词容易跑偏
        history = [{'role': 'user', 'content': '（我刚加了你好友）'}]

    system_text = _system_prompt()
    if instruction:
        system_text += f'\n本轮补充要求：{instruction}'
    try:
        messages = ai_utils.build_messages(
            None,
            messages_json=json.dumps(history, ensure_ascii=False),
            system_prompt=json.dumps([{'role': 'system', 'content': system_text}],
                                     ensure_ascii=False))
    except ValueError as exc:
        return False, f'构建对话失败: {exc}'

    ok, result = ai_utils.chat_completion(
        target, messages, background=True,
        temperature=target['temperature'], max_tokens=target['max_tokens'],
        stop=target['stop_list'])
    if not ok:
        return False, f'AI 调用失败: {result}'

    text = (result.get('reply') or '').strip()[:REPLY_MAX_LEN]
    if not text:
        return False, 'AI 返回了空内容'
    # 兜底闸门：模型偶尔会带出内部词（如「代练通」）——命中就整条换成安全话术，绝不外泄
    if contains_forbidden(text):
        logger.warning('打手 QQ 自动接待：生成内容命中内部词，已替换为安全话术 QQ %s', user_id)
        text = SAFE_REPLY
    ok, sent = _send(user_id, text, is_greeting=is_greeting)
    if not ok:
        return False, f'发送失败: {sent.get("message") or ""}'
    return True, text


def _owner_message(owner) -> str:
    """把号主信息排成一条给打手的消息（**不能出现任何内部词**）"""
    return '\n'.join([
        '✅ 已帮你接单成功，以下是号主信息：',
        '',
        f"游戏：{owner.get('游戏名称') or '-'}（{owner.get('客户端') or '-'}）",
        f"游戏账号：{owner.get('游戏账号') or '-'}",
        f"游戏密码：{owner.get('密码') or '-'}",
        f"角色名：{owner.get('角色名') or '-'}",
        f"号主联系方式：{owner.get('号主联系方式') or '-'}",
        f"剩余时间：{owner.get('剩余时间') or '-'}",
        '',
        '请及时上号，并按代练丸子的要求先上传首图。',
    ])


def _take_and_deliver(record, user_id):
    """去代练通接单；成功把号主信息发给打手，失败（已在别处被接 / 被撤）则告知打手

    「失败即回滚丸子那笔」由 `_take_on_dlt` 内部完成（撤单 / 申请撤销 + 记录置失败）。
    """
    from . import utils as om_utils

    # 号主信息一旦发过就绝不再发（不管是谁来问、说了什么）
    if record.owner_info_sent:
        return _send(user_id, f'这单（{record.dlwz_trade_no}）我们这边已经在处理啦，'
                              '不用重复发单号哈～')

    if not om_utils._take_on_dlt(record):      # noqa: SLF001 同包内的接单编排，直接复用
        _send(user_id, f'抱歉，这单（{record.dlwz_trade_no}）老板那边已经撤单/被别人接走了，'
                       '我们已在代练丸子同步撤单，这单不用再代练了。')
        return False, '代练通接单失败，已回滚并告知打手'

    from API.apis.DaiLianTong import utils as dlt_utils

    ok, owner = dlt_utils.get_owner_info(record.dlt_serial_no)
    if not ok:
        # 接单已成功，只是没取到号主信息 —— 别让打手干等，先告知并记日志
        _send(user_id, f'✅ 已帮你接单成功（{record.dlwz_trade_no}）。'
                       '号主信息稍后由客服单独发你。')
        return True, f'代练通接单成功，但取号主信息失败: {owner}'

    sent_ok, _sent = _send(user_id, _owner_message(owner if isinstance(owner, dict) else {}))
    if sent_ok:
        record.owner_info_sent = True
        record.save(update_fields=['owner_info_sent', 'updated_time'])
    else:
        logger.warning('打手 QQ 自动接待：号主信息发送失败，未标记已发送 %s',
                       record.dlwz_trade_no)
    return True, '代练通接单成功，号主信息已发给打手'


def _dlwz_order_taken(trade_no):
    """跟代练丸子**实时核一次**：这笔订单到底有没有被打手接单

    为什么不只看本地状态：我们的状态是轮询快照，打手接单后立刻来报单号时，本地可能还停在
    「待接单」，只看快照会误判成「还没被接单」。所以动手前必须跟平台核一遍。

    :return: (查询是否成功, 是否已被接单)；查询失败时第二项无意义，调用方不要据此接单
    """
    from . import utils as om_utils

    ok, orders = om_utils.poll_dlwz_orders()
    if not ok:
        return False, False
    order = orders.get(trade_no)
    if not order:
        return True, False          # 平台上查不到该单（可能已撤）：视为未接单
    return True, om_utils._is_taken(order)     # noqa: SLF001 同包内的判单口径


def _looks_like_cancel(content) -> bool:
    """粗筛退单意图（纯字符串判断，不花模型调用）"""
    text = str(content or '')
    return any(hint in text for hint in CANCEL_HINTS)


def _judge(user_id, content, prompt) -> bool:
    """用模型 + 最近往来判一个「是/否」（调不通 / 拿不准都按「否」）

    **带上下文**而不是只看这一句：退单是跨多轮的对话，单独一句「退」只有结合前文
    才知道他是在确认退单（而不是在说别的）。
    """
    from API.apis.ai.BuiltInModel import utils as ai_utils
    from API.apis.push.qqbot import ai_reply

    target, err = ai_utils.resolve_target()
    if target is None:
        logger.warning('退单意图判定跳过：%s', err[1])
        return False

    history = ai_reply._history_messages(user_id, limit=HISTORY_LIMIT)   # noqa: SLF001 复用取上下文口径
    if not history:
        history = [{'role': 'user', 'content': str(content or '')}]
    try:
        messages = ai_utils.build_messages(
            None,
            messages_json=json.dumps(history, ensure_ascii=False),
            system_prompt=json.dumps([{'role': 'system', 'content': prompt}],
                                     ensure_ascii=False))
    except ValueError as exc:
        logger.warning('退单意图判定失败：%s', exc)
        return False
    ok, result = ai_utils.chat_completion(
        target, messages, background=True,
        temperature=target['temperature'], max_tokens=target['max_tokens'],
        stop=target['stop_list'])
    if not ok:
        logger.warning('退单意图判定失败：%s', result)
        return False
    # 提示词要求只回一个字，故用 startswith：避免「不是」被当成「是」
    return str(result.get('reply') or '').strip().startswith('是')


def _ai_says_cancel(user_id, content) -> bool:
    """他是不是在提出退单（结合上下文判定）"""
    return _judge(user_id, content, CANCEL_DECIDE_PROMPT)


def _ai_confirms_cancel(user_id, content) -> bool:
    """他这条是不是在「确认退单」（我们已劝阻过一次、并请他明确回一句）"""
    return _judge(user_id, content, CANCEL_CONFIRM_PROMPT)


def _find_cancel_record(user_id, serial=''):
    """他要退的是哪一单：优先消息里的单号；否则他名下唯一在跑的单

    名下有不止一单在跑时返回 None（认不出来就别猜，先问清楚要退哪单）。
    """
    from API.models import MigrationStatus, OrderMigration

    active = (MigrationStatus.PUBLISHED, MigrationStatus.TAKER_JOINED, MigrationStatus.TAKEN,
              MigrationStatus.WAITING_ACCEPT, MigrationStatus.BOOSTER_CANCEL)
    if serial:
        return OrderMigration.objects.filter(dlwz_trade_no=serial, status__in=active).first()
    candidates = list(OrderMigration.objects.filter(booster_qq=str(user_id), status__in=active))
    return candidates[0] if len(candidates) == 1 else None


def _pending_cancel_record(user_id, serial=''):
    """他名下「已劝阻过、还没通知」的那一单 —— 用来接住他接下来的二次确认

    二次确认常常只有一两个字（「退」「确定」），粗筛词根本命中不了；所以不能靠关键词，
    要靠**状态**认：我们已劝阻过他、正等他一句确认。
    """
    from API.models import OrderMigration

    pending = OrderMigration.objects.filter(
        booster_cancel_asked=True, booster_cancel_notified=False)
    if serial:
        return pending.filter(dlwz_trade_no=serial).first()
    if not str(user_id or ''):
        return None
    return pending.filter(booster_qq=str(user_id)).first()


def _handle_cancel_confirm(record, user_id, nickname, content):
    """二次确认到位：落库「打手申请退单」并通知管理员（Server酱 + QQBot）"""
    from . import utils as om_utils

    om_utils.notify_booster_cancel(
        record, reason=f'打手在 QQ 上二次确认退单：{str(content or "")[:80]}',
        booster_name=nickname)
    return _send(user_id, '收到，我这边帮你走退单流程，客服会尽快联系你哈～')


def _handle_cancel_intent(user_id, nickname, content, serial=''):
    """打手说要退单：**先劝阻一次**；他再次确认才落库 + 通知管理员

    为什么要二次确认：退单牵着罚款和赔付，误判代价高。第一次先稳住他、请他明确一句；
    第二次（认到具体那一单）才置「打手申请退单」并通知我们人工去平台处理。
    """
    record = _find_cancel_record(user_id, serial)
    if record is None:
        # 认不出是哪一单（可能他还没报过单号，或名下有不止一单）：先问清楚，不动数据
        return _ai_reply(user_id, nickname, instruction=(
            '他说要退单，但我们还没确认是哪一笔。请先安抚他，并请他把要退的那笔'
            '代练丸子订单号（WZ 开头）发给你。不要承诺任何赔付或减免。'))

    # 记住是哪个 QQ 在谈这单：二次确认常常不带单号，要靠它（booster_qq）认出来
    updates = []
    if record.booster_qq != str(user_id):
        record.booster_qq = str(user_id)
        updates.append('booster_qq')

    if not record.booster_cancel_asked:
        record.booster_cancel_asked = True
        updates.append('booster_cancel_asked')
        record.save(update_fields=updates + ['updated_time'])
        return _ai_reply(user_id, nickname, instruction=(
            f'他说要退单（{record.dlwz_trade_no}）。请**先劝他尽量打完**：说明中途退单'
            '会影响他的接单信誉、双金也可能被扣。然后请他明确回一句「确定要退」。'
            '不要承诺任何赔付或减免，也不要提别的平台。'))

    if updates:
        record.save(update_fields=updates + ['updated_time'])
    return _handle_cancel_confirm(record, user_id, nickname, content)


def _handle_serial(user_id, serial):
    """打手报出了丸子订单号：查库 → 核实丸子已被接单 → 才去接单并交号主信息"""
    from API.models import MigrationStatus, OrderMigration

    record = OrderMigration.objects.filter(dlwz_trade_no=serial).first()
    if record is None:
        return _ai_reply(user_id, instruction=f'他发来的单号 {serial} 我们没查到，'
                                              '请礼貌地请他核对后重新发一遍。')
    if record.booster_qq != str(user_id):
        # 记住这位打手的 QQ（退单通知里要带给我们，便于联系）
        record.booster_qq = str(user_id)
        record.save(update_fields=['booster_qq', 'updated_time'])

    # 已经接过单（或号主信息已发过）→ 按规矩一律不再重复发送号主信息
    if (record.owner_info_sent
            or record.status in (MigrationStatus.TAKEN, MigrationStatus.WAITING_ACCEPT,
                                 MigrationStatus.SETTLED)):
        return _send(user_id, f'这单（{serial}）我们这边已经在处理啦，不用重复发单号哈～')
    if record.status not in (MigrationStatus.PUBLISHED, MigrationStatus.TAKER_JOINED):
        # 不直接把状态名发给打手：状态文案里可能带内部词（如「代练通已接单」）
        return _send(user_id, f'这单（{serial}）我们这边已经在处理了，暂时不用你操作，'
                              '稍后客服会联系你。')

    # 动手前核一次：**丸子上确实被接单了**才去接单，光有单号不算
    ok, taken = _dlwz_order_taken(serial)
    if not ok:
        logger.warning('打手 QQ 自动接待：核对丸子接单状态失败，暂不接单 %s', serial)
        return _send(user_id, SAFE_REPLY)
    if not taken:
        return _send(user_id, f'这笔（{serial}）在代练丸子还没被接单哦，'
                              '你先在丸子上接了单，再把单号发我～')

    return _take_and_deliver(record, user_id)


def handle_message(user_id, nickname, content):
    """处理一条私聊（**阻塞式**；调用方负责放进后台线程）

    - 我们已劝阻过他退单、正等他确认时，这条若是在确认 → 落库「打手申请退单」+ 通知管理员
    - 像是在说退单（且这是打手，或消息里带了我们的单号）→ 先劝阻，请他明确一句
    - 消息里带丸子订单号 → 执行业务动作（查库 → 代练通接单 → 交号主信息）
    - 是打手（我们给他发过开场白）但没带单号 → 以**客服口径**继续引导他要单号
    - 其它（陌生好友的广告 / 闲聊）→ 不碰，交回调用方走原有的「闲聊 AI」

    :return: True=本模块已处理；False=与本链路无关，交回调用方
    """
    serial = extract_serial(content)
    taker = is_taker_qq(user_id)

    # ① 已经劝阻过、正等他一句确认：结合**上下文**判断这条是不是在确认退单。
    #    二次确认常常只有一两个字（「退」「确定」），粗筛词命中不了，只能靠状态 + 上下文来认。
    pending = _pending_cancel_record(user_id, serial)
    if pending is not None and _ai_confirms_cancel(user_id, content):
        ok, detail = _handle_cancel_confirm(pending, user_id, nickname, content)
    # ② 首次表达退单：他像是在说退单（打手，或消息里带了我们的单号）就先按退单处理。
    #    **绝不能**让「我要退单」落到下面的「报单号 → 去平台接单」分支 —— 那会真的去接单 / 回滚。
    elif _looks_like_cancel(content) and (taker or serial) and _ai_says_cancel(user_id, content):
        ok, detail = _handle_cancel_intent(user_id, nickname, content, serial)
    elif serial:
        ok, detail = _handle_serial(user_id, serial)
    elif taker:
        # 还没报过单号 → 引导他要单号；报过了 → 交回提示词按情况（如催结算）回复
        instruction = '' if has_reported_serial(user_id) else _GUIDE_INSTRUCTION
        ok, detail = _ai_reply(user_id, nickname, instruction=instruction)
    else:
        return False

    if ok:
        logger.info('打手 QQ 自动接待已回复 QQ %s：%s', user_id, detail)
    else:
        logger.info('打手 QQ 自动接待未回复 QQ %s：%s', user_id, detail)
    return True


def greet(user_id, nickname=''):
    """好友添加成功后的开场：让 AI 主动索要丸子订单号（**阻塞式**）

    开场白会落库标记为「业务开场白」，之后该 QQ 的私聊都按打手（客服口径）处理。
    """
    ok, detail = _ai_reply(user_id, nickname,
                           instruction='他刚刚加你好友、还没说过话。请发一句简短的招呼，'
                                       '并请他直接把代练丸子的订单号（WZ 开头）发给你。',
                           is_greeting=True)
    if ok:
        logger.info('打手 QQ 自动接待已发开场白 QQ %s：%s', user_id, detail)
    else:
        logger.info('打手 QQ 自动接待开场白未发出 QQ %s：%s', user_id, detail)
    return ok, detail


def spawn_handle(user_id, nickname, content):
    """在后台守护线程里处理一条打手消息（NapCat 回调要立刻返回 200）"""
    threading.Thread(target=_worker, args=(handle_message, (user_id, nickname, content)),
                     name='qq-flow-message', daemon=True).start()


def spawn_greet(user_id, nickname=''):
    """在后台守护线程里发开场白（好友刚添加成功）"""
    threading.Thread(target=_worker, args=(greet, (user_id, nickname)),
                     name='qq-flow-greet', daemon=True).start()


def _worker(func, args):
    """线程入口：自带数据库连接管理与异常兜底（连接不能跨线程复用）"""
    from django.db import close_old_connections

    close_old_connections()
    try:
        func(*args)
    except Exception:                          # noqa: BLE001 线程入口兜底，异常不能抛到无人接管处
        logger.exception('打手 QQ 自动接待异常')
    finally:
        close_old_connections()
