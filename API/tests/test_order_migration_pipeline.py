"""代练搬单流水线单元测试（抓单 / 发单 / 监控被接单 / 接单兜底）

全程 mock 平台调用，不触网、不产生真实订单。
"""
import os
from unittest import mock

from django.test import TestCase

from API.apis.order_migration import utils as om
from API.models import MigrationStatus, OrderMigration, OrderMigrationSetting


def _candidate(**overrides):
    cand = {
        'game_id': '1', 'leveling_type_name': '排位', 'region_name': '安卓QQ',
        'title': '星耀5 1星-星耀3 1星', 'hour': 5, 'amount': 31.2,
        'security_deposit': 31.2, 'efficiency_deposit': 31.2,
        'dlt_price': 43.0, 'dlt_cost': 4, 'dlt_serial_no': 'A1',
        'dlt_zone': '安卓QQ', 'dlt_time_limit': 5, 'dlt_ensure': 60.0,
    }
    cand.update(overrides)
    return cand


class FetchCandidatesTests(TestCase):
    @mock.patch('API.apis.order_migration.utils._fetch_dlt_orders')
    def test_maps_and_skips_bad_zone(self, mocked):
        mocked.return_value = ([
            {'SerialNo': 'A1', 'Title': '星耀5 1星-星耀3 1星', 'Price': 43,
             'Zone': '苹果QQ', 'TimeLimit': 5, 'Ensure': 100.0},
            {'SerialNo': 'A2', 'Title': 'x', 'Price': 29, 'Zone': 'PC端', 'TimeLimit': 3},
        ], [])
        ok, candidates = om.fetch_candidates()
        self.assertTrue(ok)
        self.assertEqual([c['dlt_serial_no'] for c in candidates], ['A1'])
        self.assertEqual(candidates[0]['amount'], 31.2)
        self.assertEqual(candidates[0]['region_name'], '苹果QQ')
        self.assertEqual(candidates[0]['dlt_ensure'], 100.0)

    @mock.patch('API.apis.order_migration.utils._fetch_dlt_orders')
    def test_skips_already_known(self, mocked):
        OrderMigration.objects.create(dlt_serial_no='A1', dlt_title='t', dlt_price=43,
                                      dlt_zone='苹果QQ', dlt_time_limit=5)
        mocked.return_value = ([
            {'SerialNo': 'A1', 'Title': 't', 'Price': 43, 'Zone': '苹果QQ', 'TimeLimit': 5},
        ], [])
        ok, candidates = om.fetch_candidates()
        self.assertEqual(candidates, [])

    @mock.patch('API.apis.order_migration.utils._fetch_dlt_orders')
    def test_price_filter(self, mocked):
        mocked.return_value = ([
            {'SerialNo': 'A1', 'Title': 't', 'Price': 10, 'Zone': '安卓QQ', 'TimeLimit': 3},
        ], [])
        with mock.patch.dict(os.environ, {om.PRICE_MIN_ENV: '20'}):
            ok, candidates = om.fetch_candidates()
        self.assertEqual(candidates, [])

    @mock.patch('API.apis.order_migration.utils._fetch_dlt_orders')
    def test_keyword_filter(self, mocked):
        mocked.return_value = ([
            {'SerialNo': 'A1', 'Title': '我的测试单 星耀5 1星-星耀3 1星', 'Price': 43,
             'Zone': '苹果QQ', 'TimeLimit': 5},
            {'SerialNo': 'A2', 'Title': '别人的单', 'Price': 43, 'Zone': '苹果QQ', 'TimeLimit': 5},
        ], [])
        setting = OrderMigrationSetting.get_solo()
        setting.keyword = '我的测试单'
        setting.save()
        ok, candidates = om.fetch_candidates()
        self.assertEqual([c['dlt_serial_no'] for c in candidates], ['A1'])

    @mock.patch('API.apis.order_migration.utils._fetch_dlt_orders')
    def test_keyword_matches_serial(self, mocked):
        mocked.return_value = ([
            {'SerialNo': '10718796259937643683', 'Title': '自定义发布 星耀5 1星-星耀3 1星', 'Price': 2,
             'Zone': '安卓QQ', 'TimeLimit': 2},
        ], [])
        setting = OrderMigrationSetting.get_solo()
        setting.keyword = '10718796259937643683'
        setting.save()
        ok, candidates = om.fetch_candidates()
        self.assertEqual([c['dlt_serial_no'] for c in candidates], ['10718796259937643683'])


class PublishCandidateTests(TestCase):
    def test_dry_run_writes_nothing(self):
        ok, preview = om.publish_candidate(_candidate(), dry_run=True)
        self.assertTrue(ok)
        self.assertTrue(preview['dry_run'])
        self.assertEqual(OrderMigration.objects.count(), 0)

    @mock.patch('API.apis.order_migration.utils.our_qq', return_value='')
    def test_without_qq(self, _qq):
        ok, msg = om.publish_candidate(_candidate())
        self.assertFalse(ok)
        self.assertIn(om.QQ_ENV, str(msg))

    @mock.patch('API.apis.DaiLianWanZi.utils.publish_order')
    @mock.patch('API.apis.order_migration.utils.our_qq', return_value='123456')
    def test_publish_success(self, _qq, mocked_pub):
        mocked_pub.return_value = (True, {'code': 0, 'message': 'ok',
                                          'data': {'trade_no': 'WZ1', 'status': 2}})
        ok, record = om.publish_candidate(_candidate())
        self.assertTrue(ok)
        self.assertEqual(record.dlwz_trade_no, 'WZ1')
        self.assertEqual(record.status, MigrationStatus.PUBLISHED)
        self.assertEqual(mocked_pub.call_args.kwargs['game_account'], '123456')
        self.assertEqual(mocked_pub.call_args.kwargs['title'], '星耀5 1星-星耀3 1星')
        self.assertEqual(mocked_pub.call_args.kwargs['take_level'], -1)
        self.assertEqual(mocked_pub.call_args.kwargs['use_tier'], False)

    @mock.patch('API.apis.DaiLianWanZi.utils.publish_order')
    @mock.patch('API.apis.order_migration.utils.our_qq', return_value='123456')
    def test_publish_failure_marks_failed(self, _qq, mocked_pub):
        mocked_pub.return_value = (True, {'code': 1, 'message': '余额不足', 'data': None})
        ok, record = om.publish_candidate(_candidate())
        self.assertFalse(ok)
        self.assertEqual(record.status, MigrationStatus.FAILED)

    @mock.patch('API.apis.DaiLianWanZi.utils.publish_order')
    @mock.patch('API.apis.order_migration.utils.our_qq', return_value='123456')
    def test_publish_network_error_keeps_publishing(self, _qq, mocked_pub):
        # 请求异常（超时等）：丸子是否收到不确定 → 保持「发单中」，交启动对账判定
        mocked_pub.return_value = (False, '请求超时')
        ok, record = om.publish_candidate(_candidate())
        self.assertFalse(ok)
        self.assertEqual(record.status, MigrationStatus.PUBLISHING)
        self.assertIn('发单结果未知', record.message)


class TakenDetectionTests(TestCase):
    def test_is_taken(self):
        self.assertTrue(om._is_taken({'takerUsername': '小影api'}))
        self.assertTrue(om._is_taken({'takeFrontendParentUserId': 107456384}))
        self.assertFalse(om._is_taken({'takerUsername': '', 'assignTakerList': []}))
        self.assertFalse(om._is_taken({}))

    @mock.patch('API.apis.DaiLianWanZi.utils.get_my_orders')
    def test_poll_orders(self, mocked):
        mocked.return_value = (True, {'code': 0, 'message': 'Success', 'data': {
            'code': 10000, 'data': {'ordersList': [{'tradeNo': 'WZ1', 'status': 14}]}}})
        ok, orders = om.poll_dlwz_orders()
        self.assertTrue(ok)
        self.assertIn('WZ1', orders)


class TakeOnDltTests(TestCase):
    def _record(self):
        return OrderMigration.objects.create(
            dlt_serial_no='A1', dlt_title='t', dlt_price=29, dlt_zone='安卓QQ',
            dlt_time_limit=3, dlwz_trade_no='WZ1', status=MigrationStatus.PUBLISHED)

    @mock.patch('API.apis.DaiLianTong.utils.get_order_detail')
    @mock.patch('API.apis.DaiLianTong.utils.receive_order')
    def test_take_success(self, recv, detail):
        recv.return_value = (True, {'code': 0, 'message': 'ok', 'data': {}})
        detail.return_value = (True, {'code': 0, 'message': 'ok',
                                      'data': {'GameAcc': 'acc1', 'GamePass': 'p1', 'Actor': '角色A',
                                               'Zone': '安卓QQ', 'Server': '默认服'}})
        record = self._record()
        self.assertTrue(om._take_on_dlt(record))
        record.refresh_from_db()
        self.assertEqual(record.status, MigrationStatus.TAKEN)
        self.assertIn('acc1', record.account_info)
        self.assertIn('角色A', record.account_info)

    @mock.patch('API.apis.DaiLianWanZi.utils.cancel_order')
    @mock.patch('API.apis.DaiLianTong.utils.receive_order')
    def test_take_failure_rolls_back(self, recv, cancel):
        recv.return_value = (True, {'code': 1, 'message': '该订单已被接手'})
        cancel.return_value = (True, {'code': 0, 'message': 'ok'})
        record = self._record()
        self.assertFalse(om._take_on_dlt(record))
        record.refresh_from_db()
        self.assertEqual(record.status, MigrationStatus.FAILED)
        self.assertIn('已撤单', record.message)
        cancel.assert_called_once_with('WZ1')

    @mock.patch('API.apis.order_migration.utils._revoke_dlwz')
    @mock.patch('API.apis.DaiLianWanZi.utils.cancel_order')
    @mock.patch('API.apis.DaiLianTong.utils.receive_order')
    def test_take_failure_revokes_when_cancel_fails(self, recv, cancel, revoke):
        recv.return_value = (True, {'code': 1, 'message': '可操作资金不足，不能接手.'})
        cancel.return_value = (True, {'code': 1, 'message': '当前订单状态不支持取消'})
        revoke.return_value = (True, {'code': 0})
        record = self._record()
        self.assertFalse(om._take_on_dlt(record))
        record.refresh_from_db()
        self.assertEqual(record.status, MigrationStatus.FAILED)
        self.assertIn('申请撤销', record.message)
        revoke.assert_called_once_with('WZ1', '抢接失败，申请撤销')


class ReconcileTests(TestCase):
    """启动对账：把「发单中」记录与丸子上真实订单对齐"""

    def _pending(self, **overrides):
        fields = dict(dlt_serial_no='A1', dlt_title='星耀5 1星-星耀3 1星', dlt_price=43,
                      dlt_zone='安卓QQ', dlt_time_limit=5, amount=31.2,
                      status=MigrationStatus.PUBLISHING)
        fields.update(overrides)
        return OrderMigration.objects.create(**fields)

    def test_no_pending_is_noop(self):
        result = om.reconcile_on_startup()
        self.assertEqual(result, {'checked': 0, 'recovered': 0, 'failed': 0, 'errors': []})

    @mock.patch('API.apis.order_migration.utils.poll_dlwz_orders')
    def test_recovers_unique_match(self, poll):
        record = self._pending()
        poll.return_value = (True, {
            'WZ1': {'tradeNo': 'WZ1', 'title': '星耀5 1星-星耀3 1星', 'amount': 31.2, 'status': 2},
            'WZ2': {'tradeNo': 'WZ2', 'title': '别的标题', 'amount': 9.9, 'status': 2},
        })
        result = om.reconcile_on_startup()
        self.assertEqual((result['checked'], result['recovered'], result['failed']), (1, 1, 0))
        record.refresh_from_db()
        self.assertEqual(record.dlwz_trade_no, 'WZ1')
        self.assertEqual(record.status, MigrationStatus.PUBLISHED)

    @mock.patch('API.apis.order_migration.utils.poll_dlwz_orders')
    def test_no_match_marks_failed(self, poll):
        record = self._pending()
        poll.return_value = (True, {'WZ9': {'tradeNo': 'WZ9', 'title': 'x',
                                            'amount': 1.0, 'status': 2}})
        result = om.reconcile_on_startup()
        self.assertEqual(result['failed'], 1)
        record.refresh_from_db()
        self.assertEqual(record.status, MigrationStatus.FAILED)
        self.assertIn('无法唯一确认', record.message)

    @mock.patch('API.apis.order_migration.utils.poll_dlwz_orders')
    def test_ambiguous_match_marks_failed(self, poll):
        record = self._pending()
        same = {'title': '星耀5 1星-星耀3 1星', 'amount': 31.2, 'status': 2}
        poll.return_value = (True, {'WZ1': dict(same, tradeNo='WZ1'),
                                    'WZ2': dict(same, tradeNo='WZ2')})
        result = om.reconcile_on_startup()
        self.assertEqual(result['failed'], 1)
        record.refresh_from_db()
        self.assertEqual(record.status, MigrationStatus.FAILED)

    @mock.patch('API.apis.order_migration.utils.poll_dlwz_orders')
    def test_poll_failure_leaves_record_untouched(self, poll):
        record = self._pending()
        poll.return_value = (False, '请求超时')
        result = om.reconcile_on_startup()
        self.assertEqual(result['recovered'], 0)
        self.assertEqual(result['failed'], 0)
        self.assertTrue(result['errors'])
        record.refresh_from_db()
        self.assertEqual(record.status, MigrationStatus.PUBLISHING)


class CancelAllPendingTests(TestCase):
    """一键撤销全部待接单：撤销丸子单 + 释放代练通双金预扣"""

    def _record(self, serial='A1', trade='WZ1', status=MigrationStatus.PUBLISHED, ensure=60.0):
        return OrderMigration.objects.create(
            dlt_serial_no=serial, dlt_title='t', dlt_price=29, dlt_zone='安卓QQ',
            dlt_time_limit=3, dlt_ensure=ensure, dlwz_trade_no=trade, amount=31.2, status=status)

    @mock.patch('API.apis.DaiLianWanZi.utils.cancel_order')
    def test_cancels_all_and_releases_reservation(self, cancel):
        cancel.return_value = (True, {'code': 0, 'message': 'ok'})
        r1 = self._record('A1', 'WZ1', ensure=60.0)
        r2 = self._record('A2', 'WZ2', ensure=40.0)
        self.assertEqual(om.reserved_dlt_deposit(), 100.0)

        result = om.cancel_all_pending()

        self.assertEqual(result['total'], 2)
        self.assertEqual(result['cancelled'], 2)
        self.assertEqual(cancel.call_count, 2)
        self.assertEqual(om.reserved_dlt_deposit(), 0.0)      # 预扣已释放
        r1.refresh_from_db()
        r2.refresh_from_db()
        self.assertEqual(r1.status, MigrationStatus.CANCELLED)
        self.assertEqual(r2.status, MigrationStatus.CANCELLED)

    @mock.patch('API.apis.order_migration.utils._revoke_dlwz')
    @mock.patch('API.apis.DaiLianWanZi.utils.cancel_order')
    def test_falls_back_to_revoke(self, cancel, revoke):
        cancel.return_value = (True, {'code': 1, 'message': '当前订单状态不支持取消'})
        revoke.return_value = (True, {'code': 0})
        self._record()
        result = om.cancel_all_pending()
        self.assertEqual(result['revoked'], 1)
        self.assertEqual(result['failed'], 0)
        revoke.assert_called_once()

    @mock.patch('API.apis.order_migration.utils._revoke_dlwz',
                return_value=(False, '未配置撤销凭证图URL'))
    @mock.patch('API.apis.DaiLianWanZi.utils.cancel_order')
    def test_counts_failure(self, cancel, revoke):
        cancel.return_value = (True, {'code': 1, 'message': '当前订单状态不支持取消'})
        record = self._record()
        result = om.cancel_all_pending()
        self.assertEqual(result['failed'], 1)
        self.assertTrue(result['errors'])
        record.refresh_from_db()
        self.assertEqual(record.status, MigrationStatus.CANCELLED)   # 仍移出待接单 → 释放占用

    @mock.patch('API.apis.DaiLianWanZi.utils.cancel_order')
    def test_publishing_without_trade_no_just_releases(self, cancel):
        self._record('A3', trade='', status=MigrationStatus.PUBLISHING)
        result = om.cancel_all_pending()
        self.assertEqual(result['cancelled'], 1)
        cancel.assert_not_called()
        self.assertEqual(om.reserved_dlt_deposit(), 0.0)

    def test_no_pending_is_noop(self):
        result = om.cancel_all_pending()
        self.assertEqual(result['total'], 0)


class DltOrderStateTests(TestCase):
    """先查代练通原单：Status=11（未接手）才算仍可接；原单已不存在也算确定不可接"""

    @mock.patch('API.apis.DaiLianTong.utils.get_order_detail')
    def test_waiting_status_is_available(self, detail):
        detail.return_value = (True, {'code': 0, 'message': 'ok', 'data': {'Status': 11}})
        state_ok, info = om.dlt_order_state('A1')
        self.assertTrue(state_ok)
        self.assertTrue(info['available'])
        self.assertEqual(info['status'], 11)
        self.assertEqual(detail.call_args.kwargs.get('is_publish'), '1')

    @mock.patch('API.apis.DaiLianTong.utils.get_order_detail')
    def test_taken_or_cancelled_not_available(self, detail):
        for status in (12, 16, 17):
            detail.return_value = (True, {'code': 0, 'message': 'ok', 'data': {'Status': status}})
            state_ok, info = om.dlt_order_state('A1')
            self.assertTrue(state_ok, f'Status={status}')
            self.assertFalse(info['available'], f'Status={status}')
            self.assertEqual(info['status'], status)

    @mock.patch('API.apis.DaiLianTong.utils.get_order_detail')
    def test_missing_order_is_not_available(self, detail):
        # 「没有找到该订单」= 原单已被撤销 / 删除（全站查不到）→ 确定不可接，应回滚
        detail.return_value = (True, {'code': 1, 'message': '没有找到该订单', 'data': None})
        state_ok, info = om.dlt_order_state('A1')
        self.assertTrue(state_ok)
        self.assertFalse(info['available'])
        self.assertIn('原单已不存在', info['reason'])

    @mock.patch('API.apis.DaiLianTong.utils.get_order_detail')
    def test_request_failure_is_inconclusive(self, detail):
        # 查询失败（网络抖动等）不能据此回滚：state_ok=False
        detail.return_value = (False, '请求超时')
        state_ok, info = om.dlt_order_state('A1')
        self.assertFalse(state_ok)
        self.assertIsNone(info['available'])

    @mock.patch('API.apis.DaiLianTong.utils.get_order_detail')
    def test_other_business_error_is_inconclusive(self, detail):
        detail.return_value = (True, {'code': 1, 'message': '参数错误'})
        state_ok, _info = om.dlt_order_state('A1')
        self.assertFalse(state_ok)

    @mock.patch('API.apis.DaiLianTong.utils.get_order_detail')
    def test_unparsable_status_is_inconclusive(self, detail):
        detail.return_value = (True, {'code': 0, 'message': 'ok', 'data': {'Status': None}})
        state_ok, _info = om.dlt_order_state('A1')
        self.assertFalse(state_ok)


class RunCycleTests(TestCase):
    """每轮流水线：取余额 → 随机抽单 → 逐条余额闸门发单 → 监控"""

    def setUp(self):
        # 默认两个平台的实时余额都充足；个别用例用装饰器覆盖成不足 / 查询失败
        for target, value in (
            ('API.apis.order_migration.utils.dlt_balance', (True, 1000.0)),
            ('API.apis.order_migration.utils.dlwz_balance', (True, 1000.0)),
        ):
            patcher = mock.patch(target, return_value=value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def _published_record(self, **overrides):
        fields = dict(dlt_serial_no='A1', dlt_title='t', dlt_price=29, dlt_zone='安卓QQ',
                      dlt_time_limit=3, dlt_ensure=62.4, dlwz_trade_no='WZ1',
                      status=MigrationStatus.PUBLISHED)
        fields.update(overrides)
        return OrderMigration.objects.create(**fields)

    @mock.patch('API.apis.order_migration.utils.notify_taken')
    @mock.patch('API.apis.order_migration.utils.dlt_order_state',
                return_value=(True, {'available': True, 'status': 11, 'reason': '未接手（可接）'}))
    @mock.patch('API.apis.order_migration.utils._take_on_dlt')
    @mock.patch('API.apis.order_migration.utils.poll_dlwz_orders')
    @mock.patch('API.apis.order_migration.utils.publish_candidate')
    @mock.patch('API.apis.order_migration.utils.fetch_candidates')
    def test_cycle_marks_taker_joined_without_take(self, fetch, publish, poll, take,
                                                   dlt_state, notify):
        """丸子被接单 → 只置「待报单号」并通知，**不再自动去代练通接单**（等打手 QQ 报单号）"""
        fetch.return_value = (True, [_candidate()])
        publish.return_value = (True, mock.Mock())
        record = self._published_record()
        poll.return_value = (True, {'WZ1': {'tradeNo': 'WZ1', 'status': 3,
                                            'takerUsername': 'x'}})
        summary = om.run_cycle(publish_limit=1)
        self.assertEqual((summary['fetched'], summary['published'], summary['taker_joined']),
                         (1, 1, 1))
        self.assertEqual(summary['taken'], 0)
        take.assert_not_called()
        notify.assert_called_once()
        record.refresh_from_db()
        self.assertEqual(record.status, MigrationStatus.TAKER_JOINED)

    @mock.patch('API.apis.order_migration.utils.notify_taken')
    @mock.patch('API.apis.order_migration.utils.poll_dlwz_orders', return_value=(True, {}))
    @mock.patch('API.apis.order_migration.utils._cancel_dlwz')
    @mock.patch('API.apis.order_migration.utils.publish_candidate')
    @mock.patch('API.apis.order_migration.utils.fetch_candidates')
    @mock.patch('API.apis.order_migration.utils.dlt_order_state',
                return_value=(True, {'available': False, 'status': 12, 'reason': '正在代练'}))
    def test_cycle_rolls_back_taker_joined_when_dlt_gone(self, dlt_state, fetch, publish,
                                                        cancel, poll, notify):
        """已被打手接单、还在等他报单号时，代练通原单若被抢走 → 同样要回滚丸子那笔"""
        fetch.return_value = (True, [])
        cancel.return_value = (True, {'code': 0, 'message': 'ok'})
        record = self._published_record(status=MigrationStatus.TAKER_JOINED)
        summary = om.run_cycle(publish_limit=1)
        self.assertEqual(summary['rollback'], 1)
        record.refresh_from_db()
        self.assertEqual(record.status, MigrationStatus.FAILED)
        notify.assert_not_called()             # 原单都没了，不必再通知去打手交接

    @mock.patch('API.apis.order_migration.utils.poll_dlwz_orders', return_value=(True, {}))
    @mock.patch('API.apis.order_migration.utils._take_on_dlt')
    @mock.patch('API.apis.order_migration.utils._cancel_dlwz')
    @mock.patch('API.apis.order_migration.utils.publish_candidate')
    @mock.patch('API.apis.order_migration.utils.fetch_candidates')
    @mock.patch('API.apis.order_migration.utils.dlt_order_state',
                return_value=(True, {'available': False, 'status': 12, 'reason': '正在代练'}))
    def test_cycle_rolls_back_when_dlt_unavailable(self, dlt_state, fetch, publish,
                                                  cancel, take, poll):
        # 代练通原单已被接走 / 已撤销 / 原单已不存在：立刻回滚丸子那笔，不会再去代练通接单
        fetch.return_value = (True, [])
        cancel.return_value = (True, {'code': 0, 'message': 'ok'})
        record = self._published_record()
        summary = om.run_cycle(publish_limit=1)
        self.assertEqual(summary['rollback'], 1)
        self.assertEqual(summary['taken'], 0)
        record.refresh_from_db()
        self.assertEqual(record.status, MigrationStatus.FAILED)
        self.assertIn('无需再等', record.message)
        take.assert_not_called()
        # 监控日志：抬头 1 行 + 每笔 1 行，外加「验收巡检 / 结算巡检」各 1 行
        self.assertEqual(len(summary['monitor']), 4)
        self.assertTrue(any('已回滚撤单' in line for line in summary['monitor']))
        self.assertTrue(any('验收巡检' in line for line in summary['monitor']))

    @mock.patch('API.apis.order_migration.utils.poll_dlwz_orders')
    @mock.patch('API.apis.order_migration.utils.publish_candidate')
    @mock.patch('API.apis.order_migration.utils.fetch_candidates')
    @mock.patch('API.apis.order_migration.utils.dlt_order_state',
                return_value=(False, {'available': None, 'status': None, 'reason': '请求超时'}))
    def test_cycle_skips_rollback_when_dlt_query_fails(self, dlt_state, fetch, publish, poll):
        # 代练通查询失败（可能是网络抖动）不能误撤：记录 error、跳过本轮该笔
        fetch.return_value = (True, [])
        record = self._published_record()
        poll.return_value = (True, {})
        summary = om.run_cycle(publish_limit=1)
        self.assertEqual(summary['rollback'], 0)
        self.assertTrue(any('代练通状态查询失败' in e for e in summary['errors']))
        self.assertTrue(any('本轮跳过' in line for line in summary['monitor']))
        record.refresh_from_db()
        self.assertEqual(record.status, MigrationStatus.PUBLISHED)

    @mock.patch('API.apis.order_migration.utils.publish_candidate')
    @mock.patch('API.apis.order_migration.utils.fetch_candidates')
    def test_cycle_dry_run(self, fetch, publish):
        fetch.return_value = (True, [_candidate()])
        publish.return_value = (True, {'dry_run': True})
        summary = om.run_cycle(publish_limit=1, dry_run=True)
        self.assertEqual(summary['fetched'], 1)
        self.assertEqual(summary['published'], 0)

    # ---------- 余额闸门 ----------

    @mock.patch('API.apis.order_migration.utils.publish_candidate')
    @mock.patch('API.apis.order_migration.utils.fetch_candidates')
    @mock.patch('API.apis.order_migration.utils.dlt_balance', return_value=(False, '请求超时'))
    def test_skips_publish_when_balance_query_fails(self, dlt_bal, fetch, publish):
        # 余额查不到 → 本轮不发单（只监控）
        fetch.return_value = (True, [_candidate()])
        summary = om.run_cycle(publish_limit=1)
        self.assertEqual(summary['published'], 0)
        publish.assert_not_called()
        self.assertTrue(any('余额查询失败' in e for e in summary['errors']))

    @mock.patch('API.apis.order_migration.utils.publish_candidate')
    @mock.patch('API.apis.order_migration.utils.fetch_candidates')
    @mock.patch('API.apis.order_migration.utils.dlt_balance', return_value=(True, 5.0))
    def test_stops_when_dlt_balance_insufficient(self, dlt_bal, fetch, publish):
        # 代练通可用 5 < 本单双金 10 → 中断本轮，不发
        fetch.return_value = (True, [_candidate(dlt_ensure=10.0)])
        summary = om.run_cycle(publish_limit=1)
        self.assertEqual(summary['published'], 0)
        publish.assert_not_called()
        self.assertTrue(any('代练通余额不足' in e for e in summary['errors']))

    @mock.patch('API.apis.order_migration.utils.publish_candidate')
    @mock.patch('API.apis.order_migration.utils.fetch_candidates')
    @mock.patch('API.apis.order_migration.utils.dlwz_balance', return_value=(True, 1.0))
    def test_stops_when_dlwz_balance_insufficient(self, dlwz_bal, fetch, publish):
        # 丸子可用 1 < 本单发布价 31.2 → 中断本轮，不发
        fetch.return_value = (True, [_candidate(amount=31.2)])
        summary = om.run_cycle(publish_limit=1)
        self.assertEqual(summary['published'], 0)
        publish.assert_not_called()
        self.assertTrue(any('丸子余额不足' in e for e in summary['errors']))

    @mock.patch('API.apis.order_migration.utils.publish_candidate')
    @mock.patch('API.apis.order_migration.utils.fetch_candidates')
    @mock.patch('API.apis.order_migration.utils.dlt_balance', return_value=(True, 15.0))
    def test_refunds_after_publish_failure(self, dlt_bal, fetch, publish):
        # 两单各押 10：第一单发失败要退还 10，第二单才够继续发；失败不中断
        fetch.return_value = (True, [
            _candidate(dlt_serial_no='A1', dlt_ensure=10.0),
            _candidate(dlt_serial_no='A2', dlt_ensure=10.0),
        ])
        publish.side_effect = [(False, '发单失败'), (True, mock.Mock())]
        summary = om.run_cycle(publish_limit=5)
        self.assertEqual(publish.call_count, 2)
        self.assertEqual(summary['published'], 1)

    @mock.patch('API.apis.order_migration.utils.poll_dlwz_orders', return_value=(True, {}))
    @mock.patch('API.apis.order_migration.utils.dlt_order_state',
                return_value=(True, {'available': True, 'status': 11, 'reason': '未接手（可接）'}))
    @mock.patch('API.apis.order_migration.utils.publish_candidate')
    @mock.patch('API.apis.order_migration.utils.fetch_candidates')
    @mock.patch('API.apis.order_migration.utils.dlt_balance', return_value=(True, 105.0))
    def test_reserves_published_deposit(self, dlt_bal, fetch, publish, dlt_avail, poll):
        # 已发布未完成记录占用代练通双金 100：可用 105 − 100 = 5 < 10，故新单不发
        fetch.return_value = (True, [_candidate(dlt_ensure=10.0)])
        self._published_record(dlt_ensure=100.0)
        summary = om.run_cycle(publish_limit=1)
        self.assertEqual(summary['published'], 0)
        publish.assert_not_called()
        self.assertTrue(any('代练通余额不足' in e for e in summary['errors']))


class NotifyTakenTests(TestCase):
    """被接单通知：Server酱手机推送 + 邮件"""

    def _record(self):
        return OrderMigration.objects.create(
            dlt_serial_no='A1', dlt_title='t', dlt_price=29, dlt_zone='安卓QQ',
            dlt_time_limit=3, dlwz_trade_no='WZ1', status=MigrationStatus.TAKER_JOINED)

    @mock.patch('API.apis.push.serverchan.utils.send')
    def test_pushes_to_phone(self, push):
        push.return_value = (True, {'pushid': 'p1'})
        om.notify_taken(self._record())
        push.assert_called_once()
        title, body = push.call_args.args[:2]
        self.assertIn('WZ1', title)
        self.assertLessEqual(len(title), 32)            # Server酱 标题上限 32
        self.assertIn('WZ1', body)

    @mock.patch('API.apis.push.email.utils.send_email')
    @mock.patch('API.apis.push.serverchan.utils.send', return_value=(True, {'pushid': 'p1'}))
    def test_sends_mail_when_enabled(self, push, mail):
        setting = OrderMigrationSetting.get_solo()
        setting.notify_mail = True
        setting.notify_mail_to = 'a@b.com'
        setting.save()
        mail.return_value = (True, 'ok')
        om.notify_taken(self._record())
        mail.assert_called_once()
        self.assertEqual(mail.call_args.args[2], ['a@b.com'])

    @mock.patch('API.apis.push.email.utils.send_email')
    @mock.patch('API.apis.push.serverchan.utils.send',
                return_value=(False, {'message': '未配置 SendKey'}))
    def test_push_failure_does_not_block_mail(self, push, mail):
        setting = OrderMigrationSetting.get_solo()
        setting.notify_mail = True
        setting.notify_mail_to = 'a@b.com'
        setting.save()
        mail.return_value = (True, 'ok')
        om.notify_taken(self._record())
        mail.assert_called_once()

    @mock.patch('API.apis.push.email.utils.send_email')
    @mock.patch('API.apis.push.serverchan.utils.send', return_value=(True, {'pushid': 'p1'}))
    def test_mail_off_sends_no_mail(self, push, mail):
        setting = OrderMigrationSetting.get_solo()
        setting.notify_mail = False
        setting.save()
        om.notify_taken(self._record())
        mail.assert_not_called()


class TakenFeedTests(TestCase):
    """被接单语音提醒：只在「丸子被接单」(taker_joined) 那一刻响一次"""

    def _record(self, status, serial='A1', **overrides):
        fields = dict(dlt_serial_no=serial, dlt_title='t', dlt_price=29, dlt_zone='安卓QQ',
                      dlt_time_limit=3, dlwz_trade_no='WZ1', status=status)
        fields.update(overrides)
        return OrderMigration.objects.create(**fields)

    def test_fires_for_taker_joined(self):
        from django.utils import timezone
        after = timezone.now() - timezone.timedelta(seconds=5)
        self._record(MigrationStatus.TAKER_JOINED)
        _cursor, items = om.taken_feed(after)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['trade_no'], 'WZ1')

    def test_does_not_fire_for_later_stages(self):
        """代练通接单 / 转传首图 / 申请完单等后续更新都不该再响"""
        from django.utils import timezone
        after = timezone.now() - timezone.timedelta(seconds=5)
        self._record(MigrationStatus.TAKEN)
        self._record(MigrationStatus.WAITING_ACCEPT, serial='A2')
        _cursor, items = om.taken_feed(after)
        self.assertEqual(items, [])


class SettleCycleTests(TestCase):
    """结算巡检：代练通验收结算 → 丸子自动同意验收、给打手结账"""

    def _record(self, **overrides):
        fields = dict(dlt_serial_no='A1', dlt_title='t', dlt_price=29, dlt_zone='安卓QQ',
                      dlt_time_limit=3, dlwz_trade_no='WZ1',
                      status=MigrationStatus.WAITING_ACCEPT)
        fields.update(overrides)
        return OrderMigration.objects.create(**fields)

    def test_no_waiting_accept_records(self):
        self.assertEqual(om._settle_cycle(), ['结算巡检：本轮无「等待验收中」记录'])

    @mock.patch('API.apis.order_migration.utils.dlt_order_state',
                return_value=(False, {'available': None, 'status': None, 'reason': '请求超时'}))
    def test_query_failure_retries(self, dlt_state):
        record = self._record()
        lines = om._settle_cycle()
        record.refresh_from_db()
        self.assertEqual(record.status, MigrationStatus.WAITING_ACCEPT)
        self.assertTrue(any('代练通状态查询失败' in line for line in lines))

    @mock.patch('API.apis.order_migration.utils.dlt_order_state',
                return_value=(True, {'available': False, 'status': 13, 'reason': '等待验收'}))
    def test_not_settled_yet_keeps_status(self, dlt_state):
        record = self._record()
        lines = om._settle_cycle()
        record.refresh_from_db()
        self.assertEqual(record.status, MigrationStatus.WAITING_ACCEPT)
        self.assertTrue(any('继续等老板验收' in line for line in lines))

    @mock.patch('API.apis.DaiLianWanZi.utils.accept_completion',
                return_value=(True, {'code': 0, 'message': 'Success'}))
    @mock.patch('API.apis.order_migration.utils.dlt_order_state',
                return_value=(True, {'available': False, 'status': 17, 'reason': '已结算'}))
    def test_settled_accepts_on_dlwz(self, dlt_state, accept):
        record = self._record()
        lines = om._settle_cycle()
        record.refresh_from_db()
        accept.assert_called_once_with('WZ1')
        self.assertEqual(record.status, MigrationStatus.SETTLED)
        self.assertTrue(any('打手已结账' in line for line in lines))

    @mock.patch('API.apis.DaiLianWanZi.utils.accept_completion',
                return_value=(False, '缺少支付密码'))
    @mock.patch('API.apis.order_migration.utils.dlt_order_state',
                return_value=(True, {'available': False, 'status': 17, 'reason': '已结算'}))
    def test_accept_failure_keeps_status(self, dlt_state, accept):
        record = self._record()
        lines = om._settle_cycle()
        record.refresh_from_db()
        self.assertEqual(record.status, MigrationStatus.WAITING_ACCEPT)
        self.assertTrue(any('丸子同意验收失败' in line for line in lines))


class PickImageTests(TestCase):
    """按 remark 从丸子图片列表里取图"""

    def test_picks_first_match(self):
        images = [{'remark': '首图', 'url': 'https://x/1.png'},
                  {'remark': '申请验收', 'url': 'https://x/2.png'},
                  {'remark': '申请验收', 'url': 'https://x/3.png'}]
        self.assertEqual(om._pick_image(images, om.IMG_REMARK_END), 'https://x/2.png')

    def test_returns_empty_when_absent(self):
        self.assertEqual(om._pick_image([{'remark': '首图', 'url': 'u'}], om.IMG_REMARK_END), '')
        self.assertEqual(om._pick_image(None, om.IMG_REMARK_FIRST), '')

    def test_first_image_ignores_remark(self):
        """打手不一定标「首图」，兜底取列表里第一张"""
        images = [{'remark': '上号图', 'url': 'https://x/1.png'},
                  {'remark': '申请验收', 'url': 'https://x/2.png'}]
        self.assertEqual(om._first_image(images), 'https://x/1.png')
        self.assertEqual(om._first_image([]), '')
        self.assertEqual(om._first_image(None), '')

    def test_first_image_can_exclude_end_image(self):
        """排除完单图后取第一张；全被排除则返回空"""
        images = [{'remark': '申请验收', 'url': 'https://x/2.png'},
                  {'remark': '上号图', 'url': 'https://x/3.png'}]
        self.assertEqual(
            om._first_image(images, exclude_remarks=(om.IMG_REMARK_END,)), 'https://x/3.png')
        self.assertEqual(
            om._first_image([{'remark': '申请验收', 'url': 'u'}],
                            exclude_remarks=(om.IMG_REMARK_END,)), '')


class DlwzOrderImagesTests(TestCase):
    """丸子订单图片列表：解析与失败兜底"""

    @mock.patch('API.apis.DaiLianWanZi.utils.get_order_images')
    def test_parses_nested_images(self, mocked):
        mocked.return_value = (True, {'code': 0, 'message': 'Success', 'data': {
            'code': 10000, 'data': {'imagesList': [{'url': 'u', 'remark': '首图'}]}}})
        ok, images = om._dlwz_order_images('WZ1')
        self.assertTrue(ok)
        self.assertEqual(images, [{'url': 'u', 'remark': '首图'}])

    @mock.patch('API.apis.DaiLianWanZi.utils.get_order_images')
    def test_api_failure_returns_reason(self, mocked):
        mocked.return_value = (False, '网络异常')
        ok, reason = om._dlwz_order_images('WZ1')
        self.assertFalse(ok)
        self.assertIn('网络异常', reason)

    @mock.patch('API.apis.DaiLianWanZi.utils.get_order_images')
    def test_business_failure_returns_reason(self, mocked):
        mocked.return_value = (True, {'code': 1, 'message': '登录已失效'})
        ok, reason = om._dlwz_order_images('WZ1')
        self.assertFalse(ok)
        self.assertIn('登录已失效', reason)


class AcceptCycleTests(TestCase):
    """已接单巡检：首图转传 + 丸子申请验收 → 转传完单图 → 记录转「等待验收中」"""

    def _taken_record(self, **overrides):
        fields = dict(dlt_serial_no='A1', dlt_title='t', dlt_price=29, dlt_zone='安卓QQ',
                      dlt_time_limit=3, dlwz_trade_no='WZ1', status=MigrationStatus.TAKEN)
        fields.update(overrides)
        return OrderMigration.objects.create(**fields)

    @staticmethod
    def _images(*items):
        return True, [{'url': u, 'remark': r, 'initiator': 2} for r, u in items]

    def test_no_taken_records(self):
        self.assertEqual(om._accept_cycle({'WZ1': {'status': 4}}),
                         ['验收巡检：本轮无「代练通已接单」记录'])

    def test_training_forwards_first_image(self):
        """丸子上手传了首图 → 立刻转传到代练通，并记下已转传"""
        record = self._taken_record()
        with mock.patch.object(om, '_dlwz_order_images',
                               return_value=self._images(('首图', 'https://x/1.png'))), \
             mock.patch('API.apis.DaiLianTong.utils.upload_first_image',
                        return_value=(True, {'code': 0})) as first, \
             mock.patch('API.apis.DaiLianTong.utils.upload_end_image') as end:
            lines = om._accept_cycle({'WZ1': {'tradeNo': 'WZ1', 'status': 3}})

        record.refresh_from_db()
        self.assertEqual(record.status, MigrationStatus.TAKEN)
        self.assertEqual(record.dlwz_first_image, 'https://x/1.png')
        self.assertEqual(record.dlt_first_image, 'https://x/1.png')
        first.assert_called_once_with('A1', ['https://x/1.png'])
        end.assert_not_called()
        self.assertTrue(any('首图：已转传到代练通' in line for line in lines))

    def test_unlabeled_first_image_still_forwarded(self):
        """打手没标「首图」也能识别：取第一张转传代练通"""
        record = self._taken_record()
        with mock.patch.object(om, '_dlwz_order_images',
                               return_value=self._images(('上号图', 'https://x/1.png'))), \
             mock.patch('API.apis.DaiLianTong.utils.upload_first_image',
                        return_value=(True, {'code': 0})) as first, \
             mock.patch('API.apis.DaiLianTong.utils.upload_end_image') as end:
            lines = om._accept_cycle({'WZ1': {'tradeNo': 'WZ1', 'status': 3}})

        record.refresh_from_db()
        self.assertEqual(record.dlt_first_image, 'https://x/1.png')
        first.assert_called_once_with('A1', ['https://x/1.png'])
        end.assert_not_called()
        self.assertTrue(any('首图：已转传到代练通' in line for line in lines))

    def test_remark_first_wins_over_list_order(self):
        """列表里先出现完单图，但只要有标注「首图」的，就用那一张"""
        record = self._taken_record()
        with mock.patch.object(om, '_dlwz_order_images',
                               return_value=self._images(('申请验收', 'https://x/2.png'),
                                                         ('首图', 'https://x/1.png'))), \
             mock.patch('API.apis.DaiLianTong.utils.upload_first_image',
                        return_value=(True, {'code': 0})) as first, \
             mock.patch('API.apis.DaiLianTong.utils.upload_end_image',
                        return_value=(True, {'code': 0})):
            om._accept_cycle({'WZ1': {'tradeNo': 'WZ1', 'status': 4}})

        record.refresh_from_db()
        self.assertEqual(record.dlt_first_image, 'https://x/1.png')   # 不是列表里更靠前的完单图
        first.assert_called_once_with('A1', ['https://x/1.png'])

    def test_first_image_not_forwarded_twice(self):
        """同一张首图只传一次，避免每轮重复挂到代练通"""
        self._taken_record(dlwz_first_image='https://x/1.png',
                           dlt_first_image='https://x/1.png')
        with mock.patch.object(om, '_dlwz_order_images',
                               return_value=self._images(('首图', 'https://x/1.png'))), \
             mock.patch('API.apis.DaiLianTong.utils.upload_first_image') as first:
            om._accept_cycle({'WZ1': {'tradeNo': 'WZ1', 'status': 3}})
        first.assert_not_called()

    def test_first_image_forward_failure_retries_next_round(self):
        record = self._taken_record()
        with mock.patch.object(om, '_dlwz_order_images',
                               return_value=self._images(('首图', 'https://x/1.png'))), \
             mock.patch('API.apis.DaiLianTong.utils.upload_first_image',
                        return_value=(True, {'code': 1, 'message': '订单状态已改变'})):
            lines = om._accept_cycle({'WZ1': {'tradeNo': 'WZ1', 'status': 3}})

        record.refresh_from_db()
        self.assertEqual(record.dlt_first_image, '')          # 失败不记录 → 下轮重试
        self.assertTrue(any('首图：转传代练通失败' in line for line in lines))

    def test_wait_accept_forwards_end_image(self):
        record = self._taken_record(dlt_first_image='https://x/1.png')
        with mock.patch.object(om, '_dlwz_order_images',
                               return_value=self._images(('首图', 'https://x/1.png'),
                                                         ('申请验收', 'https://x/2.png'))), \
             mock.patch('API.apis.DaiLianTong.utils.upload_first_image') as first, \
             mock.patch('API.apis.DaiLianTong.utils.upload_end_image',
                        return_value=(True, {'code': 0})) as end:
            lines = om._accept_cycle({'WZ1': {'tradeNo': 'WZ1', 'status': 4}})

        record.refresh_from_db()
        self.assertEqual(record.status, MigrationStatus.WAITING_ACCEPT)
        first.assert_not_called()                              # 首图已转过就不再传
        end.assert_called_once_with('A1', ['https://x/2.png'])
        self.assertTrue(any('等待验收中' in line for line in lines))

    def test_wait_accept_without_end_image_keeps_status(self):
        record = self._taken_record(dlt_first_image='https://x/1.png')
        with mock.patch.object(om, '_dlwz_order_images',
                               return_value=self._images(('首图', 'https://x/1.png'))), \
             mock.patch('API.apis.DaiLianTong.utils.upload_first_image'), \
             mock.patch('API.apis.DaiLianTong.utils.upload_end_image') as end:
            lines = om._accept_cycle({'WZ1': {'tradeNo': 'WZ1', 'status': 4}})

        record.refresh_from_db()
        self.assertEqual(record.status, MigrationStatus.TAKEN)
        end.assert_not_called()
        self.assertTrue(any('未见完单图' in line for line in lines))

    def test_forward_failure_keeps_status(self):
        record = self._taken_record()
        with mock.patch.object(om, '_dlwz_order_images',
                               return_value=self._images(('申请验收', 'https://x/2.png'))), \
             mock.patch('API.apis.DaiLianTong.utils.upload_first_image',
                        return_value=(True, {'code': 0})), \
             mock.patch('API.apis.DaiLianTong.utils.upload_end_image',
                        return_value=(True, {'code': 1, 'message': '订单状态已改变'})):
            lines = om._accept_cycle({'WZ1': {'tradeNo': 'WZ1', 'status': 4}})

        record.refresh_from_db()
        self.assertEqual(record.status, MigrationStatus.TAKEN)
        self.assertTrue(any('转传失败' in line and '订单状态已改变' in line for line in lines))

    def test_other_status_is_skipped(self):
        record = self._taken_record()
        with mock.patch.object(om, '_dlwz_order_images',
                               return_value=self._images(('首图', 'https://x/1.png'))), \
             mock.patch('API.apis.DaiLianTong.utils.upload_first_image',
                        return_value=(True, {'code': 0})), \
             mock.patch('API.apis.DaiLianTong.utils.upload_end_image') as end:
            lines = om._accept_cycle({'WZ1': {'tradeNo': 'WZ1', 'status': 5}})

        record.refresh_from_db()
        self.assertEqual(record.status, MigrationStatus.TAKEN)
        end.assert_not_called()
        self.assertTrue(any('丸子状态 5' in line for line in lines))


class NotifyBoosterCancelTests(TestCase):
    """打手申请退单：置状态 + 双通道通知管理员（Server酱 + QQBot），幂等"""

    def _record(self, **overrides):
        fields = dict(dlt_serial_no='A1', dlt_title='t', dlt_price=29, dlt_zone='安卓QQ',
                      dlt_time_limit=3, dlwz_trade_no='WZ1', amount=22.4,
                      security_deposit=22.4, efficiency_deposit=22.4, dlt_ensure=60.0,
                      booster_qq='12345', status=MigrationStatus.TAKEN)
        fields.update(overrides)
        return OrderMigration.objects.create(**fields)

    @mock.patch('API.apis.push.qqbot.utils.send', return_value=(True, {'message_id': 'm1'}))
    @mock.patch('API.apis.push.serverchan.utils.send', return_value=(True, {'pushid': 'p1'}))
    def test_notifies_both_channels_and_sets_status(self, push, qq):
        record = self._record()
        self.assertTrue(om.notify_booster_cancel(record, reason='测试退单', booster_name='打手A'))

        record.refresh_from_db()
        self.assertEqual(record.status, MigrationStatus.BOOSTER_CANCEL)
        self.assertTrue(record.booster_cancel_notified)
        self.assertIn('测试退单', record.message)

        push.assert_called_once()
        qq.assert_called_once()
        self.assertEqual(qq.call_args.args[1], 'private')          # 私聊
        self.assertEqual(qq.call_args.args[2], '3091995257')       # 默认管理员 QQ

        body = push.call_args.args[1]
        self.assertIn('A1', body)
        self.assertIn('WZ1', body)
        self.assertIn('12345', body)                               # 打手 QQ
        self.assertIn('打手A', body)                               # 打手昵称

    @mock.patch('API.apis.push.qqbot.utils.send', return_value=(True, {'message_id': 'm1'}))
    @mock.patch('API.apis.push.serverchan.utils.send', return_value=(True, {'pushid': 'p1'}))
    def test_idempotent(self, push, qq):
        record = self._record()
        self.assertTrue(om.notify_booster_cancel(record, reason='x'))
        self.assertFalse(om.notify_booster_cancel(record, reason='x'))    # 第二次不重复轰炸
        push.assert_called_once()
        qq.assert_called_once()

    @mock.patch('API.apis.push.qqbot.utils.send', return_value=(True, {'message_id': 'm1'}))
    @mock.patch('API.apis.push.serverchan.utils.send', return_value=(True, {'pushid': 'p1'}))
    def test_owner_info_missing_is_stated(self, push, qq):
        """还没在代练通接单（没号主信息）也要通知，且明说取不到"""
        record = self._record()
        om.notify_booster_cancel(record, reason='x')
        self.assertIn('未取到', push.call_args.args[1])


class CancelCycleTests(TestCase):
    """退单巡检：丸子上出现「撤销中」(status=5) → 置「打手申请退单」+ 通知，幂等"""

    def _record(self, status=MigrationStatus.TAKEN, **overrides):
        fields = dict(dlt_serial_no='A1', dlt_title='t', dlt_price=29, dlt_zone='安卓QQ',
                      dlt_time_limit=3, dlwz_trade_no='WZ1', status=status)
        fields.update(overrides)
        return OrderMigration.objects.create(**fields)

    def test_no_records_is_quiet(self):
        self.assertEqual(om._cancel_cycle({'WZ1': {'status': 5}}), [])

    @mock.patch('API.apis.order_migration.utils.notify_booster_cancel')
    def test_detects_cancelling_and_notifies(self, notify):
        record = self._record()
        lines = om._cancel_cycle({'WZ1': {'tradeNo': 'WZ1', 'status': 5, 'takerUsername': '打手X'}})

        notify.assert_called_once()
        self.assertEqual(notify.call_args.args[0], record)
        self.assertIn('撤销中', notify.call_args.kwargs['reason'])
        self.assertEqual(notify.call_args.kwargs['booster_name'], '打手X')
        self.assertTrue(any('已置「打手申请退单」' in line for line in lines))

    @mock.patch('API.apis.order_migration.utils.notify_booster_cancel')
    def test_skips_non_cancelling(self, notify):
        self._record()
        lines = om._cancel_cycle({'WZ1': {'tradeNo': 'WZ1', 'status': 3}})
        notify.assert_not_called()
        self.assertEqual(lines, [])

    @mock.patch('API.apis.order_migration.utils.notify_booster_cancel')
    def test_already_notified_is_skipped(self, notify):
        self._record(status=MigrationStatus.BOOSTER_CANCEL, booster_cancel_notified=True)
        lines = om._cancel_cycle({'WZ1': {'tradeNo': 'WZ1', 'status': 5}})
        notify.assert_not_called()
        self.assertTrue(any('已通知过' in line for line in lines))

    @mock.patch('API.apis.order_migration.utils.notify_booster_cancel')
    def test_missing_order_is_skipped(self, notify):
        self._record()
        self.assertEqual(om._cancel_cycle({}), [])
        notify.assert_not_called()

    @mock.patch('API.apis.order_migration.utils.notify_booster_cancel')
    def test_finished_record_is_ignored(self, notify):
        """已结算 / 已撤单的老记录即便平台仍显示 5 也不该再触发退单告警"""
        self._record(status=MigrationStatus.SETTLED)
        self.assertEqual(om._cancel_cycle({'WZ1': {'tradeNo': 'WZ1', 'status': 5}}), [])
        notify.assert_not_called()
