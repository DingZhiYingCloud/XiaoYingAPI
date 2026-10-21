"""自研验证码：统计埋点 + 官网随机类型路由 回归测试

覆盖：
- `CaptchaStat` 按天 / 线路累加，生成 / 通过 / 失败原因 / 拦截各走一列；
- 服务层埋点确实被生成与校验触发（接口与官网表单共用同一本账）；
- 官网 `captcha.check_params` 能按 captcha_type 路由到字符 / 滑块 / 汉字点选；
- 参数缺失、类型非法、校验失败三种分支的语义；
- 控制台监控面板可正常渲染。
"""
import json
from datetime import timedelta
from unittest import mock

from django.contrib.auth.models import User
from django.core.cache import caches
from django.test import Client, RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from API.apis.captcha_self import behavior
from API.apis.captcha_self import click_word as click_service
from API.apis.captcha_self import request as captcha_views
from API.apis.captcha_self import slider as slider_service
from API.apis.captcha_self import stats
from API.apis.captcha_self import utils as captcha_utils
from API.models import CaptchaStat
from API.models.Captcha.behavior import BehaviorSample
from API.models.Captcha.captcha import CaptchaChallenge
from SpiderServices.Captcha import generator

from API.website import captcha as website_captcha


class CaptchaStatTests(TestCase):
    """统计埋点"""

    def setUp(self):
        caches['ratelimit'].clear()

    def tearDown(self):
        caches['ratelimit'].clear()

    def _row(self, kind='slider'):
        return CaptchaStat.objects.get(day=timezone.localdate(), kind=kind)

    def test_counters_accumulate(self):
        stats.record_generated('slider')
        stats.record_generated('slider')
        stats.record_passed('slider')
        stats.record_failed('slider', 'expired')
        stats.record_failed('slider', 'wrong')
        stats.record_blocked('slider')

        row = self._row()
        self.assertEqual(row.generated, 2)
        self.assertEqual(row.passed, 1)
        self.assertEqual(row.failed, 2)
        self.assertEqual(row.blocked, 1)
        self.assertEqual(row.fail_expired, 1)
        self.assertEqual(row.fail_wrong, 1)
        self.assertEqual(row.fail_used, 0)

    def test_unknown_reason_falls_back_to_wrong(self):
        stats.record_failed('char', 'not-a-reason')
        self.assertEqual(self._row('char').fail_wrong, 1)

    def test_service_layer_hooked(self):
        with mock.patch.object(generator, 'new_char_captcha', return_value=(b'png', 'ABCD')):
            data = captcha_utils.create_challenge(CaptchaChallenge.KIND_CHAR, 4)

        row = self._row(CaptchaChallenge.KIND_CHAR)
        self.assertEqual(row.generated, 1)

        ok, _err = captcha_utils.verify_challenge(data['captcha_id'], 'abcd')
        self.assertTrue(ok)
        row.refresh_from_db()
        self.assertEqual(row.passed, 1)


class WebsiteCaptchaRoutingTests(TestCase):
    """官网表单按 captcha_type 路由校验"""

    def setUp(self):
        self.rf = RequestFactory()
        caches['ratelimit'].clear()

    def tearDown(self):
        caches['ratelimit'].clear()

    def _text_params(self):
        with mock.patch.object(generator, 'new_char_captcha', return_value=(b'png', 'ABCD')):
            data = captcha_utils.create_challenge(CaptchaChallenge.KIND_CHAR, 4)
        return {'captcha_type': 'char', 'captcha_id': data['captcha_id'], 'answer': 'abcd'}

    def _slider_params(self):
        data, answer_x = slider_service.create_challenge()
        step = answer_x / 4.0
        points = [{'x': round(step * i, 1), 't': i * 80} for i in range(5)]
        return {
            'captcha_type': 'slider',
            'slider_id': data['slider_id'],
            'x': str(answer_x),
            'track': json.dumps(points),
        }

    def _click_params(self):
        data, targets = click_service.create_challenge()
        points = [
            {'x': target['x'], 'y': target['y'], 't': index * 400}
            for index, target in enumerate(targets)
        ]
        return {
            'captcha_type': 'click',
            'challenge_id': data['challenge_id'],
            'points': json.dumps(points),
        }

    def test_char_type_passes(self):
        ok, reason, detail = website_captcha.check_params(self._text_params())
        self.assertTrue(ok, detail)
        self.assertEqual(reason, '')

    def test_slider_type_passes(self):
        ok, reason, detail = website_captcha.check_params(self._slider_params())
        self.assertTrue(ok, detail)
        self.assertEqual(reason, '')

    def test_click_type_passes(self):
        ok, reason, detail = website_captcha.check_params(self._click_params())
        self.assertTrue(ok, detail)
        self.assertEqual(reason, '')

    def test_missing_params(self):
        ok, reason, _detail = website_captcha.check_params({'captcha_type': 'slider'})
        self.assertFalse(ok)
        self.assertEqual(reason, 'missing')

    def test_invalid_type(self):
        ok, reason, _detail = website_captcha.check_params({'captcha_type': 'nope'})
        self.assertFalse(ok)
        self.assertEqual(reason, 'invalid_type')

    def test_wrong_answer_maps_to_invalid_status(self):
        params = self._text_params()
        params['answer'] = 'WRONG'
        request = self.rf.post('/login/', params)
        ok, err = website_captcha.verify(request)
        self.assertFalse(ok)
        self.assertEqual(err[0], 20003)

    def test_legacy_request_without_type_defaults_to_char(self):
        params = self._text_params()
        params.pop('captcha_type')
        ok, _reason, detail = website_captcha.check_params(params)
        self.assertTrue(ok, detail)


class BehaviorShadowTests(TestCase):
    """行为验证影子模式：只打分记录，不影响放行"""

    def setUp(self):
        self.rf = RequestFactory()
        caches['ratelimit'].clear()

    def tearDown(self):
        caches['ratelimit'].clear()

    def test_bot_like_features_score_high(self):
        score, hits = behavior.score_features({
            'dwell_ms': 300,
            'pointer_moves': 0,
            'key_count': 5,
            'key_intervals': [10, 12, 9, 11],
            'webdriver': True,
        })
        self.assertGreaterEqual(score, 70)
        self.assertEqual(behavior.band_of(score), BehaviorSample.BAND_HIGH)
        self.assertIn('webdriver', hits)
        self.assertIn('instant_keys', hits)

    def test_human_like_features_score_low(self):
        score, hits = behavior.score_features({
            'dwell_ms': 9000,
            'pointer_moves': 60,
            'pointer_distance': 1800,
            'key_count': 12,
            'key_intervals': [120, 240, 180, 300],
            'key_corrections': 2,
            'focus_changes': 0,
            'hidden_count': 0,
        })
        self.assertLess(score, behavior.LOW_MAX)
        self.assertEqual(behavior.band_of(score), BehaviorSample.BAND_LOW)
        self.assertEqual(hits, [])

    def test_missing_features_is_high_risk(self):
        score, hits = behavior.score_features(None)
        self.assertEqual(score, 100)
        self.assertIn('no_features', hits)

    def test_endpoint_records_sample(self):
        request = self.rf.post(
            '/api/captcha_self/behavior',
            data=json.dumps({
                'scene': 'login',
                'features': {'dwell_ms': 200, 'pointer_moves': 0,
                             'key_count': 6, 'key_intervals': [8, 9, 7],
                             'webdriver': True},
            }),
            content_type='application/json',
        )
        body = json.loads(captcha_views.behavior_view(request).content.decode())
        self.assertEqual(body['code'], 10000)
        self.assertTrue(body['data']['shadow'])
        self.assertEqual(body['data']['band'], 'high')

        sample = BehaviorSample.objects.get()
        self.assertEqual(sample.scene, 'login')
        self.assertEqual(sample.band, 'high')
        self.assertIn('webdriver', sample.hits)

    def test_endpoint_rejects_bad_json(self):
        request = self.rf.post('/api/captcha_self/behavior', data='{not-json',
                               content_type='application/json')
        body = json.loads(captcha_views.behavior_view(request).content.decode())
        self.assertEqual(body['code'], 20002)

    def test_panel_counts_behavior_samples(self):
        BehaviorSample.objects.create(scene='login', score=80, band='high', hits=['webdriver'])
        BehaviorSample.objects.create(scene='register', score=10, band='low', hits=[])

        admin = User.objects.create_superuser('bh_admin', 'bh@example.com', 'pw12345678')
        client = Client()
        client.force_login(admin)
        response = client.get(reverse('website:console_captcha'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['behavior']['total'], 2)
        self.assertEqual(response.context['behavior']['today_total'], 2)
        self.assertEqual(response.context['behavior']['bands'][0]['count'], 1)
        self.assertEqual(response.context['behavior']['bands'][2]['count'], 1)


class CaptchaMonitorPageTests(TestCase):
    """控制台验证码监控页"""

    def setUp(self):
        self.admin = User.objects.create_superuser('cap_admin', 'cap@example.com', 'pw12345678')
        self.client = Client()
        self.client.force_login(self.admin)

    def test_page_renders(self):
        stats.record_generated('slider')
        stats.record_failed('slider', 'wrong')
        stats.record_blocked('slider')

        response = self.client.get(reverse('website:console_captcha'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'console/captcha.html')
        self.assertEqual(response.context['window']['generated'], 1)
        self.assertEqual(response.context['window']['failed'], 1)
        self.assertEqual(response.context['window']['blocked'], 1)

    def test_window_accepts_only_known_days(self):
        response = self.client.get(reverse('website:console_captcha'), {'days': '999'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['days'], 14)

    def test_requires_superadmin(self):
        normal = User.objects.create_user('cap_user', 'u@example.com', 'pw12345678')
        self.client.force_login(normal)
        response = self.client.get(reverse('website:console_captcha'))
        # 控制台对非超管返回 404（不暴露页面存在），而不是重定向
        self.assertEqual(response.status_code, 404)
