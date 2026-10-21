"""自研滑块验证码（/api/captcha_self/slider/）回归测试

覆盖：
- 生成接口返回背景图 / 拼图块 / 纵坐标 / 画布尺寸，且不泄露缺口横坐标；
- 容差内通过、超出容差失败；
- 拖动轨迹（点数 / 时长 / 终点）校验；
- 一次性消费、过期；
- 生成 / 校验限流与连续失败冷却；
- 演示页可访问。
"""
import json
from datetime import timedelta
from unittest import mock

from django.core.cache import caches
from django.test import RequestFactory, TestCase
from django.utils import timezone

from API.apis.captcha_self import request as captcha_views
from API.apis.captcha_self import slider as slider_service
from API.models.Captcha.slider import SliderChallenge


def _track(end_x, duration=1000, points=8):
    """构造一条正常拖动轨迹（匀速、时间单调、终点为 end_x）"""
    rows = []
    for index in range(points):
        ratio = index / (points - 1)
        rows.append({
            'x': round(end_x * ratio, 1),
            't': round(duration * ratio),
        })
    return json.dumps(rows)


class SliderCaptchaTests(TestCase):
    def setUp(self):
        self.rf = RequestFactory()
        caches['ratelimit'].clear()

    def tearDown(self):
        caches['ratelimit'].clear()

    def _generate(self):
        response = captcha_views.slider_generate_view(
            self.rf.get('/api/captcha_self/slider/generate'))
        return json.loads(response.content.decode())

    def _verify(self, slider_id, x, track):
        response = captcha_views.slider_verify_view(
            self.rf.post('/api/captcha_self/slider/verify', {
                'slider_id': slider_id,
                'x': str(x),
                'track': track,
            }))
        return json.loads(response.content.decode())

    def test_generate_structure(self):
        body = self._generate()
        self.assertEqual(body['code'], 10000)
        data = body['data']
        self.assertTrue(data['slider_id'])
        self.assertTrue(data['background'].startswith('data:image/jpeg;base64,'))
        self.assertTrue(data['piece'].startswith('data:image/png;base64,'))
        self.assertEqual(data['width'], 320)
        self.assertEqual(data['height'], 160)
        self.assertEqual(data['piece_size'], 52)
        self.assertGreaterEqual(data['piece_y'], 0)
        self.assertLessEqual(data['piece_y'], data['height'] - data['piece_size'])
        self.assertEqual(data['expire_in'], slider_service.EXPIRE_SECONDS)
        # 答案（缺口横坐标）不应出现在响应里
        self.assertNotIn('answer', data)
        self.assertNotIn('x', data)

    def test_generate_response_is_not_cacheable(self):
        response = captcha_views.slider_generate_view(
            self.rf.get('/api/captcha_self/slider/generate'))
        self.assertIn('no-store', response['Cache-Control'])

    def test_verify_within_tolerance(self):
        data, answer_x = slider_service.create_challenge()
        # 容差 8px：偏 5px 仍应通过
        body = self._verify(data['slider_id'], answer_x + 5, _track(answer_x + 5))
        self.assertEqual(body['code'], 10000)
        self.assertTrue(body['data']['passed'])

    def test_verify_out_of_tolerance(self):
        data, answer_x = slider_service.create_challenge()
        body = self._verify(data['slider_id'], answer_x + 30, _track(answer_x + 30))
        self.assertEqual(body['code'], 20003)
        self.assertIn('未对齐', body['msg'])

    def test_verify_rejects_bad_track(self):
        data, answer_x = slider_service.create_challenge()
        # 点数不足
        too_few = json.dumps([{'x': 0, 't': 0}, {'x': answer_x, 't': 900}])
        body = self._verify(data['slider_id'], answer_x, too_few)
        self.assertEqual(body['code'], 20003)
        self.assertIn('轨迹异常', body['msg'])

        # 用时过短
        data2, answer_x2 = slider_service.create_challenge()
        too_fast = _track(answer_x2, duration=50)
        body2 = self._verify(data2['slider_id'], answer_x2, too_fast)
        self.assertEqual(body2['code'], 20003)
        self.assertIn('轨迹异常', body2['msg'])

    def test_verify_accepts_long_track(self):
        """长时间拖动会产生大量轨迹点：不能被点数上限误伤"""
        data, answer_x = slider_service.create_challenge()
        points = []
        total = 1500
        for index in range(total):
            ratio = index / (total - 1)
            points.append({
                'x': round(answer_x * ratio, 1),
                't': round(3000 * ratio),
            })
        body = self._verify(data['slider_id'], answer_x, json.dumps(points))
        self.assertEqual(body['code'], 10000)
        self.assertTrue(body['data']['passed'])

    def test_verify_one_time(self):
        data, answer_x = slider_service.create_challenge()
        track = _track(answer_x)
        first = self._verify(data['slider_id'], answer_x, track)
        self.assertEqual(first['code'], 10000)

        again = self._verify(data['slider_id'], answer_x, track)
        self.assertEqual(again['code'], 20003)
        self.assertIn('已被使用', again['msg'])

    def test_verify_expired(self):
        data, answer_x = slider_service.create_challenge()
        SliderChallenge.objects.filter(pk=data['slider_id']).update(
            expire_time=timezone.now() - timedelta(seconds=1))
        body = self._verify(data['slider_id'], answer_x, _track(answer_x))
        self.assertEqual(body['code'], 20003)
        self.assertIn('已过期', body['msg'])

    def test_verify_missing_track(self):
        data, answer_x = slider_service.create_challenge()
        response = captcha_views.slider_verify_view(
            self.rf.post('/api/captcha_self/slider/verify', {
                'slider_id': data['slider_id'], 'x': str(answer_x),
            }))
        self.assertEqual(json.loads(response.content.decode())['code'], 20001)

    def test_generate_rate_limited(self):
        with mock.patch.object(captcha_views, 'SLIDER_GENERATE_LIMIT', 2):
            self.assertEqual(self._generate()['code'], 10000)
            self.assertEqual(self._generate()['code'], 10000)
            third = self._generate()
        self.assertEqual(third['code'], 20040)

    def test_verify_rate_limited(self):
        with mock.patch.object(captcha_views, 'SLIDER_VERIFY_LIMIT', 2):
            self._verify('00000000-0000-0000-0000-000000000000', 1, '[]')
            self._verify('00000000-0000-0000-0000-000000000000', 1, '[]')
            third = self._verify('00000000-0000-0000-0000-000000000000', 1, '[]')
        self.assertEqual(third['code'], 20040)

    def test_failure_cooldown_blocks_correct_answer(self):
        with mock.patch.object(captcha_views, 'SLIDER_FAIL_LIMIT', 2), \
                mock.patch.object(captcha_views, 'SLIDER_BLOCK_SECONDS', 60):
            bad_a, x_a = slider_service.create_challenge()
            bad_b, x_b = slider_service.create_challenge()
            good, x_good = slider_service.create_challenge()

            first = self._verify(bad_a['slider_id'], x_a + 60, _track(x_a + 60))
            self.assertEqual(first['code'], 20003)
            second = self._verify(bad_b['slider_id'], x_b + 60, _track(x_b + 60))
            self.assertEqual(second['code'], 20040)  # 第二次失败触发冷却
            blocked = self._verify(good['slider_id'], x_good, _track(x_good))
        self.assertEqual(blocked['code'], 20040)
        self.assertIn('次数过多', blocked['msg'])

    def test_demo_page_renders(self):
        response = self.client.get('/captcha_self/slider/')
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn('slider-captcha', html)
        self.assertIn('/api/captcha_self/slider/generate', html)
        self.assertIn('/api/captcha_self/slider/verify', html)
