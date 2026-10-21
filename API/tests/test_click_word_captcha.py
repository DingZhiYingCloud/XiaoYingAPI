"""自研汉字点选验证码（/api/captcha_self/click/）回归测试

覆盖：
- 生成接口返回图片、目标字与数量，且不泄露目标坐标；
- 按顺序点选通过、顺序错 / 点偏 / 点数不足 / 用时过短失败；
- 一次性消费、过期、缺参；
- 生成 / 校验限流与连续失败冷却；
- 演示页可访问。
"""
import json
from datetime import timedelta
from unittest import mock

from django.core.cache import caches
from django.test import RequestFactory, TestCase
from django.utils import timezone

from API.apis.captcha_self import click_word as click_service
from API.apis.captcha_self import request as captcha_views
from API.models.Captcha.click_word import ClickWordChallenge
from SpiderServices.Captcha import click_word as word_gen


def _points(targets, duration=600, offset=0):
    """按目标顺序构造点击点（默认总用时 600ms）"""
    total = max(1, len(targets) - 1)
    rows = []
    for index, target in enumerate(targets):
        rows.append({
            'x': round(target['x'] + offset, 1),
            'y': round(target['y'], 1),
            't': round(duration * index / total),
        })
    return json.dumps(rows)


class ClickWordCaptchaTests(TestCase):
    def setUp(self):
        self.rf = RequestFactory()
        caches['ratelimit'].clear()

    def tearDown(self):
        caches['ratelimit'].clear()

    def _generate(self):
        response = captcha_views.click_generate_view(
            self.rf.get('/api/captcha_self/click/generate'))
        return json.loads(response.content.decode())

    def _verify(self, challenge_id, points):
        response = captcha_views.click_verify_view(
            self.rf.post('/api/captcha_self/click/verify', {
                'challenge_id': challenge_id,
                'points': points,
            }))
        return json.loads(response.content.decode())

    def test_generate_structure(self):
        body = self._generate()
        self.assertEqual(body['code'], 10000)
        data = body['data']
        self.assertTrue(data['challenge_id'])
        self.assertTrue(data['image'].startswith('data:image/png;base64,'))
        self.assertEqual(data['width'], 360)
        self.assertEqual(data['height'], 200)
        self.assertIn(len(data['chars']), (2, 3, 4))
        self.assertEqual(data['count'], len(data['chars']))
        self.assertEqual(data['expire_in'], click_service.EXPIRE_SECONDS)
        for char in data['chars']:
            self.assertIsInstance(char, str)
            self.assertEqual(len(char), 1)

    def test_generate_response_is_not_cacheable(self):
        response = captcha_views.click_generate_view(
            self.rf.get('/api/captcha_self/click/generate'))
        self.assertIn('no-store', response['Cache-Control'])

    def test_verify_in_order(self):
        data, targets = click_service.create_challenge()
        body = self._verify(data['challenge_id'], _points(targets))
        self.assertEqual(body['code'], 10000)
        self.assertTrue(body['data']['passed'])

    def test_verify_wrong_order(self):
        data, targets = click_service.create_challenge()
        if len(targets) < 2:
            self.skipTest('目标字不足两个')
        swapped = [targets[1], targets[0], *targets[2:]]
        body = self._verify(data['challenge_id'], _points(swapped))
        self.assertEqual(body['code'], 20003)
        self.assertIn('未命中', body['msg'])

    def test_verify_wrong_position(self):
        data, targets = click_service.create_challenge()
        # 第一个点改点到另一个目标字的位置：顺序没错，但命中位置不对
        points = json.loads(_points(targets))
        points[0]['x'] = round(targets[1]['x'], 1)
        points[0]['y'] = round(targets[1]['y'], 1)
        body = self._verify(data['challenge_id'], json.dumps(points))
        self.assertEqual(body['code'], 20003)
        self.assertIn('未命中', body['msg'])

    def test_verify_too_few_points(self):
        data, targets = click_service.create_challenge()
        body = self._verify(data['challenge_id'], _points(targets[:1]))
        self.assertEqual(body['code'], 20003)
        self.assertIn('请依次点击', body['msg'])

    def test_verify_too_fast(self):
        data, targets = click_service.create_challenge()
        body = self._verify(data['challenge_id'], _points(targets, duration=0))
        self.assertEqual(body['code'], 20003)
        self.assertIn('点击速度过快', body['msg'])

    def test_verify_one_time(self):
        data, targets = click_service.create_challenge()
        points = _points(targets)
        self.assertEqual(self._verify(data['challenge_id'], points)['code'], 10000)
        again = self._verify(data['challenge_id'], points)
        self.assertEqual(again['code'], 20003)
        self.assertIn('已被使用', again['msg'])

    def test_verify_expired(self):
        data, targets = click_service.create_challenge()
        ClickWordChallenge.objects.filter(pk=data['challenge_id']).update(
            expire_time=timezone.now() - timedelta(seconds=1))
        body = self._verify(data['challenge_id'], _points(targets))
        self.assertEqual(body['code'], 20003)
        self.assertIn('已过期', body['msg'])

    def test_verify_missing_points(self):
        data, _targets = click_service.create_challenge()
        response = captcha_views.click_verify_view(
            self.rf.post('/api/captcha_self/click/verify',
                         {'challenge_id': data['challenge_id']}))
        self.assertEqual(json.loads(response.content.decode())['code'], 20001)

    def test_generate_rate_limited(self):
        with mock.patch.object(captcha_views, 'CLICK_GENERATE_LIMIT', 2):
            self.assertEqual(self._generate()['code'], 10000)
            self.assertEqual(self._generate()['code'], 10000)
            third = self._generate()
        self.assertEqual(third['code'], 20040)

    def test_verify_rate_limited(self):
        with mock.patch.object(captcha_views, 'CLICK_VERIFY_LIMIT', 2):
            self._verify('00000000-0000-0000-0000-000000000000', '[]')
            self._verify('00000000-0000-0000-0000-000000000000', '[]')
            third = self._verify('00000000-0000-0000-0000-000000000000', '[]')
        self.assertEqual(third['code'], 20040)

    def test_failure_cooldown_blocks_correct_answer(self):
        first, first_targets = click_service.create_challenge()
        second, second_targets = click_service.create_challenge()
        third, third_targets = click_service.create_challenge()

        with mock.patch.object(captcha_views, 'CLICK_FAIL_LIMIT', 2), \
                mock.patch.object(captcha_views, 'CLICK_BLOCK_SECONDS', 60):
            one = self._verify(first['challenge_id'], _points(first_targets, offset=90))
            self.assertEqual(one['code'], 20003)
            two = self._verify(second['challenge_id'], _points(second_targets, offset=90))
            self.assertEqual(two['code'], 20040)  # 第二次失败触发冷却
            blocked = self._verify(third['challenge_id'], _points(third_targets))
        self.assertEqual(blocked['code'], 20040)
        self.assertIn('次数过多', blocked['msg'])

    def test_demo_page_renders(self):
        response = self.client.get('/captcha_self/click/')
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn('click-captcha', html)
        self.assertIn('/api/captcha_self/click/generate', html)
        self.assertIn('/api/captcha_self/click/verify', html)


class ClickWordGeneratorTests(TestCase):
    """生成引擎约束（不依赖 HTTP）"""

    def test_chars_and_targets(self):
        png, targets = word_gen.new_click_word_captcha()
        self.assertTrue(png.startswith(b'\x89PNG'))
        self.assertIn(len(targets), (2, 3, 4))
        for target in targets:
            self.assertIn(target['char'], word_gen.CHAR_POOL)
            self.assertTrue(0 <= target['x'] <= word_gen.CANVAS_WIDTH)
            self.assertTrue(0 <= target['y'] <= word_gen.CANVAS_HEIGHT)
            self.assertEqual(target['r'], word_gen.HIT_RADIUS)

    def test_targets_are_unique(self):
        _png, targets = word_gen.new_click_word_captcha()
        chars = [target['char'] for target in targets]
        self.assertEqual(len(chars), len(set(chars)))
