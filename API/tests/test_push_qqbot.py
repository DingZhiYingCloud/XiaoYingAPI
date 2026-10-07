"""消息推送 push · QQBot 线路 单元测试

全程 mock 上游 HTTP 请求，不触网、不发真实 QQ 消息。
覆盖：参数校验、未配置地址、发送成功/失败，以及「每次发送写入推送日志」与 QQBot 控制台页。
"""
import io
import json
from types import SimpleNamespace
from unittest import mock

import requests
from django.contrib.auth.models import User
from django.test import RequestFactory, TestCase

from API.apis.push.qqbot import ai_reply
from API.apis.push.qqbot import hook as qqbot_hook
from API.apis.push.qqbot import request as qqbot_request
from API.apis.push.qqbot import utils as qqbot_utils
from API.models import PushLog, PushSetting, QQPrivateMessage

POST_TARGET = 'API.apis.push.qqbot.utils.requests.post'


def _post(**data):
    return RequestFactory().post('/api/push/qqbot/send', data)


def _body(response):
    return json.loads(response.content)


def _configure(base='http://127.0.0.1:3000', token='tk'):
    setting = PushSetting.get_solo()
    setting.qqbot_api_base = base
    setting.qqbot_token = token
    setting.save()
    return setting


class QqbotSendViewTests(TestCase):
    def test_missing_params(self):
        body = _body(qqbot_request.send_view(_post(target_type='group')))
        self.assertEqual(body['code'], 20001)

    def test_invalid_target_type(self):
        body = _body(qqbot_request.send_view(_post(
            target_type='channel', target_id='123', message='hi')))
        self.assertEqual(body['code'], 20003)

    def test_target_id_must_be_digits(self):
        body = _body(qqbot_request.send_view(_post(
            target_type='group', target_id='abc', message='hi')))
        self.assertEqual(body['code'], 20002)

    def test_not_configured(self):
        body = _body(qqbot_request.send_view(_post(
            target_type='group', target_id='123456', message='hi')))
        self.assertEqual(body['code'], 40001)
        self.assertIn('QQBot', body['msg'])

    @mock.patch(POST_TARGET)
    def test_success(self, post):
        _configure()
        post.return_value = mock.Mock(json=lambda: {
            'status': 'ok', 'retcode': 0, 'data': {'message_id': 123456}, 'message': ''})
        request = _post(target_type='group', target_id='123456', message='告警正文')
        request.auth_app = SimpleNamespace(app_id='app_1')
        body = _body(qqbot_request.send_view(request))
        self.assertEqual(body['code'], 10000)
        self.assertEqual(body['data'], {'message_id': 123456})

        sent = post.call_args
        self.assertTrue(sent.args[0].endswith('/send_msg'))
        self.assertEqual(sent.kwargs['json'],
                         {'message_type': 'group', 'group_id': '123456',
                          'message': '告警正文', 'auto_escape': True})
        self.assertEqual(sent.kwargs['headers'], {'Authorization': 'Bearer tk'})

        log = PushLog.objects.get()
        self.assertEqual(log.channel, 'qqbot')
        self.assertEqual(log.title, '群 123456')
        self.assertEqual(log.content, '告警正文')
        self.assertEqual(log.recipients, '123456')
        self.assertEqual(log.app_id, 'app_1')
        self.assertTrue(log.ok)
        self.assertEqual(log.pushid, '123456')

    @mock.patch(POST_TARGET)
    def test_private_target_uses_user_id(self, post):
        _configure()
        post.return_value = mock.Mock(json=lambda: {
            'status': 'ok', 'retcode': 0, 'data': {'message_id': 1}, 'message': ''})
        _body(qqbot_request.send_view(_post(
            target_type='private', target_id='987654', message='hi')))
        self.assertEqual(post.call_args.kwargs['json']['user_id'], '987654')
        self.assertEqual(PushLog.objects.get().title, '私聊 987654')

    @mock.patch(POST_TARGET)
    def test_upstream_error_is_logged(self, post):
        _configure()
        post.return_value = mock.Mock(json=lambda: {
            'status': 'failed', 'retcode': 1404, 'data': None, 'message': '群不存在'})
        body = _body(qqbot_request.send_view(_post(
            target_type='group', target_id='123456', message='hi')))
        self.assertEqual(body['code'], 40001)
        self.assertIn('群不存在', body['msg'])
        log = PushLog.objects.get()
        self.assertFalse(log.ok)
        self.assertEqual(log.code, 1404)

    @mock.patch(POST_TARGET)
    def test_cq_code_disables_auto_escape(self, post):
        """正文含 CQ 码时按 CQ 发（auto_escape=False），否则会被当普通文字发出去"""
        _configure()
        post.return_value = mock.Mock(json=lambda: {
            'status': 'ok', 'retcode': 0, 'data': {'message_id': 1}, 'message': ''})
        _body(qqbot_request.send_view(_post(
            target_type='private', target_id='123456', message='[CQ:face,id=1]')))
        self.assertFalse(post.call_args.kwargs['json']['auto_escape'])

        post.reset_mock()
        _body(qqbot_request.send_view(_post(
            target_type='private', target_id='123456', message='普通文本')))
        self.assertTrue(post.call_args.kwargs['json']['auto_escape'])

    @mock.patch(POST_TARGET, side_effect=requests.RequestException('conn refused'))
    def test_network_error_is_logged(self, _mocked_post):
        _configure()
        body = _body(qqbot_request.send_view(_post(
            target_type='group', target_id='123456', message='hi')))
        self.assertEqual(body['code'], 40001)
        log = PushLog.objects.get()
        self.assertFalse(log.ok)
        self.assertIn('请求失败', log.message)


class QqbotUtilsTests(TestCase):
    def test_target_label(self):
        self.assertEqual(qqbot_utils.target_label('group', '123'), '群 123')
        self.assertEqual(qqbot_utils.target_label('private', '456'), '私聊 456')

    def test_login_info_not_configured(self):
        ok, message = qqbot_utils.get_login_info()
        self.assertFalse(ok)
        self.assertIn('未配置', message)

    @mock.patch('API.apis.push.qqbot.utils.requests.get')
    def test_login_info_success(self, get):
        _configure()
        get.return_value = mock.Mock(json=lambda: {
            'status': 'ok', 'retcode': 0,
            'data': {'user_id': 3766849790, 'nickname': '小影机器人'}})
        ok, info = qqbot_utils.get_login_info()
        self.assertTrue(ok)
        self.assertEqual(info, {'user_id': '3766849790', 'nickname': '小影机器人'})
        self.assertTrue(get.call_args.args[0].endswith('/get_login_info'))
        self.assertEqual(get.call_args.kwargs['headers'], {'Authorization': 'Bearer tk'})

    @mock.patch('API.apis.push.qqbot.utils.requests.get')
    def test_login_info_token_rejected(self, get):
        _configure()
        get.return_value = mock.Mock(json=lambda: {
            'status': 'failed', 'retcode': 1401, 'data': None, 'message': 'token 错误'})
        ok, message = qqbot_utils.get_login_info()
        self.assertFalse(ok)
        self.assertIn('token 错误', message)

    @mock.patch('API.apis.push.qqbot.utils.requests.get')
    def test_list_groups(self, get):
        _configure()
        get.return_value = mock.Mock(json=lambda: {
            'status': 'ok', 'retcode': 0,
            'data': [{'group_id': 111, 'group_name': '测试群A'},
                     {'group_id': 222, 'group_name': '测试群B'}]})
        ok, groups = qqbot_utils.list_groups()
        self.assertTrue(ok)
        self.assertEqual([g['group_id'] for g in groups], [111, 222])

    @mock.patch('API.apis.push.qqbot.utils.requests.get')
    def test_list_groups_failure(self, get):
        _configure()
        get.return_value = mock.Mock(json=lambda: {
            'status': 'failed', 'retcode': 1400, 'data': None, 'message': '未登录'})
        ok, message = qqbot_utils.list_groups()
        self.assertFalse(ok)
        self.assertIn('未登录', message)

    def test_flatten_message(self):
        """消息段数组拍平成可读文本：文本保留、非文本给中文占位符"""
        self.assertEqual(qqbot_utils.flatten_message('纯字符串'), '纯字符串')
        self.assertEqual(qqbot_utils.flatten_message([
            {'type': 'text', 'data': {'text': '你好'}},
            {'type': 'image', 'data': {'file': 'x.jpg'}},
            {'type': 'text', 'data': {'text': '在吗'}},
        ]), '你好[图片]在吗')
        self.assertEqual(qqbot_utils.flatten_message([
            {'type': 'poke', 'data': {}}, {'type': 'text', 'data': {'text': ' '}},
            {'type': 'unknown_seg', 'data': {}},
        ]), '[戳一戳] [unknown_seg]')


class ReplyComposeTests(TestCase):
    """回复内容组装：CQ 码透传、图片转 base64 图源、展示文本把 CQ 码换成占位符"""

    def test_cq_display(self):
        self.assertEqual(qqbot_utils.cq_display('你好[CQ:face,id=1]'), '你好[表情]')
        self.assertEqual(qqbot_utils.cq_display('[CQ:at,qq=10001] 在吗'), '@10001 在吗')
        self.assertEqual(qqbot_utils.cq_display('纯文本'), '纯文本')

    def test_build_reply_text_only(self):
        self.assertEqual(qqbot_utils.build_reply('你好', []), ('你好', '你好'))

    def test_build_reply_with_image(self):
        outgoing, display = qqbot_utils.build_reply('看图', ['data:image/png;base64,AAA'])
        self.assertEqual(outgoing, '看图 [CQ:image,file=base64://AAA]')
        self.assertEqual(display, '看图 [图片]')

    def test_build_reply_rejects_bad_image(self):
        with self.assertRaises(ValueError):
            qqbot_utils.build_reply('x', ['not-a-data-url'])

    def test_build_reply_rejects_too_many_images(self):
        with self.assertRaises(ValueError):
            qqbot_utils.build_reply(
                'x', ['data:image/png;base64,AA'] * (qqbot_utils.MAX_REPLY_IMAGES + 1))


PRIVATE_EVENT = {
    'post_type': 'message', 'message_type': 'private', 'sub_type': 'friend',
    'message_id': 123456, 'user_id': 123456789,
    'sender': {'user_id': 123456789, 'nickname': '小明'},
    'message': [{'type': 'text', 'data': {'text': '你好'}}],
    'time': 1700000000,
}


class QqbotHookTests(TestCase):
    """NapCat 事件上报回调：好友私聊消息落库（实时接收消息的唯一来源）"""

    def _post(self, payload, secret):
        request = RequestFactory().post(f'/hook/qqbot/{secret}/',
                                        data=json.dumps(payload),
                                        content_type='application/json')
        return qqbot_hook.hook_view(request, secret)

    def test_secret_mismatch_ignored(self):
        # 密钥不对：不落库，但照样回成功（不向外暴露差异）
        self.assertEqual(json.loads(self._post(PRIVATE_EVENT, 'wrong').content)['retcode'], 0)
        self.assertFalse(QQPrivateMessage.objects.exists())

    def test_private_message_recorded(self):
        secret = PushSetting.get_solo().hook_secret
        self._post(PRIVATE_EVENT, secret)
        row = QQPrivateMessage.objects.get()
        self.assertEqual(row.user_id, '123456789')
        self.assertEqual(row.nickname, '小明')
        self.assertEqual(row.content, '你好')
        self.assertEqual(row.message_id, '123456')
        self.assertIsNotNone(row.received_at)

    def test_duplicate_message_id_skipped(self):
        """上游重推同一条（message_id 相同）时不重复入库"""
        secret = PushSetting.get_solo().hook_secret
        self._post(PRIVATE_EVENT, secret)
        self._post(PRIVATE_EVENT, secret)
        self.assertEqual(QQPrivateMessage.objects.count(), 1)

    def test_group_message_ignored(self):
        secret = PushSetting.get_solo().hook_secret
        self._post({**PRIVATE_EVENT, 'message_type': 'group', 'group_id': 1}, secret)
        self.assertFalse(QQPrivateMessage.objects.exists())

    def test_other_events_ignored(self):
        secret = PushSetting.get_solo().hook_secret
        self._post({'post_type': 'notice', 'notice_type': 'friend_recall', 'user_id': 1}, secret)
        self._post({'post_type': 'request', 'request_type': 'friend', 'user_id': 1}, secret)
        self.assertFalse(QQPrivateMessage.objects.exists())


AI_CHAT_TARGET = 'API.apis.push.qqbot.ai_reply.ai_utils.chat_completion'


def _ai_target():
    """resolve_target() 的返回值（只需 chat_completion 会用到的字段）"""
    return {'key': 'demo', 'upstream': 'demo', 'url': 'http://up.example/chat/completions',
            'temperature': 0.7, 'max_tokens': 100, 'stop_list': [], 'api_key': 'k'}


class QqbotAiReplyTests(TestCase):
    """AI 自动回复：开关关闭不动现有行为、开启后按人格生成并发出、[SKIP] 不回"""

    def _enable(self, persona=None, enabled=True):
        setting = PushSetting.get_solo()
        setting.qqbot_api_base = 'http://127.0.0.1:3000'
        setting.qqbot_token = 'tk'
        setting.ai_reply_enabled = enabled
        if persona:
            setting.ai_persona = persona
        setting.save()
        return setting

    def _incoming(self, content='在吗'):
        return QQPrivateMessage.objects.create(
            user_id='123456789', nickname='小明', content=content,
            direction=QQPrivateMessage.Direction.IN)

    @mock.patch(POST_TARGET)
    @mock.patch(AI_CHAT_TARGET)
    @mock.patch('API.apis.push.qqbot.ai_reply.ai_utils.resolve_target')
    def test_generates_and_sends_reply(self, resolve, chat, post):
        self._enable()
        self._incoming()
        resolve.return_value = (_ai_target(), None)
        chat.return_value = (True, {'reply': '在的，怎么啦'})
        post.return_value = mock.Mock(json=lambda: {
            'status': 'ok', 'retcode': 0, 'data': {'message_id': 999}, 'message': ''})

        ok, reply = ai_reply.reply_to('123456789', '小明')

        self.assertTrue(ok)
        self.assertEqual(reply, '在的，怎么啦')
        # 发出的是纯文本（auto_escape=True）：模型输出不会被当成 CQ 码，杜绝注入
        sent = post.call_args.kwargs['json']
        self.assertEqual(sent['message'], '在的，怎么啦')
        self.assertEqual(sent['user_id'], '123456789')
        self.assertTrue(sent['auto_escape'])
        # 与手动回复同一口径落库，后台「好友消息」才看得到这次自动回复
        row = QQPrivateMessage.objects.get(direction=QQPrivateMessage.Direction.OUT)
        self.assertEqual(row.content, '在的，怎么啦')
        self.assertEqual(row.message_id, '999')

    @mock.patch(POST_TARGET)
    @mock.patch(AI_CHAT_TARGET)
    @mock.patch('API.apis.push.qqbot.ai_reply.ai_utils.resolve_target')
    def test_skip_token_means_silent_skip(self, resolve, chat, post):
        """模型输出 SKIP 标记（可能被裹上标点）时判定为不值得回，什么都不发"""
        self._enable()
        self._incoming('嗯')
        resolve.return_value = (_ai_target(), None)
        chat.return_value = (True, {'reply': '。[SKIP]。'})

        ok, _reason = ai_reply.reply_to('123456789', '小明')

        self.assertFalse(ok)
        post.assert_not_called()
        self.assertFalse(QQPrivateMessage.objects.filter(
            direction=QQPrivateMessage.Direction.OUT).exists())

    @mock.patch(AI_CHAT_TARGET)
    @mock.patch('API.apis.push.qqbot.ai_reply.ai_utils.resolve_target')
    def test_no_default_model_skips(self, resolve, chat):
        """后台没有可用 / 默认模型时：不发送，只把原因写进日志"""
        self._enable()
        self._incoming()
        resolve.return_value = (None, (503, '平台未设置默认 AI 模型'))

        ok, reason = ai_reply.reply_to('123456789', '小明')

        self.assertFalse(ok)
        self.assertIn('默认', reason)
        chat.assert_not_called()

    def test_persona_prompts_differ(self):
        """三种内置人格给出的系统提示词必须各不相同，且键与模型定义对得上"""
        prompts = {}
        for persona in PushSetting.Persona.values:
            setting = self._enable(persona=persona)
            prompts[persona] = ai_reply._system_prompt(setting, '小明', '123456789')

        self.assertEqual(len(set(prompts.values())), 3)
        self.assertEqual(set(prompts), set(PushSetting.Persona.values))
        self.assertIn('毒舌', prompts[PushSetting.Persona.SARCASTIC])
        self.assertIn('温柔', prompts[PushSetting.Persona.GENTLE])
        self.assertIn('幽默', prompts[PushSetting.Persona.HUMOROUS])

    @mock.patch('API.apis.push.qqbot.ai_reply.spawn')
    def test_hook_triggers_only_when_enabled(self, spawn):
        """开关关闭：落库照旧、完全不碰 AI；开启：落库后异步触发一次"""
        secret = PushSetting.get_solo().hook_secret

        def _report(message_id):
            request = RequestFactory().post(
                f'/hook/qqbot/{secret}/',
                data=json.dumps({**PRIVATE_EVENT, 'message_id': message_id}),
                content_type='application/json')
            return qqbot_hook.hook_view(request, secret)

        self.assertEqual(json.loads(_report(1).content)['retcode'], 0)
        self.assertEqual(QQPrivateMessage.objects.count(), 1)
        spawn.assert_not_called()

        self._enable()
        self.assertEqual(json.loads(_report(2).content)['retcode'], 0)
        spawn.assert_called_once()
        self.assertEqual(spawn.call_args.args[0], '123456789')

    def test_has_readable_text(self):
        """只有含文字的消息才算「有话头」；纯表情 / 图片、纯空白、纯 CQ 码都不算"""
        self.assertTrue(qqbot_utils.has_readable_text(
            [{'type': 'text', 'data': {'text': '在吗'}}, {'type': 'face', 'data': {'id': 1}}]))
        self.assertTrue(qqbot_utils.has_readable_text('在吗'))
        self.assertFalse(qqbot_utils.has_readable_text(
            [{'type': 'face', 'data': {'id': '1'}}]))
        self.assertFalse(qqbot_utils.has_readable_text(
            [{'type': 'text', 'data': {'text': '   '}}]))
        self.assertFalse(qqbot_utils.has_readable_text('[CQ:image,file=a.jpg]'))
        self.assertFalse(qqbot_utils.has_readable_text(None))

    @mock.patch('API.apis.push.qqbot.ai_reply.spawn')
    def test_hook_ignores_non_text_message(self, spawn):
        """纯表情消息：照常落库并回执，但不触发 AI"""
        self._enable()
        secret = PushSetting.get_solo().hook_secret
        event = {**PRIVATE_EVENT, 'message_id': 777,
                 'message': [{'type': 'face', 'data': {'id': '1'}}]}
        request = RequestFactory().post(f'/hook/qqbot/{secret}/',
                                        data=json.dumps(event),
                                        content_type='application/json')
        body = json.loads(qqbot_hook.hook_view(request, secret).content)
        self.assertEqual(body['retcode'], 0)
        self.assertEqual(QQPrivateMessage.objects.count(), 1)
        spawn.assert_not_called()


class QqbotHookRoutingTests(TestCase):
    """事件路由：好友添加成功 → 业务开场；带丸子单号的消息 → 搬单业务链路；其余走闲聊 AI"""

    def setUp(self):
        self.secret = PushSetting.get_solo().hook_secret

    def _post(self, payload):
        request = RequestFactory().post(f'/hook/qqbot/{self.secret}/',
                                        data=json.dumps(payload),
                                        content_type='application/json')
        return qqbot_hook.hook_view(request, self.secret)

    @mock.patch('API.apis.order_migration.qq_flow.spawn_greet')
    def test_friend_add_triggers_greet(self, greet):
        body = json.loads(self._post({'post_type': 'notice', 'notice_type': 'friend_add',
                                      'user_id': 123456789}).content)
        self.assertEqual(body['retcode'], 0)
        greet.assert_called_once()
        self.assertEqual(greet.call_args.args[0], '123456789')
        self.assertFalse(QQPrivateMessage.objects.exists())    # 通知事件不进消息表

    @mock.patch('API.apis.push.qqbot.ai_reply.spawn')
    @mock.patch('API.apis.order_migration.qq_flow.spawn_handle')
    def test_serial_message_routes_to_business(self, spawn_handle, ai_spawn):
        setting = PushSetting.get_solo()
        setting.ai_reply_enabled = True                        # 闲聊开着也不该抢答
        setting.save()
        self._post({**PRIVATE_EVENT, 'message_id': 9001,
                    'message': [{'type': 'text',
                                 'data': {'text': '我的单号 WZ20261006210929319040'}}]})
        spawn_handle.assert_called_once()
        ai_spawn.assert_not_called()

    @mock.patch('API.apis.push.qqbot.ai_reply.spawn')
    @mock.patch('API.apis.order_migration.qq_flow.spawn_handle')
    def test_plain_message_still_uses_chat_ai(self, spawn_handle, ai_spawn):
        setting = PushSetting.get_solo()
        setting.ai_reply_enabled = True
        setting.save()
        self._post({**PRIVATE_EVENT, 'message_id': 9002})
        spawn_handle.assert_not_called()
        ai_spawn.assert_called_once()

    @mock.patch('API.apis.push.qqbot.ai_reply.spawn')
    @mock.patch('API.apis.order_migration.qq_flow.spawn_handle')
    def test_taker_plain_message_routes_to_business(self, spawn_handle, ai_spawn):
        """打手（我们发过开场白）没给单号也要接话：按客服口径引导，不走闲聊 AI"""
        QQPrivateMessage.objects.create(
            user_id='123456789', content='你好，麻烦把丸子单号发我',
            direction=QQPrivateMessage.Direction.OUT, is_read=True, is_greeting=True)
        setting = PushSetting.get_solo()
        setting.ai_reply_enabled = True
        setting.save()
        self._post({**PRIVATE_EVENT, 'message_id': 9003})
        spawn_handle.assert_called_once()
        ai_spawn.assert_not_called()


class ChunkedBodyTests(TestCase):
    """开发服务器的 chunked 请求体解析（NapCat 上报用 chunked，Django runserver 默认读不到）"""

    def test_read_chunked(self):
        from API.common.devserver import _read_chunked

        raw = io.BytesIO(b'5\r\nhello\r\n6\r\n world\r\n0\r\n\r\n')
        self.assertEqual(_read_chunked(raw), b'hello world')

    def test_read_chunked_with_extension_and_trailer(self):
        from API.common.devserver import _read_chunked

        raw = io.BytesIO(b'c;ext=1\r\n' + '你好世界'.encode() + b'\r\n0\r\nX-Trace: 1\r\n\r\n')
        self.assertEqual(_read_chunked(raw).decode('utf-8'), '你好世界')

    def test_read_chunked_tolerates_truncated_body(self):
        """半截请求（EOF）按「读到多少算多少」处理，绝不卡死"""
        from API.common.devserver import _read_chunked

        raw = io.BytesIO(b'a\r\nabc')
        self.assertEqual(_read_chunked(raw), b'abc')


class QqbotConsoleTests(TestCase):
    """QQBot 控制台页：渲染（含好友消息面板）+ 回复 + 旧「推送设置」地址重定向"""

    def setUp(self):
        self.admin = User.objects.create_superuser('admin', 'a@example.com', 'pw')
        self.client.force_login(self.admin)

    def test_page_renders(self):
        response = self.client.get('/console/qqbot/')
        self.assertEqual(response.status_code, 200)

    def test_page_renders_ai_reply_section(self):
        """AI 自动回复区要真的渲染出来，三种内置人格都要在下拉里"""
        response = self.client.get('/console/qqbot/')
        self.assertContains(response, 'AI 自动回复')
        self.assertContains(response, 'AI 人格')
        for _value, label in PushSetting.Persona.choices:
            self.assertContains(response, label)

    def test_page_renders_thread_of_selected_chat(self):
        QQPrivateMessage.objects.create(user_id='123456789', nickname='小明', content='你好')
        response = self.client.get('/console/qqbot/', {'chat': '123456789'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '你好')

    def test_opening_chat_marks_its_messages_read(self):
        QQPrivateMessage.objects.create(user_id='123456789', nickname='小明', content='未读的')
        self.client.get('/console/qqbot/', {'chat': '123456789'})
        self.assertTrue(QQPrivateMessage.objects.get(user_id='123456789').is_read)

    def test_save_ai_reply_settings(self):
        response = self.client.post('/console/qqbot/', {
            'action': 'save', 'qqbot_api_base': 'http://127.0.0.1:3000',
            'qqbot_timeout': '15', 'ai_reply_enabled': 'on', 'ai_persona': 'humorous'})
        self.assertRedirects(response, '/console/qqbot/')
        setting = PushSetting.get_solo()
        self.assertTrue(setting.ai_reply_enabled)
        self.assertEqual(setting.ai_persona, 'humorous')

    def test_save_ai_reply_unchecked_means_off(self):
        """复选框不勾时该字段根本不会进 POST —— 按「关闭」处理"""
        setting = PushSetting.get_solo()
        setting.ai_reply_enabled = True
        setting.save()
        self.client.post('/console/qqbot/', {
            'action': 'save', 'qqbot_timeout': '15', 'ai_persona': 'gentle'})
        self.assertFalse(PushSetting.get_solo().ai_reply_enabled)

    def test_save_rejects_unknown_persona(self):
        self.client.post('/console/qqbot/', {
            'action': 'save', 'qqbot_timeout': '15', 'ai_persona': 'nope'})
        self.assertNotEqual(PushSetting.get_solo().ai_persona, 'nope')

    @mock.patch(POST_TARGET)
    def test_reply_sends_and_records_outgoing(self, post):
        _configure()
        post.return_value = mock.Mock(json=lambda: {
            'status': 'ok', 'retcode': 0, 'data': {'message_id': 77}, 'message': ''})
        response = self.client.post('/console/qqbot/',
                                    {'action': 'reply', 'to_user': '123456789', 'content': '收到'})
        self.assertRedirects(response, '/console/qqbot/?chat=123456789')

        row = QQPrivateMessage.objects.get()
        self.assertEqual(row.direction, QQPrivateMessage.Direction.OUT)
        self.assertEqual(row.user_id, '123456789')
        self.assertEqual(row.content, '收到')
        self.assertEqual(row.message_id, '77')

        sent = post.call_args
        self.assertTrue(sent.args[0].endswith('/send_msg'))
        self.assertEqual(sent.kwargs['json']['user_id'], '123456789')
        self.assertEqual(sent.kwargs['json']['message'], '收到')

    def test_reply_requires_receiver_and_content(self):
        response = self.client.post('/console/qqbot/', {'action': 'reply', 'content': 'x'})
        self.assertRedirects(response, '/console/qqbot/')       # 没选好友：回面板
        self.assertFalse(QQPrivateMessage.objects.exists())

    # ---- 无刷新用的两个 JSON 接口 ----
    def test_thread_endpoint_returns_messages_and_marks_read(self):
        QQPrivateMessage.objects.create(user_id='123456789', nickname='小明', content='在吗')
        response = self.client.get('/console/qqbot/messages/thread/', {'chat': '123456789'})
        data = response.json()
        self.assertTrue(data['ok'])
        self.assertEqual(data['chat'], '123456789')
        self.assertEqual(data['title'], '小明')
        self.assertEqual(data['messages'][0]['content'], '在吗')
        self.assertEqual(data['messages'][0]['direction'], 'in')
        self.assertTrue(QQPrivateMessage.objects.get().is_read)   # 打开即已读

    def test_thread_endpoint_rejects_bad_chat(self):
        response = self.client.get('/console/qqbot/messages/thread/', {'chat': 'abc'})
        self.assertFalse(response.json()['ok'])

    @mock.patch(POST_TARGET)
    def test_reply_endpoint_returns_item(self, post):
        _configure()
        post.return_value = mock.Mock(json=lambda: {
            'status': 'ok', 'retcode': 0, 'data': {'message_id': 88}, 'message': ''})
        response = self.client.post('/console/qqbot/messages/reply/',
                                    {'action': 'reply', 'to_user': '123456789', 'content': '好的'})
        data = response.json()
        self.assertTrue(data['ok'])
        # user_id / nickname 必须回给前端：发出后本地直接上屏要用它更新左侧会话项，
        # 缺了会导致 JS 报错、发送成功却提示「发送失败」
        self.assertEqual(data['item']['user_id'], '123456789')
        self.assertEqual(data['item']['nickname'], '')
        self.assertEqual(data['item']['direction'], 'out')
        self.assertEqual(data['item']['content'], '好的')
        self.assertTrue(QQPrivateMessage.objects.filter(
            direction=QQPrivateMessage.Direction.OUT, content='好的').exists())

    def test_reply_endpoint_validates(self):
        response = self.client.post('/console/qqbot/messages/reply/', {'content': 'x'})
        self.assertFalse(response.json()['ok'])
        self.assertFalse(QQPrivateMessage.objects.exists())

    @mock.patch(POST_TARGET)
    def test_reply_endpoint_with_image(self, post):
        """只发图片（不带文字）也应可发；上游收到的是 base64 图源，展示文本是 [图片]"""
        _configure()
        post.return_value = mock.Mock(json=lambda: {
            'status': 'ok', 'retcode': 0, 'data': {'message_id': 9}, 'message': ''})
        response = self.client.post('/console/qqbot/messages/reply/',
                                    {'action': 'reply', 'to_user': '123456789',
                                     'images': ['data:image/png;base64,AAA']})
        data = response.json()
        self.assertTrue(data['ok'])
        self.assertEqual(data['item']['content'], '[图片]')

        sent = post.call_args.kwargs['json']
        self.assertEqual(sent['message'], '[CQ:image,file=base64://AAA]')
        self.assertFalse(sent['auto_escape'])

    def test_star_endpoint_toggles(self):
        row = QQPrivateMessage.objects.create(user_id='123456789', content='要留的')
        response = self.client.post('/console/qqbot/messages/star/', {'id': row.pk})
        self.assertTrue(response.json()['starred'])
        self.assertTrue(QQPrivateMessage.objects.get(pk=row.pk).is_starred)

        response = self.client.post('/console/qqbot/messages/star/', {'id': row.pk})
        self.assertFalse(response.json()['starred'])
        self.assertFalse(QQPrivateMessage.objects.get(pk=row.pk).is_starred)

    def test_delete_endpoint_local(self):
        row = QQPrivateMessage.objects.create(user_id='123456789', content='删我')
        response = self.client.post('/console/qqbot/messages/delete/',
                                    {'id': row.pk, 'mode': 'local'})
        self.assertTrue(response.json()['ok'])
        self.assertFalse(QQPrivateMessage.objects.exists())

    @mock.patch(POST_TARGET)
    def test_delete_endpoint_recall(self, post):
        _configure()
        post.return_value = mock.Mock(json=lambda: {
            'status': 'ok', 'retcode': 0, 'data': None, 'message': ''})
        row = QQPrivateMessage.objects.create(
            user_id='123456789', content='我发的', direction=QQPrivateMessage.Direction.OUT,
            message_id='5')
        response = self.client.post('/console/qqbot/messages/delete/',
                                    {'id': row.pk, 'mode': 'recall'})
        self.assertTrue(response.json()['ok'])
        self.assertTrue(post.call_args.args[0].endswith('/delete_msg'))
        self.assertEqual(post.call_args.kwargs['json'], {'message_id': 5})
        self.assertFalse(QQPrivateMessage.objects.exists())

    def test_delete_endpoint_rejects_recalling_incoming(self):
        row = QQPrivateMessage.objects.create(user_id='123456789', content='别人发的')
        response = self.client.post('/console/qqbot/messages/delete/',
                                    {'id': row.pk, 'mode': 'recall'})
        self.assertFalse(response.json()['ok'])
        self.assertTrue(QQPrivateMessage.objects.exists())      # 别人的消息撤回不了，也没被删

    def test_old_push_settings_url_redirects(self):
        response = self.client.get('/console/push-settings/')
        self.assertRedirects(response, '/console/qqbot/')
