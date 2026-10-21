"""自研图形验证码（/api/captcha_self/）回归测试

覆盖：
- 生成接口返回 captcha_id / base64 PNG / 有效期，且响应禁止缓存；
- 数据库只存答案的 HMAC 摘要，不落明文；
- 一次性消费：同一 captcha_id 重复校验只有第一次可能成功；
- 错误答案、过期、非法 UUID 的失败分支；
- 生成 / 校验接口的 IP 限流。
"""
import json
import unittest
from datetime import timedelta
from unittest import mock

from django.core.cache import caches
from django.test import RequestFactory, TestCase
from django.utils import timezone

from API.apis.captcha_self import request as captcha_views
from API.apis.captcha_self import utils
from API.models.Captcha.captcha import CaptchaChallenge
from SpiderServices.Captcha import generator


class CaptchaSelfTests(TestCase):
    def setUp(self):
        self.rf = RequestFactory()
        caches['ratelimit'].clear()

    def tearDown(self):
        caches['ratelimit'].clear()

    def _generate(self, **params):
        request = self.rf.get('/api/captcha_self/generate', params)
        return json.loads(captcha_views.generate_view(request).content.decode())

    def _verify(self, captcha_id, answer):
        request = self.rf.post('/api/captcha_self/verify',
                               {'captcha_id': captcha_id, 'answer': answer})
        return json.loads(captcha_views.verify_view(request).content.decode())

    def test_generate_returns_png_and_meta(self):
        body = self._generate()
        self.assertEqual(body['code'], 10000)
        data = body['data']
        self.assertTrue(data['captcha_id'])
        self.assertEqual(data['kind'], 'char')
        self.assertTrue(data['image'].startswith('data:image/png;base64,'))
        self.assertEqual(data['expire_in'], utils.EXPIRE_SECONDS)

    def test_generate_response_is_not_cacheable(self):
        request = self.rf.get('/api/captcha_self/generate')
        response = captcha_views.generate_view(request)
        self.assertIn('no-store', response['Cache-Control'])
        self.assertEqual(response['Pragma'], 'no-cache')

    def test_answer_stored_as_digest(self):
        with mock.patch.object(generator, 'new_char_captcha', return_value=(b'png', 'ABCD')):
            data = utils.create_challenge(CaptchaChallenge.KIND_CHAR, 4)
        record = CaptchaChallenge.objects.get(pk=data['captcha_id'])
        self.assertNotEqual(record.answer, 'ABCD')
        self.assertEqual(record.answer, utils._answer_digest(record.id, 'abcd'))
        self.assertEqual(len(record.answer), 64)  # SHA256 十六进制

    def test_verify_success_and_one_time(self):
        with mock.patch.object(generator, 'new_char_captcha', return_value=(b'png', 'ABCD')):
            data = utils.create_challenge(CaptchaChallenge.KIND_CHAR, 4)

        body = self._verify(data['captcha_id'], 'abcd')  # 大小写不敏感
        self.assertEqual(body['code'], 10000)
        self.assertTrue(body['data']['passed'])

        again = self._verify(data['captcha_id'], 'ABCD')
        self.assertEqual(again['code'], 20003)
        self.assertFalse(again['data']['passed'])
        self.assertIn('已被使用', again['msg'])

    def test_verify_wrong_answer_consumes_challenge(self):
        with mock.patch.object(generator, 'new_char_captcha', return_value=(b'png', 'ABCD')):
            data = utils.create_challenge(CaptchaChallenge.KIND_CHAR, 4)

        body = self._verify(data['captcha_id'], 'ZZZZ')
        self.assertEqual(body['code'], 20003)
        self.assertIn('答案错误', body['msg'])
        # 失败也作废，不能再用正确答案重试
        retry = self._verify(data['captcha_id'], 'ABCD')
        self.assertIn('已被使用', retry['msg'])

    def test_verify_expired(self):
        with mock.patch.object(generator, 'new_char_captcha', return_value=(b'png', 'ABCD')):
            data = utils.create_challenge(CaptchaChallenge.KIND_CHAR, 4)
        CaptchaChallenge.objects.filter(pk=data['captcha_id']).update(
            expire_time=timezone.now() - timedelta(seconds=1))

        body = self._verify(data['captcha_id'], 'ABCD')
        self.assertEqual(body['code'], 20003)
        self.assertIn('已过期', body['msg'])

    def test_verify_bad_uuid(self):
        ok, msg = utils.verify_challenge('not-a-uuid', 'ABCD')
        self.assertFalse(ok)
        self.assertIn('不存在或已失效', msg)

    def test_generate_invalid_kind(self):
        body = self._generate(kind='unknown')
        self.assertEqual(body['code'], 20003)

    def test_generate_rate_limited(self):
        with mock.patch.object(captcha_views, 'GENERATE_LIMIT', 2):
            self.assertEqual(self._generate()['code'], 10000)
            self.assertEqual(self._generate()['code'], 10000)
            third = self._generate()
        self.assertEqual(third['code'], 20040)
        self.assertIn('请求过于频繁', third['msg'])

    def test_verify_rate_limited(self):
        with mock.patch.object(captcha_views, 'VERIFY_LIMIT', 2):
            self._verify('00000000-0000-0000-0000-000000000000', 'A')
            self._verify('00000000-0000-0000-0000-000000000000', 'A')
            third = self._verify('00000000-0000-0000-0000-000000000000', 'A')
        self.assertEqual(third['code'], 20040)
        self.assertIn('请求过于频繁', third['msg'])

    def test_failure_cooldown_blocks_correct_answer(self):
        with mock.patch.object(generator, 'new_char_captcha', return_value=(b'png', 'ABCD')):
            first = utils.create_challenge(CaptchaChallenge.KIND_CHAR, 4)
            second = utils.create_challenge(CaptchaChallenge.KIND_CHAR, 4)
            third = utils.create_challenge(CaptchaChallenge.KIND_CHAR, 4)

        with mock.patch.object(captcha_views, 'FAIL_LIMIT', 2), \
                mock.patch.object(captcha_views, 'BLOCK_SECONDS', 60):
            wrong_one = self._verify(first['captcha_id'], 'ZZZZ')
            self.assertEqual(wrong_one['code'], 20003)
            wrong_two = self._verify(second['captcha_id'], 'ZZZZ')
            self.assertEqual(wrong_two['code'], 20040)  # 第二次失败触发冷却
            # 冷却期内即使答案正确也直接拒绝
            blocked = self._verify(third['captcha_id'], 'ABCD')
        self.assertEqual(blocked['code'], 20040)
        self.assertIn('次数过多', blocked['msg'])

    def test_success_resets_failure_counter(self):
        with mock.patch.object(generator, 'new_char_captcha', return_value=(b'png', 'ABCD')):
            first = utils.create_challenge(CaptchaChallenge.KIND_CHAR, 4)
            second = utils.create_challenge(CaptchaChallenge.KIND_CHAR, 4)
            third = utils.create_challenge(CaptchaChallenge.KIND_CHAR, 4)

        with mock.patch.object(captcha_views, 'FAIL_LIMIT', 2):
            self.assertEqual(self._verify(first['captcha_id'], 'ZZZZ')['code'], 20003)
            # 成功一次把失败计数清零，后续单次失败不应触发冷却
            self.assertEqual(self._verify(second['captcha_id'], 'ABCD')['code'], 10000)
            after_success = self._verify(third['captcha_id'], 'ZZZZ')
        self.assertEqual(after_success['code'], 20003)


class CaptchaGeneratorTests(unittest.TestCase):
    """图形生成引擎的基本约束（不依赖 DB）"""

    def test_char_captcha_length_and_alphabet(self):
        pool = set(generator.CHAR_POOL)
        for length in (generator.MIN_LENGTH, generator.MAX_LENGTH):
            png, answer = generator.new_char_captcha(length)
            self.assertEqual(len(answer), length)
            self.assertTrue(set(answer) <= pool)
            self.assertTrue(png.startswith(b'\x89PNG'))

    def test_arithmetic_answer_non_negative(self):
        for _ in range(20):
            png, answer = generator.new_arithmetic_captcha()
            self.assertGreaterEqual(int(answer), 0)
            self.assertTrue(png.startswith(b'\x89PNG'))
