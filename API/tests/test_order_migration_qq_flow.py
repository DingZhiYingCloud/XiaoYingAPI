"""代练搬单「打手 QQ 自动接待」单元测试

覆盖：单号抽取、好友添加开场、报单号后的接单 / 交号 / 失败撤单分支。
全程 mock 平台调用与 AI，不触网、不产生真实订单。
"""
from unittest import mock

from django.test import TestCase

from API.apis.order_migration import qq_flow
from API.models import MigrationStatus, OrderMigration, QQPrivateMessage

SERIAL = 'WZ20261006210929319040'


def _mark_taker(user_id='u1', greeting=True):
    """模拟「我们给该 QQ 发过业务开场白」→ 把他认作来交接的打手"""
    return QQPrivateMessage.objects.create(
        user_id=user_id, content='你好，麻烦把丸子订单号发我',
        direction=QQPrivateMessage.Direction.OUT, is_read=True, is_greeting=greeting)


class TakerDetectionTests(TestCase):
    """谁是打手：被我们开场白打过招呼的 QQ（我们的 QQ 只写在丸子订单里）"""

    def test_no_greeting_is_not_taker(self):
        self.assertFalse(qq_flow.is_taker_qq('u1'))
        QQPrivateMessage.objects.create(
            user_id='u1', content='你好', direction=QQPrivateMessage.Direction.IN)
        self.assertFalse(qq_flow.is_taker_qq('u1'))

    def test_plain_outgoing_reply_is_not_taker(self):
        """后台人工回复不算开场白，别把普通好友当打手"""
        QQPrivateMessage.objects.create(
            user_id='u1', content='在的', direction=QQPrivateMessage.Direction.OUT)
        self.assertFalse(qq_flow.is_taker_qq('u1'))

    def test_greeting_marks_taker(self):
        _mark_taker('u1')
        self.assertTrue(qq_flow.is_taker_qq('u1'))
        self.assertFalse(qq_flow.is_taker_qq('u2'))       # 只认打过招呼那个 QQ

    def test_should_handle(self):
        self.assertTrue(qq_flow.should_handle('u1', f'单号 {SERIAL}'))     # 带单号
        self.assertFalse(qq_flow.should_handle('u1', '你好在吗'))          # 陌生人闲聊
        _mark_taker('u1')
        self.assertTrue(qq_flow.should_handle('u1', '你好在吗'))          # 打手闲聊也要接

    def test_has_reported_serial(self):
        self.assertFalse(qq_flow.has_reported_serial('u1'))
        QQPrivateMessage.objects.create(user_id='u1', content=f'我的单号 {SERIAL}',
                                        direction=QQPrivateMessage.Direction.IN)
        self.assertTrue(qq_flow.has_reported_serial('u1'))

    def test_outgoing_serial_does_not_count(self):
        """我们自己发出去的（如接单成功回执里带单号）不算「他报过号」"""
        QQPrivateMessage.objects.create(user_id='u1', content=f'已帮你接好 {SERIAL}',
                                        direction=QQPrivateMessage.Direction.OUT)
        self.assertFalse(qq_flow.has_reported_serial('u1'))


class ExtractSerialTests(TestCase):
    """丸子单号抽取：WZ + 数字，大小写不敏感，取第一个"""

    def test_extracts_serial(self):
        self.assertEqual(qq_flow.extract_serial(f'你好，我的单号是 {SERIAL}'), SERIAL)

    def test_case_insensitive(self):
        self.assertEqual(qq_flow.extract_serial('wz20261006210929319040'), SERIAL)

    def test_no_serial(self):
        self.assertEqual(qq_flow.extract_serial('你好，在吗'), '')
        self.assertEqual(qq_flow.extract_serial(''), '')
        self.assertEqual(qq_flow.extract_serial(None), '')

    def test_takes_first_of_many(self):
        text = f'{SERIAL} 和 WZ20260101000000000001'
        self.assertEqual(qq_flow.extract_serial(text), SERIAL)


class HandleMessageTests(TestCase):
    """报单号 → 查库 → 接单 / 交号主信息 / 失败撤单"""

    def _record(self, **overrides):
        fields = dict(dlt_serial_no='10718808437372810349', dlt_title='t', dlt_price=3,
                      dlt_zone='安卓QQ', dlt_time_limit=3, dlwz_trade_no=SERIAL,
                      status=MigrationStatus.TAKER_JOINED)
        fields.update(overrides)
        return OrderMigration.objects.create(**fields)

    def test_no_serial_is_not_handled(self):
        """陌生人（非打手）的闲聊不接：交给调用方的闲聊 AI"""
        with mock.patch.object(qq_flow, '_ai_reply') as ai, \
             mock.patch.object(qq_flow, '_send') as send:
            self.assertFalse(qq_flow.handle_message('u1', '打手', '你好在吗'))
        ai.assert_not_called()
        send.assert_not_called()

    def test_taker_without_serial_gets_guidance(self):
        """打手还没给单号 → 以客服口径继续引导（并解释为什么必须要单号）"""
        _mark_taker('u1')
        with mock.patch.object(qq_flow, '_ai_reply', return_value=(True, '请把单号发我')) as ai:
            self.assertTrue(qq_flow.handle_message('u1', '打手', '你好，我接单了'))
        ai.assert_called_once()
        self.assertIn('订单号', ai.call_args.kwargs['instruction'])

    def test_reported_taker_not_asked_for_serial_again(self):
        """已经报过单号的人再说话（比如催结算）→ 不该再被追着要单号"""
        _mark_taker('u1')
        QQPrivateMessage.objects.create(user_id='u1', content=f'我的单号 {SERIAL}',
                                        direction=QQPrivateMessage.Direction.IN)
        with mock.patch.object(qq_flow, '_ai_reply', return_value=(True, '好的')) as ai:
            self.assertTrue(qq_flow.handle_message('u1', '打手', '我打完了，麻烦同意一下验收'))
        self.assertEqual(ai.call_args.kwargs['instruction'], '')

    def test_unknown_serial_asks_ai_to_recheck(self):
        with mock.patch.object(qq_flow, '_ai_reply',
                               return_value=(True, '没查到')) as ai:
            self.assertTrue(qq_flow.handle_message('u1', '打手', SERIAL))
        ai.assert_called_once()
        self.assertIn(SERIAL, ai.call_args.kwargs['instruction'])

    def test_take_success_delivers_owner_info(self):
        record = self._record()
        owner = {'游戏名称': '王者荣耀', '客户端': '安卓QQ', '游戏账号': 'acc1',
                 '密码': 'pwd1', '角色名': '小影', '号主联系方式': '13700000000',
                 '剩余时间': 3}
        with mock.patch.object(qq_flow, '_dlwz_order_taken', return_value=(True, True)), \
             mock.patch('API.apis.order_migration.utils._take_on_dlt',
                        return_value=True) as take, \
             mock.patch('API.apis.DaiLianTong.utils.get_owner_info',
                        return_value=(True, owner)), \
             mock.patch.object(qq_flow, '_send', return_value=(True, {})) as send:
            self.assertTrue(qq_flow.handle_message('u1', '打手', f'单号 {SERIAL}'))

        take.assert_called_once()
        sent_text = send.call_args.args[1]
        self.assertIn('acc1', sent_text)
        self.assertIn('13700000000', sent_text)
        record.refresh_from_db()
        self.assertTrue(record.owner_info_sent)          # 标记已发送 → 之后绝不再发

    def test_take_failure_tells_booster_cancelled(self):
        record = self._record()
        with mock.patch.object(qq_flow, '_dlwz_order_taken', return_value=(True, True)), \
             mock.patch('API.apis.order_migration.utils._take_on_dlt',
                        return_value=False) as take, \
             mock.patch('API.apis.DaiLianTong.utils.get_owner_info') as owner, \
             mock.patch.object(qq_flow, '_send', return_value=(True, {})) as send:
            self.assertTrue(qq_flow.handle_message('u1', '打手', SERIAL))

        take.assert_called_once()
        owner.assert_not_called()                  # 没接成，不该去取号主信息
        self.assertIn('撤单', send.call_args.args[1])
        record.refresh_from_db()
        self.assertEqual(record.status, MigrationStatus.TAKER_JOINED)   # 状态由 _take_on_dlt 内部处理
        self.assertFalse(record.owner_info_sent)

    def test_owner_info_failure_still_replies(self):
        record = self._record()
        with mock.patch.object(qq_flow, '_dlwz_order_taken', return_value=(True, True)), \
             mock.patch('API.apis.order_migration.utils._take_on_dlt', return_value=True), \
             mock.patch('API.apis.DaiLianTong.utils.get_owner_info',
                        return_value=(False, '订单不存在')), \
             mock.patch.object(qq_flow, '_send', return_value=(True, {})) as send:
            ok = qq_flow.handle_message('u1', '打手', SERIAL)

        self.assertTrue(ok)
        send.assert_called_once()                  # 明确告诉他接好了、信息稍后发
        self.assertIn('号主信息', send.call_args.args[1])
        record.refresh_from_db()
        self.assertFalse(record.owner_info_sent)   # 没真发出去 → 不标记

    def test_not_taken_on_dlwz_refuses_to_take(self):
        """丸子上还没被接单：只提示他先接单，绝不去代练通接单"""
        self._record()
        with mock.patch.object(qq_flow, '_dlwz_order_taken', return_value=(True, False)), \
             mock.patch('API.apis.order_migration.utils._take_on_dlt') as take, \
             mock.patch.object(qq_flow, '_send', return_value=(True, {})) as send:
            self.assertTrue(qq_flow.handle_message('u1', '打手', SERIAL))

        take.assert_not_called()
        self.assertIn('还没被接单', send.call_args.args[1])

    def test_taken_check_failure_uses_safe_reply(self):
        """核对丸子接单状态失败 → 不接单，用安全话术拖住"""
        self._record()
        with mock.patch.object(qq_flow, '_dlwz_order_taken', return_value=(False, False)), \
             mock.patch('API.apis.order_migration.utils._take_on_dlt') as take, \
             mock.patch.object(qq_flow, '_send', return_value=(True, {})) as send:
            self.assertTrue(qq_flow.handle_message('u1', '打手', SERIAL))

        take.assert_not_called()
        self.assertEqual(send.call_args.args[1], qq_flow.SAFE_REPLY)

    def test_already_taken_never_resends(self):
        """已接过单的单号再来问：只回一句「已处理」，绝不再发号主信息"""
        self._record(status=MigrationStatus.TAKEN)
        with mock.patch.object(qq_flow, '_send', return_value=(True, {})) as send, \
             mock.patch.object(qq_flow, '_dlwz_order_taken') as check, \
             mock.patch('API.apis.order_migration.utils._take_on_dlt') as take:
            self.assertTrue(qq_flow.handle_message('u1', '打手', SERIAL))
        take.assert_not_called()
        check.assert_not_called()
        self.assertIn('已经在处理', send.call_args.args[1])

    def test_owner_info_sent_blocks_resend(self):
        """号主信息已发过（哪怕状态没变）→ 绝不再发，不管是谁来问"""
        self._record(owner_info_sent=True)
        with mock.patch.object(qq_flow, '_send', return_value=(True, {})) as send, \
             mock.patch.object(qq_flow, '_dlwz_order_taken') as check, \
             mock.patch('API.apis.order_migration.utils._take_on_dlt') as take:
            self.assertTrue(qq_flow.handle_message('u1', '打手', SERIAL))
        take.assert_not_called()
        check.assert_not_called()
        self.assertIn('已经在处理', send.call_args.args[1])


class DlwzOrderTakenCheckTests(TestCase):
    """「丸子确实被接单了吗」：动手前必须跟平台实时核一次"""

    @mock.patch('API.apis.order_migration.utils.poll_dlwz_orders')
    def test_taken(self, poll):
        poll.return_value = (True, {'WZ1': {'tradeNo': 'WZ1', 'takerUsername': 'x'}})
        self.assertEqual(qq_flow._dlwz_order_taken('WZ1'), (True, True))

    @mock.patch('API.apis.order_migration.utils.poll_dlwz_orders')
    def test_not_taken(self, poll):
        poll.return_value = (True, {'WZ1': {'tradeNo': 'WZ1'}})
        self.assertEqual(qq_flow._dlwz_order_taken('WZ1'), (True, False))

    @mock.patch('API.apis.order_migration.utils.poll_dlwz_orders')
    def test_not_found(self, poll):
        poll.return_value = (True, {})
        self.assertEqual(qq_flow._dlwz_order_taken('WZ1'), (True, False))

    @mock.patch('API.apis.order_migration.utils.poll_dlwz_orders')
    def test_query_failure(self, poll):
        poll.return_value = (False, '网络异常')
        self.assertEqual(qq_flow._dlwz_order_taken('WZ1'), (False, False))


class ForbiddenTermTests(TestCase):
    """内部词闸门：发给打手的话里绝不能出现「代练通」「搬单」"""

    def test_detects_forbidden_terms(self):
        self.assertTrue(qq_flow.contains_forbidden('我这边在代练通给你接好了'))
        self.assertTrue(qq_flow.contains_forbidden('搬单记录'))
        self.assertFalse(qq_flow.contains_forbidden('已帮你接单成功，号主信息如下'))
        self.assertFalse(qq_flow.contains_forbidden(''))
        self.assertFalse(qq_flow.contains_forbidden(None))

    def test_owner_message_has_no_forbidden_term(self):
        owner = {'游戏名称': '王者荣耀', '客户端': '安卓QQ', '游戏账号': 'acc1',
                 '密码': 'pwd1', '角色名': '小影', '号主联系方式': '13700000000',
                 '剩余时间': 3}
        self.assertFalse(qq_flow.contains_forbidden(qq_flow._owner_message(owner)))

    @mock.patch('API.apis.push.qqbot.utils.record_outgoing_message')
    @mock.patch('API.apis.push.qqbot.utils.send', return_value=(True, {'message_id': 'm1'}))
    @mock.patch('API.apis.ai.BuiltInModel.utils.chat_completion',
                return_value=(True, {'reply': '我这边在代练通给你接好了'}))
    @mock.patch('API.apis.ai.BuiltInModel.utils.build_messages', return_value=[])
    @mock.patch('API.apis.ai.BuiltInModel.utils.resolve_target',
                return_value=({'temperature': 0.5, 'max_tokens': 100, 'stop_list': []}, None))
    def test_leaky_ai_reply_is_replaced(self, target, build, chat, send, record):
        """模型万一说出内部词 → 整条换成安全话术，绝不外发"""
        ok, text = qq_flow._ai_reply('u1', '打手')
        self.assertTrue(ok)
        self.assertEqual(text, qq_flow.SAFE_REPLY)
        self.assertEqual(send.call_args.args[0], qq_flow.SAFE_REPLY)


class GreetTests(TestCase):
    """好友添加成功 → 让 AI 主动索要丸子订单号"""

    def test_greet_asks_for_serial(self):
        with mock.patch.object(qq_flow, '_ai_reply',
                               return_value=(True, '你好，请发我丸子单号')) as ai:
            ok, _detail = qq_flow.greet('u1', '打手')
        self.assertTrue(ok)
        self.assertIn('订单号', ai.call_args.kwargs['instruction'])


class CancelIntentTests(TestCase):
    """打手退单：先劝阻一次，二次确认才落库 + 通知管理员；平台动作留给人工"""

    def _record(self, **overrides):
        fields = dict(dlt_serial_no='10718808437372810349', dlt_title='t', dlt_price=3,
                      dlt_zone='安卓QQ', dlt_time_limit=3, dlwz_trade_no=SERIAL,
                      status=MigrationStatus.TAKEN, booster_qq='u1')
        fields.update(overrides)
        return OrderMigration.objects.create(**fields)

    def test_looks_like_cancel(self):
        self.assertTrue(qq_flow._looks_like_cancel('这单我不打了'))
        self.assertTrue(qq_flow._looks_like_cancel('帮我退单吧'))
        self.assertFalse(qq_flow._looks_like_cancel('我打完了，麻烦同意验收'))
        self.assertFalse(qq_flow._looks_like_cancel(''))
        self.assertFalse(qq_flow._looks_like_cancel(None))

    def test_find_cancel_record_by_serial(self):
        record = self._record()
        self.assertEqual(qq_flow._find_cancel_record('u1', SERIAL), record)

    def test_find_cancel_record_single_active(self):
        record = self._record()
        self.assertEqual(qq_flow._find_cancel_record('u1'), record)

    def test_find_cancel_record_ambiguous_returns_none(self):
        self._record()
        self._record(dlt_serial_no='A2', dlwz_trade_no='WZ20261006210929319041')
        self.assertIsNone(qq_flow._find_cancel_record('u1'))

    def test_find_cancel_record_ignores_finished(self):
        self._record(status=MigrationStatus.SETTLED)
        self.assertIsNone(qq_flow._find_cancel_record('u1'))

    def test_first_cancel_only_urges_no_notify(self):
        """第一次提退单：只劝阻 + 请他明确确认，绝不落库 / 通知"""
        record = self._record()
        with mock.patch.object(qq_flow, '_ai_reply', return_value=(True, '再想想？')) as ai, \
             mock.patch('API.apis.order_migration.utils.notify_booster_cancel') as notify:
            ok, _detail = qq_flow._handle_cancel_intent('u1', '打手', '我不想打了', SERIAL)

        self.assertTrue(ok)
        ai.assert_called_once()
        notify.assert_not_called()
        record.refresh_from_db()
        self.assertTrue(record.booster_cancel_asked)
        self.assertNotEqual(record.status, MigrationStatus.BOOSTER_CANCEL)

    def test_second_cancel_notifies(self):
        """二次确认：才置「打手申请退单」并通知管理员"""
        self._record(booster_cancel_asked=True)
        with mock.patch('API.apis.order_migration.utils.notify_booster_cancel') as notify, \
             mock.patch.object(qq_flow, '_send', return_value=(True, {})) as send:
            ok, _detail = qq_flow._handle_cancel_intent('u1', '打手', '确定要退', SERIAL)

        self.assertTrue(ok)
        notify.assert_called_once()
        self.assertEqual(notify.call_args.kwargs['booster_name'], '打手')
        send.assert_called_once()

    def test_unknown_record_asks_for_serial(self):
        """认不出是哪一单 → 先问清楚，不动数据"""
        with mock.patch.object(qq_flow, '_ai_reply', return_value=(True, '哪一单？')) as ai, \
             mock.patch('API.apis.order_migration.utils.notify_booster_cancel') as notify:
            ok, _detail = qq_flow._handle_cancel_intent('u1', '打手', '不打了')

        self.assertTrue(ok)
        notify.assert_not_called()
        self.assertIn('订单号', ai.call_args.kwargs['instruction'])

    def test_handle_message_routes_cancel_first(self):
        """一句话里既带单号又说退单：退单优先，不走「报单号接单」"""
        _mark_taker('u1')
        with mock.patch.object(qq_flow, '_ai_says_cancel', return_value=True), \
             mock.patch.object(qq_flow, '_handle_cancel_intent',
                               return_value=(True, 'ok')) as cancel, \
             mock.patch.object(qq_flow, '_handle_serial') as serial:
            self.assertTrue(qq_flow.handle_message('u1', '打手', f'我不打了 {SERIAL}'))

        cancel.assert_called_once()
        serial.assert_not_called()

    def test_handle_message_ignores_non_taker_cancel(self):
        """陌生好友说要退单（无单号）：不是打手，不处理，交回调用方"""
        with mock.patch.object(qq_flow, '_ai_says_cancel') as decide:
            self.assertFalse(qq_flow.handle_message('u1', '路人', '我要退单'))
        decide.assert_not_called()

    def test_non_taker_with_serial_cancel_is_handled_as_cancel(self):
        """陌生 QQ 拿着我们的单号说要撤单：也必须按退单处理，
        绝不能落到「报单号 → 去平台接单」分支（那会真的去接单 / 回滚）"""
        self._record()
        with mock.patch.object(qq_flow, '_ai_says_cancel', return_value=True), \
             mock.patch.object(qq_flow, '_handle_cancel_intent',
                               return_value=(True, 'ok')) as cancel, \
             mock.patch.object(qq_flow, '_handle_serial') as serial_handler:
            self.assertTrue(qq_flow.handle_message('u2', '路人', f'{SERIAL} 撤单吧'))
        cancel.assert_called_once()
        serial_handler.assert_not_called()

    def test_handle_message_ignores_normal_talk(self):
        """打手正常聊天（未提退单、也无待确认的退单）不会触发任何退单判定"""
        _mark_taker('u1')
        with mock.patch.object(qq_flow, '_ai_says_cancel') as decide, \
             mock.patch.object(qq_flow, '_ai_confirms_cancel') as confirm, \
             mock.patch.object(qq_flow, '_ai_reply', return_value=(True, '好的')):
            self.assertTrue(qq_flow.handle_message('u1', '打手', '我这边还在打呢'))
        decide.assert_not_called()
        confirm.assert_not_called()

    # ---------- 二次确认：靠状态 + 上下文认，不靠关键词 ----------

    def test_pending_cancel_record_by_serial(self):
        record = self._record(booster_cancel_asked=True)
        self.assertEqual(qq_flow._pending_cancel_record('u1', SERIAL), record)

    def test_pending_cancel_record_by_qq(self):
        record = self._record(booster_cancel_asked=True)
        self.assertEqual(qq_flow._pending_cancel_record('u1'), record)

    def test_pending_cancel_record_none_when_not_asked(self):
        self._record()                                  # 还没劝阻过
        self.assertIsNone(qq_flow._pending_cancel_record('u1', SERIAL))
        self.assertIsNone(qq_flow._pending_cancel_record('u1'))

    def test_pending_cancel_record_none_when_already_notified(self):
        self._record(booster_cancel_asked=True, booster_cancel_notified=True)
        self.assertIsNone(qq_flow._pending_cancel_record('u1', SERIAL))

    def test_short_confirmation_triggers_notify(self):
        """二次确认只有一个「退」字（粗筛词根本命中不了）→ 仍要按上下文落库 + 通知"""
        self._record(booster_cancel_asked=True)
        with mock.patch.object(qq_flow, '_ai_confirms_cancel', return_value=True) as confirm, \
             mock.patch.object(qq_flow, '_looks_like_cancel') as coarse, \
             mock.patch.object(qq_flow, '_handle_cancel_confirm',
                               return_value=(True, 'ok')) as handler:
            self.assertTrue(qq_flow.handle_message('u1', '打手', '退'))
        confirm.assert_called_once()
        coarse.assert_not_called()          # 走状态判定，不再依赖粗筛词
        handler.assert_called_once()

    def test_pending_but_not_confirming_falls_through(self):
        """已劝阻过，但他这条不是确认（比如问别的）→ 不落库、不通知"""
        _mark_taker('u1')
        self._record(booster_cancel_asked=True)
        with mock.patch.object(qq_flow, '_ai_confirms_cancel', return_value=False), \
             mock.patch('API.apis.order_migration.utils.notify_booster_cancel') as notify, \
             mock.patch.object(qq_flow, '_ai_reply', return_value=(True, '好的')):
            self.assertTrue(qq_flow.handle_message('u1', '打手', '我这边还在打呢'))
        notify.assert_not_called()

    def test_first_cancel_remembers_booster_qq(self):
        """首次退单即使消息没带 QQ，也要把这份 QQ 记到记录上（供后续二次确认认人）"""
        record = self._record(booster_qq='')            # 记录上还没有 QQ
        with mock.patch.object(qq_flow, '_ai_reply', return_value=(True, '再想想？')), \
             mock.patch('API.apis.order_migration.utils.notify_booster_cancel'):
            qq_flow._handle_cancel_intent('u9', '打手', '我不打了', SERIAL)
        record.refresh_from_db()
        self.assertEqual(record.booster_qq, 'u9')
        self.assertTrue(record.booster_cancel_asked)

