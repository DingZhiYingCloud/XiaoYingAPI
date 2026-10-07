"""代练搬单「代练通订单 → 代练丸子发单参数」映射单元测试

覆盖：
- 手续费阶梯 / 发布价公式 / 双金公式 / 区服映射（纯函数）
- 视图契约：必填缺失 20001、取值非法 20003、成功 10000、非 POST 405
- 标题黑名单过滤 / 被接单通知（邮件、语音）
"""
import json
from unittest.mock import patch

from django.test import RequestFactory, TestCase

from API.apis.order_migration import request as om_request
from API.apis.order_migration import utils as om_utils
from API.models import (DEFAULT_BLACKLIST_WORDS, MigrationStatus, OrderMigration,
                        OrderMigrationBlacklist, OrderMigrationSetting)
from API.website import console_order_migration


class CostTests(TestCase):
    """代练通王者·代练区·公共频道手续费阶梯"""

    def test_boundaries(self):
        self.assertEqual(om_utils.dlt_cost(10), 1)
        self.assertEqual(om_utils.dlt_cost(19.99), 1)
        self.assertEqual(om_utils.dlt_cost(20), 4)
        self.assertEqual(om_utils.dlt_cost(49.9), 4)
        self.assertEqual(om_utils.dlt_cost(50), 5)
        self.assertEqual(om_utils.dlt_cost(99), 5)
        self.assertEqual(om_utils.dlt_cost(100), 6)
        self.assertEqual(om_utils.dlt_cost(150), 7)
        self.assertEqual(om_utils.dlt_cost(800), 20)
        self.assertEqual(om_utils.dlt_cost(5000), 20)


class AmountAndDepositTests(TestCase):
    def test_amount_is_eighty_percent_of_net(self):
        # (43-4)*0.8 = 31.2
        self.assertEqual(om_utils.recommended_amount(43), 31.2)
        # (29-4)*0.8 = 20.0
        self.assertEqual(om_utils.recommended_amount(29), 20.0)
        # (139-6)*0.8 = 106.4
        self.assertEqual(om_utils.recommended_amount(139), 106.4)

    def test_deposits_default_total_is_double_amount(self):
        # 默认双金倍数 2：双金合计（安全+效率）= 发布价 × 2，两项均分各 = 发布价 × 1
        self.assertEqual(om_utils.deposits(31.2), (31.2, 31.2))

    def test_deposit_ratio_configurable(self):
        setting = OrderMigrationSetting.get_solo()
        setting.deposit_ratio = 0
        setting.save()
        self.assertEqual(om_utils.deposits(31.2), (0.0, 0.0))
        setting.deposit_ratio = 5
        setting.save()
        # 合计 = 31.2 × 5 = 156.0，两项各 78.0
        self.assertEqual(om_utils.deposits(31.2), (78.0, 78.0))

    def test_deposit_ratio_clamped_to_range(self):
        setting = OrderMigrationSetting.get_solo()
        setting.deposit_ratio = 9   # 越界：业务层夹紧到上限 5
        setting.save()
        self.assertEqual(om_utils.deposit_ratio(), 5)


class MapOrderTests(TestCase):
    def test_happy_path(self):
        ok, data = om_utils.map_order(
            title='星耀5 1星-星耀3 1星 铭文150级 刷机关定位',
            price=43, zone='苹果QQ', time_limit=5)
        self.assertTrue(ok)
        self.assertEqual(data, {
            'game_id': '1',
            'leveling_type_name': '排位',
            'region_name': '苹果QQ',
            'title': '星耀5 1星-星耀3 1星 铭文150级 刷机关定位',
            'hour': 5,
            'amount': 31.2,
            'security_deposit': 31.2,
            'efficiency_deposit': 31.2,
            'dlt_price': 43.0,
            'dlt_cost': 4,
        })

    def test_wx_zone_maps_to_weixin(self):
        ok, data = om_utils.map_order(title='t', price=29, zone='安卓WX', time_limit=3)
        self.assertTrue(ok)
        self.assertEqual(data['region_name'], '安卓微信')

    def test_unsupported_zone(self):
        ok, msg = om_utils.map_order(title='t', price=29, zone='PC端', time_limit=3)
        self.assertFalse(ok)
        self.assertIn('大区', msg)

    def test_empty_title(self):
        ok, msg = om_utils.map_order(title='  ', price=29, zone='安卓QQ', time_limit=3)
        self.assertFalse(ok)

    def test_bad_number(self):
        ok, msg = om_utils.map_order(title='t', price='abc', zone='安卓QQ', time_limit=3)
        self.assertFalse(ok)

    def test_non_positive_price(self):
        ok, msg = om_utils.map_order(title='t', price=0, zone='安卓QQ', time_limit=3)
        self.assertFalse(ok)


class PreviewViewTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.url = '/api/order_migration/preview'

    def _post(self, **data):
        return om_request.preview_view(self.factory.post(self.url, data))

    def test_success(self):
        body = json.loads(self._post(
            title='星耀5 1星-星耀3 1星 铭文150级', price='43',
            zone='安卓QQ', time_limit='5').content)
        self.assertEqual(body['code'], 10000)
        self.assertEqual(body['data']['region_name'], '安卓QQ')
        self.assertEqual(body['data']['amount'], 31.2)

    def test_missing_params(self):
        body = json.loads(self._post(title='t', zone='安卓QQ').content)
        self.assertEqual(body['code'], 20001)
        self.assertIn('price', body['msg'])
        self.assertIn('time_limit', body['msg'])

    def test_invalid_zone_value(self):
        body = json.loads(self._post(
            title='t', price='43', zone='PC端', time_limit='5').content)
        self.assertEqual(body['code'], 20003)

    def test_method_not_allowed(self):
        resp = om_request.preview_view(self.factory.get(self.url))
        self.assertEqual(resp.status_code, 405)


class BlacklistTests(TestCase):
    """标题黑名单：独立表，代练通标题命中任意一个词就不搬运"""

    def setUp(self):
        OrderMigrationBlacklist.objects.all().delete()
        for word in ('联系', '看要求', '勿扰'):
            OrderMigrationBlacklist.objects.create(word=word)

    def test_words_read_from_table(self):
        self.assertEqual(set(om_utils.blacklist_words()), {'联系', '看要求', '勿扰'})

    def test_default_words_constant_matches_spec(self):
        """初始黑名单应与需求给的数组一致（数据迁移按此写入）"""
        self.assertEqual(DEFAULT_BLACKLIST_WORDS, [
            'r', '此单', '联系', '看要求', '出w', 'w', '出', '需要', '老板',
            '接', '人不够', '俱乐部', '限', '陪练', '陪', '勿扰', '一个',
        ])

    def test_blacklisted_title_skipped(self):
        items = [
            {'SerialNo': 'A1', 'Title': '此单联系看要求 勿扰', 'Price': 43,
             'Zone': '安卓QQ', 'TimeLimit': 5},
            {'SerialNo': 'A2', 'Title': '星耀5 1星-王者 1星 铭文150级', 'Price': 43,
             'Zone': '安卓QQ', 'TimeLimit': 5},
        ]
        with patch.object(om_utils, '_fetch_dlt_orders', return_value=(items, [])):
            ok, candidates = om_utils.fetch_candidates()
        self.assertTrue(ok)
        self.assertEqual([c['dlt_serial_no'] for c in candidates], ['A2'])

    def test_empty_blacklist_keeps_all(self):
        OrderMigrationBlacklist.objects.all().delete()
        items = [{'SerialNo': 'A1', 'Title': '联系我看要求', 'Price': 43,
                  'Zone': '安卓QQ', 'TimeLimit': 5}]
        with patch.object(om_utils, '_fetch_dlt_orders', return_value=(items, [])):
            ok, candidates = om_utils.fetch_candidates()
        self.assertTrue(ok)
        self.assertEqual(len(candidates), 1)


class BlacklistSeedTests(TestCase):
    """数据迁移应把默认黑名单写入独立表"""

    def test_seeded_with_defaults(self):
        words = set(OrderMigrationBlacklist.objects.values_list('word', flat=True))
        self.assertEqual(words, set(DEFAULT_BLACKLIST_WORDS))


class NotifyTests(TestCase):
    """被接单通知：服务端只发邮件；声音提醒改由浏览器播报（见 TakenFeedTests）"""

    def setUp(self):
        self.setting = OrderMigrationSetting.get_solo()
        self.record = OrderMigration.objects.create(
            dlt_serial_no='S1', dlt_title='星耀5 1星-王者 1星', dlt_price=10,
            dlt_zone='安卓QQ', dlt_time_limit=2, dlwz_trade_no='WZ123', amount=7.2)

    def test_no_mail_when_disabled(self):
        self.setting.notify_mail = False
        self.setting.save()
        with patch('API.apis.push.email.utils.send_email') as send:
            om_utils.notify_taken(self.record)
        send.assert_not_called()

    def test_mail_sent_to_configured_recipient(self):
        self.setting.notify_mail = True
        self.setting.notify_mail_to = 'boss@example.com'
        self.setting.save()
        with patch('API.apis.push.email.utils.send_email',
                   return_value=(True, 'ok')) as send:
            om_utils.notify_taken(self.record)
        send.assert_called_once()
        args, _kwargs = send.call_args
        self.assertIn('WZ123', args[0])
        self.assertEqual(args[2], ['boss@example.com'])
        self.assertIn('S1', args[1])

    def test_mail_falls_back_to_env_sender(self):
        self.setting.notify_mail = True
        self.setting.notify_mail_to = ''
        self.setting.save()
        with patch('django.conf.settings.EMAIL_HOST_USER', 'env@qq.com'), \
                patch('API.apis.push.email.utils.send_email',
                      return_value=(True, 'ok')) as send:
            om_utils.notify_taken(self.record)
        send.assert_called_once()
        self.assertEqual(send.call_args[0][2], ['env@qq.com'])


class TakenFeedTests(TestCase):
    """浏览器语音提醒的数据源：只回传「游标之后、丸子刚被接单」的记录"""

    def setUp(self):
        self.record = OrderMigration.objects.create(
            dlt_serial_no='S1', dlt_title='t', dlt_price=10, dlt_zone='安卓QQ',
            dlt_time_limit=2, dlwz_trade_no='WZ1')

    def test_first_call_returns_cursor_without_history(self):
        cursor, items = om_utils.taken_feed(None)
        self.assertTrue(cursor)
        self.assertEqual(items, [])

    def test_published_record_not_returned(self):
        from django.utils import timezone
        _cursor, items = om_utils.taken_feed(timezone.now())
        self.assertEqual(items, [])

    def test_new_taker_joined_record_returned(self):
        from django.utils import timezone
        start = timezone.now()
        self.record.status = MigrationStatus.TAKER_JOINED
        self.record.save()
        cursor, items = om_utils.taken_feed(start)
        self.assertEqual([i['trade_no'] for i in items], ['WZ1'])
        self.assertEqual(cursor, items[0]['time'])

    def test_taken_record_not_returned(self):
        """代练通接单 / 转传图片等后续流转不该再响（只有丸子被接单那一刻响一次）"""
        from django.utils import timezone
        start = timezone.now()
        self.record.status = MigrationStatus.TAKEN
        self.record.save()
        _cursor, items = om_utils.taken_feed(start)
        self.assertEqual(items, [])


class RunLogTests(TestCase):
    """运行日志：滚动保留最近若干轮，供后台页实时展示"""

    def test_append_caps_at_limit(self):
        from django.utils import timezone
        raw = ''
        for _ in range(om_utils.RUN_LOG_LIMIT + 5):
            raw = om_utils._append_run_log(
                raw, {'fetched': 1, 'published': 0, 'taken': 0, 'rollback': 0, 'errors': []},
                timezone.now())
        self.assertEqual(len(json.loads(raw)), om_utils.RUN_LOG_LIMIT)

    @patch('API.apis.order_migration.utils.run_cycle')
    def test_run_once_writes_log(self, run_cycle):
        run_cycle.return_value = {'fetched': 3, 'published': 1, 'taker_joined': 1, 'taken': 0,
                                  'rollback': 0, 'errors': ['e1']}
        OrderMigrationSetting.get_solo().save()
        om_utils.run_once(publish_count=1)
        logs = om_utils.recent_run_logs()
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0]['fetched'], 3)
        self.assertEqual(logs[0]['published'], 1)
        self.assertEqual(logs[0]['errors'], ['e1'])

    def test_recent_logs_newest_first(self):
        from django.utils import timezone
        setting = OrderMigrationSetting.get_solo()
        raw = ''
        for n in (1, 2, 3):
            raw = om_utils._append_run_log(
                raw, {'fetched': n, 'published': 0, 'taken': 0, 'rollback': 0, 'errors': []},
                timezone.now())
        setting.run_logs = raw
        setting.save()
        logs = om_utils.recent_run_logs()
        self.assertEqual([log['fetched'] for log in logs], [3, 2, 1])


class FeedViewTests(TestCase):
    """实时刷新接口：返回记录 / 统计 / 运行状态 / 运行日志"""

    def setUp(self):
        from django.contrib.auth import get_user_model
        self.factory = RequestFactory()
        self.url = '/console/order-migration/feed/'
        self.user = get_user_model().objects.create_superuser('admin', 'a@b.com', 'pw')

    def _get(self, **params):
        request = self.factory.get(self.url, params)
        request.user = self.user
        return json.loads(console_order_migration.feed_view(request).content)

    def test_returns_records_stats_and_logs(self):
        OrderMigration.objects.create(dlt_serial_no='S1', dlt_title='t', dlt_price=10,
                                      dlt_zone='安卓QQ', dlt_time_limit=2,
                                      dlwz_trade_no='WZ1', status=MigrationStatus.PUBLISHED)
        body = self._get()
        self.assertTrue(body['ok'])
        self.assertEqual(body['stats']['published'], 1)
        self.assertEqual(body['records'][0]['serial'], 'S1')
        self.assertEqual(body['records'][0]['trade_no'], 'WZ1')
        self.assertIn('logs', body)
        self.assertIn('run', body)
        self.assertIn('cursor', body)

    def test_feed_respects_status_filter(self):
        OrderMigration.objects.create(dlt_serial_no='P1', dlt_title='t', dlt_price=10,
                                      dlt_zone='安卓QQ', dlt_time_limit=2,
                                      dlwz_trade_no='WZP', status=MigrationStatus.PUBLISHED)
        OrderMigration.objects.create(dlt_serial_no='F1', dlt_title='t', dlt_price=10,
                                      dlt_zone='安卓QQ', dlt_time_limit=2,
                                      dlwz_trade_no='WZF', status=MigrationStatus.FAILED)
        body = self._get(status='failed')
        # 列表按筛选，统计仍为全局
        self.assertEqual([r['serial'] for r in body['records']], ['F1'])
        self.assertEqual(body['stats']['published'], 1)
        self.assertEqual(body['stats']['failed'], 1)

    def test_feed_ignores_unknown_status(self):
        OrderMigration.objects.create(dlt_serial_no='P1', dlt_title='t', dlt_price=10,
                                      dlt_zone='安卓QQ', dlt_time_limit=2,
                                      dlwz_trade_no='WZP', status=MigrationStatus.PUBLISHED)
        body = self._get(status='bogus')
        self.assertEqual([r['serial'] for r in body['records']], ['P1'])

    def test_feed_supports_pagination(self):
        size = console_order_migration.PAGE_SIZE
        for i in range(size + 3):
            OrderMigration.objects.create(
                dlt_serial_no=f'P{i}', dlt_title='t', dlt_price=10, dlt_zone='安卓QQ',
                dlt_time_limit=2, dlwz_trade_no=f'WZ{i}', status=MigrationStatus.PUBLISHED)
        body = self._get()
        self.assertEqual(body['page'], 1)
        self.assertEqual(body['num_pages'], 2)
        self.assertEqual(body['filtered_total'], size + 3)
        self.assertEqual(len(body['records']), size)
        body2 = self._get(page=2)
        self.assertEqual(body2['page'], 2)
        self.assertEqual(len(body2['records']), 3)

    def test_records_include_id_and_booster_cancel_stat(self):
        """列表带上记录 id（编辑按钮要用）+ 新增「打手申请退单」统计"""
        OrderMigration.objects.create(dlt_serial_no='B1', dlt_title='t', dlt_price=10,
                                      dlt_zone='安卓QQ', dlt_time_limit=2,
                                      dlwz_trade_no='WZB', status=MigrationStatus.BOOSTER_CANCEL)
        body = self._get()
        self.assertEqual(body['stats']['booster_cancel'], 1)
        self.assertTrue(all(r.get('id') for r in body['records']))

    def test_method_not_allowed(self):
        request = self.factory.post(self.url)
        request.user = self.user
        self.assertEqual(console_order_migration.feed_view(request).status_code, 405)

    def test_page_renders_live_elements(self):
        from django.test import Client
        client = Client()
        client.force_login(self.user)
        resp = client.get('/console/order-migration/')
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        self.assertIn('/console/order-migration/feed/', html)
        self.assertIn('id="records-body"', html)
        self.assertIn('id="run-logs"', html)
        self.assertIn('id="run-back-top"', html)

    def test_page_filters_records_by_status(self):
        from django.test import Client
        OrderMigration.objects.create(dlt_serial_no='P1', dlt_title='标题P', dlt_price=10,
                                      dlt_zone='安卓QQ', dlt_time_limit=2,
                                      dlwz_trade_no='WZP', status=MigrationStatus.PUBLISHED)
        OrderMigration.objects.create(dlt_serial_no='F1', dlt_title='标题F', dlt_price=10,
                                      dlt_zone='安卓QQ', dlt_time_limit=2,
                                      dlwz_trade_no='WZF', status=MigrationStatus.FAILED)
        client = Client()
        client.force_login(self.user)
        html = client.get('/console/order-migration/?status=failed').content.decode()
        self.assertIn('状态筛选：', html)
        self.assertIn('F1', html)
        self.assertNotIn('P1', html)


class ClearLogsViewTests(TestCase):
    """清空运行日志：只清日志，不动搬单记录"""

    def setUp(self):
        from django.contrib.auth import get_user_model
        from django.test import Client
        self.client = Client()
        self.user = get_user_model().objects.create_superuser('admin4', 'a@b.com', 'pw')
        self.client.force_login(self.user)

    def test_clears_run_logs_only(self):
        setting = OrderMigrationSetting.get_solo()
        setting.run_logs = '[{"fetched": 1}]'
        setting.save()
        OrderMigration.objects.create(dlt_serial_no='S1', dlt_title='t', dlt_price=10,
                                      dlt_zone='安卓QQ', dlt_time_limit=2)

        resp = self.client.post('/console/order-migration/', {'action': 'clear_logs'})

        self.assertEqual(resp.status_code, 302)
        setting.refresh_from_db()
        self.assertEqual(setting.run_logs, '')
        self.assertEqual(OrderMigration.objects.count(), 1)     # 记录没被删


class CancelAllViewTests(TestCase):
    """一键撤销待接单的页面动作：撤销后自动运行必须被关掉"""

    def setUp(self):
        from django.contrib.auth import get_user_model
        from django.test import Client
        self.client = Client()
        self.user = get_user_model().objects.create_superuser('admin3', 'a@b.com', 'pw')
        self.client.force_login(self.user)

    @patch('API.website.console_order_migration.om_utils.cancel_all_pending')
    def test_turns_off_auto_run(self, cancel_all):
        cancel_all.return_value = {'total': 2, 'cancelled': 2, 'revoked': 0,
                                   'failed': 0, 'errors': []}
        setting = OrderMigrationSetting.get_solo()
        setting.auto_run = True
        setting.save()

        resp = self.client.post('/console/order-migration/', {'action': 'cancel_all'})

        self.assertEqual(resp.status_code, 302)
        setting.refresh_from_db()
        self.assertFalse(setting.auto_run)
        cancel_all.assert_called_once()


class EditRecordViewTests(TestCase):
    """编辑记录：只改本地状态 + 备注，不发任何平台请求"""

    def setUp(self):
        from django.contrib.auth import get_user_model
        from django.test import Client
        self.client = Client()
        self.user = get_user_model().objects.create_superuser('admin5', 'a@b.com', 'pw')
        self.client.force_login(self.user)
        self.record = OrderMigration.objects.create(
            dlt_serial_no='S1', dlt_title='t', dlt_price=10, dlt_zone='安卓QQ',
            dlt_time_limit=2, dlwz_trade_no='WZ1', status=MigrationStatus.BOOSTER_CANCEL,
            message='旧备注')

    def _post(self, **data):
        return self.client.post('/console/order-migration/', data)

    def test_updates_status_and_message(self):
        resp = self._post(action='edit', record_id=str(self.record.pk),
                          status=MigrationStatus.CANCELLED.value, message='已人工撤销')
        self.assertEqual(resp.status_code, 302)
        self.record.refresh_from_db()
        self.assertEqual(self.record.status, MigrationStatus.CANCELLED)
        self.assertEqual(self.record.message, '已人工撤销')

    def test_rejects_invalid_status(self):
        self._post(action='edit', record_id=str(self.record.pk), status='bogus', message='x')
        self.record.refresh_from_db()
        self.assertEqual(self.record.status, MigrationStatus.BOOSTER_CANCEL)    # 未变

    def test_unknown_record_is_ignored(self):
        self._post(action='edit', record_id='00000000-0000-0000-0000-000000000000',
                   status=MigrationStatus.CANCELLED.value, message='x')
        self.record.refresh_from_db()
        self.assertEqual(self.record.status, MigrationStatus.BOOSTER_CANCEL)

    def test_invalid_uuid_is_ignored(self):
        resp = self._post(action='edit', record_id='not-a-uuid',
                          status=MigrationStatus.CANCELLED.value, message='x')
        self.assertEqual(resp.status_code, 302)
        self.record.refresh_from_db()
        self.assertEqual(self.record.status, MigrationStatus.BOOSTER_CANCEL)


class NotifyQqSettingTests(TestCase):
    """设置页可维护「管理员QQ」（退单通知）"""

    def setUp(self):
        from django.contrib.auth import get_user_model
        from django.test import Client
        self.client = Client()
        self.user = get_user_model().objects.create_superuser('admin6', 'a@b.com', 'pw')
        self.client.force_login(self.user)

    def test_saves_notify_qq(self):
        self.client.post('/console/order-migration/', {
            'action': 'save', 'notify_qq': '99887766'})
        self.assertEqual(OrderMigrationSetting.get_solo().notify_qq, '99887766')
