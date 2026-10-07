"""消息推送 push · QQBot 一键部署（NapCat）单元测试

只测纯逻辑（配置生成、下载回退、状态机、探测），不真实下载、不拉起任何进程。
"""
import json
import os
import tempfile
import threading
from unittest import mock

from django.test import TestCase

from API.apis.push.qqbot import setup as qqbot_setup
from API.models import PushSetting


def _configure(**fields):
    setting = PushSetting.get_solo()
    for key, value in fields.items():
        setattr(setting, key, value)
    setting.save()
    return setting


class ConfigTests(TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='napcat-test-')
        _configure(qqbot_api_base='http://127.0.0.1:18908', qqbot_token='')

    def test_port_from_base(self):
        self.assertEqual(qqbot_setup._port_from_base('http://127.0.0.1:18908'), 18908)
        self.assertEqual(qqbot_setup._port_from_base(''), qqbot_setup.DEFAULT_HTTP_PORT)
        self.assertEqual(qqbot_setup._port_from_base('http://1.2.3.4:1234'), 1234)

    def test_write_configs_creates_http_server(self):
        token = qqbot_setup._write_configs(self.tmp)
        self.assertTrue(token)
        data = json.loads(open(os.path.join(self.tmp, 'config', 'onebot11.json'),
                               encoding='utf-8').read())
        servers = data['network']['httpServers']
        self.assertEqual(len(servers), 1)
        self.assertEqual(servers[0]['name'], 'xiaoYingHttp')
        self.assertEqual(servers[0]['port'], 18908)
        self.assertTrue(servers[0]['enable'])
        self.assertEqual(servers[0]['token'], token)
        webui = json.loads(open(os.path.join(self.tmp, 'config', 'webui.json'),
                                encoding='utf-8').read())
        self.assertEqual(webui['token'], token)
        self.assertEqual(webui['port'], qqbot_setup.DEFAULT_WEBUI_PORT)

    def test_write_configs_merges_without_duplicating(self):
        first = qqbot_setup._write_configs(self.tmp)
        second = qqbot_setup._write_configs(self.tmp)          # 第二次不应新增条目
        data = json.loads(open(os.path.join(self.tmp, 'config', 'onebot11.json'),
                               encoding='utf-8').read())
        self.assertEqual(len(data['network']['httpServers']), 1)
        self.assertEqual(first, second)                        # 已配 token 时沿用原值

    def test_write_configs_keeps_other_fields(self):
        path = os.path.join(self.tmp, 'config', 'onebot11.json')
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as fh:
            json.dump({'musicSignUrl': 'http://x', 'network': {'httpServers': []}}, fh)
        qqbot_setup._write_configs(self.tmp)
        data = json.loads(open(path, encoding='utf-8').read())
        self.assertEqual(data['musicSignUrl'], 'http://x')     # 其它字段原样保留

    def test_apply_setting_fills_base_when_empty(self):
        _configure(qqbot_api_base='')
        qqbot_setup._apply_setting('tok')
        setting = PushSetting.get_solo()
        self.assertEqual(setting.qqbot_api_base, f'http://127.0.0.1:{qqbot_setup.DEFAULT_HTTP_PORT}')
        self.assertEqual(setting.qqbot_token, 'tok')


class DownloadTests(TestCase):
    def test_falls_back_to_next_source(self):
        ok_response = mock.MagicMock()
        ok_response.__enter__.return_value = ok_response
        ok_response.headers = {'Content-Length': '10'}
        ok_response.iter_content.return_value = [b'0123456789']
        with mock.patch('requests.get', side_effect=[OSError('mirror down'), ok_response]) as get:
            target = os.path.join(tempfile.mkdtemp(prefix='napcat-dl-'), 'x.zip')
            used = qqbot_setup._download('NapCat.Shell.zip', target)
        self.assertEqual(get.call_count, 2)
        self.assertTrue(used)                                  # 第二次成功
        self.assertTrue(os.path.exists(target))

    def test_all_sources_fail(self):
        with mock.patch('requests.get', side_effect=OSError('boom')):
            with self.assertRaises(RuntimeError):
                qqbot_setup._download('x.zip', os.path.join(tempfile.mkdtemp(), 'x.zip'))


class StateTests(TestCase):
    """状态机与日志帧（把 _persist 打桩：TestCase 的事务里子线程写库会互相锁住）"""

    def test_start_pipeline_rejects_when_running(self):
        gate = threading.Event()
        with mock.patch.object(qqbot_setup, '_persist', return_value=None), \
                mock.patch.object(qqbot_setup, '_pipeline_windows',
                                  side_effect=lambda: gate.wait(5)):
            ok, _msg = qqbot_setup.start_pipeline()
            self.assertTrue(ok)
            ok2, msg2 = qqbot_setup.start_pipeline()       # 流程还没结束 → 应被拒绝
            self.assertFalse(ok2)
            self.assertIn('正在进行', msg2)
            gate.set()
            qqbot_setup._thread.join(timeout=5)
        self.assertEqual(qqbot_setup.current_state(), qqbot_setup.STATE_SUCCESS)
        frames, state = qqbot_setup.next_frames(0)
        self.assertTrue(frames)
        self.assertEqual(state, qqbot_setup.STATE_SUCCESS)

    def test_next_frames_since(self):
        with mock.patch.object(qqbot_setup, '_persist', return_value=None), \
                mock.patch.object(qqbot_setup, '_pipeline_windows', return_value=None):
            qqbot_setup.start_pipeline()
            qqbot_setup._thread.join(timeout=5)
        frames, _state = qqbot_setup.next_frames(0)
        self.assertTrue(frames)
        after = qqbot_setup.next_frames(frames[-1]['seq'])[0]
        self.assertEqual(after, [])


class ProbeTests(TestCase):
    def test_probe_shape(self):
        _configure(napcat_dir=tempfile.mkdtemp(prefix='napcat-probe-'),
                   qqbot_api_base='http://127.0.0.1:18908', napcat_qq='3766849790')
        info = qqbot_setup.probe()
        for key in ('platform', 'dir', 'installed', 'http_port', 'port_listening',
                    'webui_url', 'state', 'napcat_qq'):
            self.assertIn(key, info)
        self.assertEqual(info['http_port'], 18908)
        self.assertEqual(info['napcat_qq'], '3766849790')
        self.assertFalse(info['installed'])                    # 空目录 → 未安装
        self.assertIn(str(qqbot_setup.DEFAULT_WEBUI_PORT), info['webui_url'])


def _fake_run(stdout='', returncode=0, error=None):
    """伪造 subprocess.run 的返回（只取 stdout / returncode）"""
    result = mock.MagicMock()
    result.stdout = stdout
    result.returncode = returncode
    if error is not None:
        return mock.Mock(side_effect=error)
    return mock.Mock(return_value=result)


class DockerInspectTests(TestCase):
    """容器名过滤与 token 提取（`--filter name=` 是包含匹配，必须锚定）"""

    def test_container_state_anchors_name_filter(self):
        with mock.patch('subprocess.run', _fake_run('running\n')) as run:
            self.assertEqual(qqbot_setup._docker_container_state(), 'running')
        self.assertIn('name=^napcat$', run.call_args[0][0])

    def test_container_state_empty_when_absent(self):
        with mock.patch('subprocess.run', _fake_run('  \n')):
            self.assertEqual(qqbot_setup._docker_container_state(), '')

    def test_container_token_reads_env(self):
        env = 'PATH=/usr/bin\nNAPCAT_TOKEN=tok123\nHOME=/root\n'
        with mock.patch('subprocess.run', _fake_run(env)):
            self.assertEqual(qqbot_setup._docker_container_token(), 'tok123')

    def test_container_token_empty_when_not_docker_run(self):
        with mock.patch('subprocess.run', _fake_run('PATH=/usr/bin\n')):
            self.assertEqual(qqbot_setup._docker_container_token(), '')


class LinuxDockerReuseTests(TestCase):
    """Linux 一键部署遇到已存在的 napcat 容器：只复用、不重建

    线上真踩过：服务器重启后容器自动拉起，此时 `docker run --name napcat` 会因名字冲突
    返回 125 让整个部署失败；而删掉重建又会让 NapCat 把 QQ 当新设备、必须重新扫码。
    """

    def _run_linux(self, state, token=''):
        calls = []
        with mock.patch.object(qqbot_setup, '_docker_available', return_value=True), \
                mock.patch.object(qqbot_setup, '_docker_container_state', return_value=state), \
                mock.patch.object(qqbot_setup, '_docker_container_token', return_value=token), \
                mock.patch.object(qqbot_setup, '_run_cmd',
                                  side_effect=lambda cmd, timeout=300: calls.append(cmd)), \
                mock.patch.object(qqbot_setup, '_wait_ready', return_value=True), \
                mock.patch.object(qqbot_setup, '_apply_setting') as apply_setting, \
                mock.patch.object(qqbot_setup, '_persist', return_value=None):
            qqbot_setup._pipeline_linux()
        return calls, apply_setting

    def test_reuses_running_container_without_recreating(self):
        calls, apply_setting = self._run_linux('running', token='tok123')
        self.assertEqual(calls, [])                            # 既不重建也不必启动
        apply_setting.assert_called_once_with('tok123')

    def test_starts_stopped_container_instead_of_recreating(self):
        calls, apply_setting = self._run_linux('exited')
        self.assertEqual(calls, [['docker', 'start', qqbot_setup.DOCKER_CONTAINER]])
        apply_setting.assert_not_called()                      # 读不到 token 就不动现有配置

    def test_creates_container_when_absent(self):
        calls, apply_setting = self._run_linux('')
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][:4], ['docker', 'run', '-d', '--name'])
        self.assertEqual(calls[0][4], qqbot_setup.DOCKER_CONTAINER)
        apply_setting.assert_called_once()
