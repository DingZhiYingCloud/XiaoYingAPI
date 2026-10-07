"""代练通「上传首图」单元测试

覆盖：
- 爬虫工具：OSS 对象名规则 / policy+签名算法 / 图片扩展名推断
- 爬虫：图片直传 OSS（成功 / 非 200）、首图逐张挂单（成功 / 第 2 张失败 / 下载失败）
- 视图契约：必填校验、image_url_2 可选、参数透传业务层
"""
import base64
import hashlib
import hmac
import json
import sys
from unittest import mock

from django.test import RequestFactory, TestCase

from API.apis.DaiLianTong import request as dlt_request
from API.apis.DaiLianTong import utils as dlt_utils

_home = sys.modules['home']              # 爬虫业务模块（由 utils 注入 sys.path 后导入）
_oss = sys.modules['utils']              # 爬虫工具模块（OSS 常量都在这里）
DaiLianTongService = dlt_utils.DaiLianTongService


class OssHelperTests(TestCase):
    """爬虫工具：对象名规则 + policy/签名算法 + 扩展名推断"""

    def test_object_key_format(self):
        key = _home.oss_object_key('jpg')
        # Progress/<时><分><4位随机大写字母><4位随机数>.<扩展名>
        self.assertRegex(key, r'^Progress/\d{2,4}[A-Z]{4}\d{4}\.jpg$')

    def test_object_key_normalizes_ext(self):
        self.assertTrue(_home.oss_object_key('.PNG').endswith('.png'))
        self.assertTrue(_home.oss_object_key('').endswith('.png'))

    def test_policy_and_signature_match_frontend_algorithm(self):
        policy, signature = _home.oss_policy_and_signature()

        decoded = json.loads(base64.b64decode(policy).decode('utf-8'))
        self.assertIn('expiration', decoded)
        self.assertEqual(decoded['conditions'], [['content-length-range', 0, _oss.OSS_MAX_SIZE]])

        expected = base64.b64encode(hmac.new(
            _oss.OSS_ACCESS_KEY_SECRET.encode('utf-8'), policy.encode('utf-8'),
            hashlib.sha1).digest()).decode('utf-8')
        self.assertEqual(signature, expected)

    def test_guess_image_ext(self):
        self.assertEqual(_home.guess_image_ext('http://a/1.JPEG?x=1'), 'jpg')
        self.assertEqual(_home.guess_image_ext('http://a/1', 'image/webp'), 'webp')
        self.assertEqual(_home.guess_image_ext('http://a/1', 'text/plain'), 'png')

    def test_image_content_type(self):
        self.assertEqual(_home.image_content_type('jpg'), 'image/jpeg')
        self.assertEqual(_home.image_content_type('.PNG'), 'image/png')
        self.assertEqual(_home.image_content_type(''), 'image/png')


class UploadImageToOssTests(TestCase):
    """爬虫层：图片直传阿里云 OSS"""

    def setUp(self):
        with mock.patch.object(_home, 'SIGN_KEY', 'test_sign_key'):
            self.service = DaiLianTongService()

    def test_success_returns_cdn_url(self):
        response = mock.Mock(status_code=200)
        with mock.patch.object(_home.requests, 'post', return_value=response) as posted:
            result = self.service.upload_image_to_oss(b'png-bytes', ext='png')

        self.assertEqual(result['code'], 0)
        key = result['data']['key']
        self.assertTrue(key.startswith('Progress/'))
        self.assertEqual(result['data']['url'], f'{_oss.IMG_SERVER_URL}/{key}')

        sent = posted.call_args
        self.assertEqual(sent.args[0], _oss.OSS_UPLOAD_URL)
        self.assertEqual(sent.kwargs['data']['OSSAccessKeyId'], _oss.OSS_ACCESS_KEY_ID)
        self.assertEqual(sent.kwargs['data']['key'], key)
        self.assertEqual(sent.kwargs['data']['success_action_status'], '200')
        self.assertIn('policy', sent.kwargs['data'])
        self.assertIn('signature', sent.kwargs['data'])
        self.assertIn('file', sent.kwargs['files'])

    def test_non_200_returns_error(self):
        response = mock.Mock(status_code=403)
        with mock.patch.object(_home.requests, 'post', return_value=response):
            result = self.service.upload_image_to_oss(b'x', ext='png')
        self.assertEqual(result['code'], 1)
        self.assertIn('403', result['message'])


class UploadFirstImageCrawlerTests(TestCase):
    """爬虫层：外链图片转存 OSS 后逐张以「首图」挂到订单上"""

    def setUp(self):
        with mock.patch.object(_home, 'SIGN_KEY', 'test_sign_key'):
            self.service = DaiLianTongService()
        self.service.session = mock.Mock()
        self.service.session.post.return_value = mock.Mock()

    @staticmethod
    def _image_response():
        response = mock.Mock(content=b'png-bytes', status_code=200)
        response.headers = {'Content-Type': 'image/png'}
        response.raise_for_status = mock.Mock()
        return response

    @staticmethod
    def _oss_ok(name):
        return {'code': 0, 'message': '上传成功',
                'data': {'key': name, 'url': f'https://img001.dailiantong.com.cn/{name}'}}

    def test_uploads_each_image_then_attaches(self):
        with mock.patch.object(_home.requests, 'get',
                               side_effect=[self._image_response(), self._image_response()]), \
             mock.patch.object(self.service, 'upload_image_to_oss',
                               side_effect=[self._oss_ok('Progress/1AAAA1111.png'),
                                            self._oss_ok('Progress/2BBBB2222.png')]), \
             mock.patch.object(_home, 'parse_response',
                               return_value={'code': 0, 'message': 'ok', 'data': {'Result': 1}}):
            result = self.service.upload_first_image(
                '10718808437372810349', ['https://x/1.png', 'https://x/2.png'],
                token='tok', user_id=24479174)

        self.assertEqual(result['code'], 0)
        self.assertEqual(result['data']['images'], [
            'https://img001.dailiantong.com.cn/Progress/1AAAA1111.png',
            'https://img001.dailiantong.com.cn/Progress/2BBBB2222.png',
        ])
        calls = self.service.session.post.call_args_list
        self.assertEqual(len(calls), 2)                      # 每张调一次上游
        for index, call in enumerate(calls):
            self.assertEqual(call.kwargs['params'], {'Action': 'LevelOrderProgressAdd'})
            sent = call.kwargs['data']
            self.assertEqual(sent['ODSerialNo'], '10718808437372810349')
            self.assertEqual(sent['Tier'], '')               # 官方必传（空串）
            self.assertEqual(sent['Msg'], '首图')
            self.assertEqual(sent['Img'], result['data']['images'][index])
            self.assertEqual(sent['OrderWinTxt'], '')        # 官方必传（空串）
            self.assertEqual(sent['UserID'], '24479174')     # 官方 web_query 自动补

    def test_second_image_attach_failure_reports_index(self):
        with mock.patch.object(_home.requests, 'get',
                               side_effect=[self._image_response(), self._image_response()]), \
             mock.patch.object(self.service, 'upload_image_to_oss',
                               side_effect=[self._oss_ok('Progress/1AAAA1111.png'),
                                            self._oss_ok('Progress/2BBBB2222.png')]), \
             mock.patch.object(_home, 'parse_response',
                               side_effect=[{'code': 0, 'message': 'ok', 'data': {}},
                                            {'code': 1, 'message': '订单不存在'}]):
            result = self.service.upload_first_image(
                '1071', ['https://x/1.png', 'https://x/2.png'], token='tok')

        self.assertEqual(result['code'], 1)
        self.assertIn('第 2 张', result['message'])
        self.assertIn('订单不存在', result['message'])
        # 已挂上的第 1 张仍然有效（透出，方便调用方判断）
        self.assertEqual(result['data']['images'],
                         ['https://img001.dailiantong.com.cn/Progress/1AAAA1111.png'])

    def test_download_failure_returns_error(self):
        with mock.patch.object(_home.requests, 'get', side_effect=RuntimeError('boom')):
            result = self.service.upload_first_image('1071', ['https://x/1.png'], token='tok')
        self.assertEqual(result['code'], 1)
        self.assertIn('第 1 张图片下载失败', result['message'])


class UploadFirstImageViewTests(TestCase):
    """视图层：必填校验与参数透传"""

    def setUp(self):
        self.factory = RequestFactory()

    @staticmethod
    def _ok():
        return True, {'code': 0, 'message': 'ok', 'data': {}}

    def test_requires_order_id(self):
        with mock.patch.object(dlt_request.utils, 'upload_first_image',
                               return_value=self._ok()) as mocked:
            request = self.factory.post('/x', {'image_url_1': 'https://x/1.png'})
            body = json.loads(dlt_request.upload_first_image_view(request).content)
        self.assertEqual(body['code'], 20001)
        mocked.assert_not_called()

    def test_requires_first_image(self):
        with mock.patch.object(dlt_request.utils, 'upload_first_image',
                               return_value=self._ok()) as mocked:
            request = self.factory.post('/x', {'order_id': '1071'})
            body = json.loads(dlt_request.upload_first_image_view(request).content)
        self.assertEqual(body['code'], 20001)
        mocked.assert_not_called()

    def test_single_image_is_allowed(self):
        with mock.patch.object(dlt_request.utils, 'upload_first_image',
                               return_value=self._ok()) as mocked:
            request = self.factory.post('/x', {'order_id': '1071', 'image_url_1': 'https://x/1.png'})
            body = json.loads(dlt_request.upload_first_image_view(request).content)
        self.assertEqual(body['code'], 10000)
        self.assertEqual(mocked.call_args.args[0], '1071')
        self.assertEqual(mocked.call_args.args[1], ['https://x/1.png'])

    def test_two_images_forwarded_in_order(self):
        with mock.patch.object(dlt_request.utils, 'upload_first_image',
                               return_value=self._ok()) as mocked:
            request = self.factory.post('/x', {'order_id': '1071',
                                               'image_url_1': 'https://x/1.png',
                                               'image_url_2': 'https://x/2.png'})
            dlt_request.upload_first_image_view(request)
        self.assertEqual(mocked.call_args.args[1], ['https://x/1.png', 'https://x/2.png'])

    def test_upstream_failure_maps_to_40001(self):
        with mock.patch.object(dlt_request.utils, 'upload_first_image',
                               return_value=(False, '第 1 张图片下载失败: boom')):
            request = self.factory.post('/x', {'order_id': '1071', 'image_url_1': 'https://x/1.png'})
            body = json.loads(dlt_request.upload_first_image_view(request).content)
        self.assertEqual(body['code'], 40001)
        self.assertIn('下载失败', body['msg'])


class UploadEndImageCrawlerTests(TestCase):
    """爬虫层：完单图逐张挂单 + 自动申请完单"""

    def setUp(self):
        with mock.patch.object(_home, 'SIGN_KEY', 'test_sign_key'):
            self.service = DaiLianTongService()
        self.service.session = mock.Mock()
        self.service.session.post.return_value = mock.Mock()

    @staticmethod
    def _image_response():
        response = mock.Mock(content=b'png-bytes', status_code=200)
        response.headers = {'Content-Type': 'image/png'}
        response.raise_for_status = mock.Mock()
        return response

    @staticmethod
    def _oss_ok(name):
        return {'code': 0, 'message': '上传成功',
                'data': {'key': name, 'url': f'https://img001.dailiantong.com.cn/{name}'}}

    def test_uploads_images_then_requests_over(self):
        with mock.patch.object(_home.requests, 'get',
                               side_effect=[self._image_response(), self._image_response()]), \
             mock.patch.object(self.service, 'upload_image_to_oss',
                               side_effect=[self._oss_ok('Progress/1AAAA1111.png'),
                                            self._oss_ok('Progress/2BBBB2222.png')]), \
             mock.patch.object(_home, 'parse_response',
                               side_effect=[{'code': 0, 'message': 'ok', 'data': {'Result': 1}},
                                            {'code': 0, 'message': 'ok', 'data': {'Result': 1}},
                                            {'code': 0, 'message': 'ok', 'data': {'Result': 1}}]):
            result = self.service.upload_end_image(
                '10718808437372810349', ['https://x/1.png', 'https://x/2.png'],
                token='tok', user_id=24479174, uid='USR123')

        self.assertEqual(result['code'], 0)
        self.assertIn('已申请完单', result['message'])
        self.assertEqual(len(result['data']['images']), 2)
        self.assertEqual(result['data']['over'], {'Result': 1})

        calls = self.service.session.post.call_args_list
        self.assertEqual(len(calls), 3)                       # 2 张图 + 1 次申请完单
        for index in range(2):                                # 前两次：完单图挂单
            sent = calls[index].kwargs['data']
            self.assertEqual(calls[index].kwargs['params'], {'Action': 'LevelOrderProgressAdd'})
            self.assertEqual(sent['Msg'], '完单图')
            self.assertEqual(sent['Tier'], '')
            self.assertEqual(sent['OrderWinTxt'], '')
            self.assertEqual(sent['UserID'], '24479174')
        over = calls[2]                                       # 第三次：申请完单
        self.assertEqual(over.kwargs['params'], {'Action': 'LevelOrderOver'})
        self.assertEqual(over.kwargs['data']['ODSerialNo'], '10718808437372810349')
        self.assertEqual(over.kwargs['data']['Flag'], '0')
        self.assertEqual(over.kwargs['data']['IsShareTrends'], '1')
        self.assertEqual(over.kwargs['data']['UserID'], '24479174')
        self.assertEqual(over.kwargs['data']['PayPass'],
                         _home.md5_encrypt(_home.md5_encrypt('') + 'USR123'))

    def test_image_failure_skips_request_over(self):
        with mock.patch.object(_home.requests, 'get',
                               side_effect=[self._image_response(), self._image_response()]), \
             mock.patch.object(self.service, 'upload_image_to_oss',
                               side_effect=[self._oss_ok('Progress/1AAAA1111.png'),
                                            self._oss_ok('Progress/2BBBB2222.png')]), \
             mock.patch.object(_home, 'parse_response',
                               side_effect=[{'code': 0, 'message': 'ok', 'data': {}},
                                            {'code': 1, 'message': '参数错误.'}]):
            result = self.service.upload_end_image(
                '1071', ['https://x/1.png', 'https://x/2.png'], token='tok', user_id=1)

        self.assertEqual(result['code'], 1)
        self.assertIn('第 2 张', result['message'])
        # 图片没全部挂成功，不应发起申请完单
        self.assertEqual(len(self.service.session.post.call_args_list), 2)

    def test_request_over_failure_reports_partial(self):
        with mock.patch.object(_home.requests, 'get',
                               side_effect=[self._image_response()]), \
             mock.patch.object(self.service, 'upload_image_to_oss',
                               side_effect=[self._oss_ok('Progress/1AAAA1111.png')]), \
             mock.patch.object(_home, 'parse_response',
                               side_effect=[{'code': 0, 'message': 'ok', 'data': {}},
                                            {'code': 1, 'message': '余额不足'}]):
            result = self.service.upload_end_image(
                '1071', ['https://x/1.png'], token='tok', user_id=1, uid='U')

        self.assertEqual(result['code'], 1)
        self.assertIn('申请完单失败', result['message'])
        self.assertIn('余额不足', result['message'])
        # 图片已挂上，需透出（方便调用方判断是否有残留）
        self.assertEqual(result['data']['images'],
                         ['https://img001.dailiantong.com.cn/Progress/1AAAA1111.png'])


class UploadEndImageViewTests(TestCase):
    """视图层：必填校验与参数透传"""

    def setUp(self):
        self.factory = RequestFactory()

    @staticmethod
    def _ok():
        return True, {'code': 0, 'message': 'ok', 'data': {}}

    def test_requires_order_id(self):
        with mock.patch.object(dlt_request.utils, 'upload_end_image',
                               return_value=self._ok()) as mocked:
            request = self.factory.post('/x', {'image_url_1': 'https://x/1.png'})
            body = json.loads(dlt_request.upload_end_image_view(request).content)
        self.assertEqual(body['code'], 20001)
        mocked.assert_not_called()

    def test_requires_first_image(self):
        with mock.patch.object(dlt_request.utils, 'upload_end_image',
                               return_value=self._ok()) as mocked:
            request = self.factory.post('/x', {'order_id': '1071'})
            body = json.loads(dlt_request.upload_end_image_view(request).content)
        self.assertEqual(body['code'], 20001)
        mocked.assert_not_called()

    def test_two_images_forwarded_in_order(self):
        with mock.patch.object(dlt_request.utils, 'upload_end_image',
                               return_value=self._ok()) as mocked:
            request = self.factory.post('/x', {'order_id': '1071',
                                               'image_url_1': 'https://x/1.png',
                                               'image_url_2': 'https://x/2.png'})
            body = json.loads(dlt_request.upload_end_image_view(request).content)
        self.assertEqual(body['code'], 10000)
        self.assertEqual(mocked.call_args.args[0], '1071')
        self.assertEqual(mocked.call_args.args[1], ['https://x/1.png', 'https://x/2.png'])

    def test_upstream_failure_maps_to_40001(self):
        with mock.patch.object(dlt_request.utils, 'upload_end_image',
                               return_value=(False, '第 1 张图片下载失败: boom')):
            request = self.factory.post('/x', {'order_id': '1071', 'image_url_1': 'https://x/1.png'})
            body = json.loads(dlt_request.upload_end_image_view(request).content)
        self.assertEqual(body['code'], 40001)
        self.assertIn('下载失败', body['msg'])
