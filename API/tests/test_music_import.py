"""批量导入接口（import_musics）单元测试

覆盖场景：
- 正常导入：合法数据（多歌手/播放源/时间字段/关联）整体入库
- 部分失败：混入非法记录，成功/失败统计正确，失败记录无半成品
- 全量失败：所有记录非法，数据库零写入
- 并发导入：多线程同时导入互不干扰，数据总数正确
- 接口层：文件上传正常/超限/非法 JSON 的响应
"""
import json
import threading

from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connections
from django.test import Client, TestCase, TransactionTestCase

from API.apis.musics.xiaoying import utils
from API.models.Music.music import Music, MusicSource


def _valid_record(name='晴天', singers=None, online=None, sources=None):
    """构造一条合法记录（可覆盖指定字段）"""
    record = {'name': name, 'singer': singers or ['周杰伦']}
    if online is not None:
        record['online'] = online
    if sources is not None:
        record['music_sources'] = sources
    return record


class ImportSuccessTests(TestCase):
    """正常导入"""

    def test_import_valid_records_with_sources(self):
        records = [
            _valid_record('晴天', ['周杰伦'], sources=['https://example.com/a.mp3', 'https://example.com/b.mp3']),
            _valid_record('珊瑚海', ['周杰伦', '蔡依林']),
            _valid_record('稻香', ['周杰伦'], online=False),
        ]
        ok, data = utils.import_musics(records)

        self.assertTrue(ok)
        self.assertEqual(data['total'], 3)
        self.assertEqual(data['success_count'], 3)
        self.assertEqual(data['failed_count'], 0)
        self.assertEqual(data['failures'], [])

        self.assertEqual(Music.objects.count(), 3)
        self.assertEqual(MusicSource.objects.count(), 2)
        sunny = Music.objects.get(name='晴天')
        self.assertEqual(sunny.singer, ['周杰伦'])
        self.assertEqual(sunny.online, True)
        self.assertEqual(sunny.music_sources.count(), 2)
        coral = Music.objects.get(name='珊瑚海')
        self.assertEqual(coral.singer, ['周杰伦', '蔡依林'])
        # create_time 由模型自动填充
        self.assertIsNotNone(coral.create_time)
        self.assertIsNotNone(coral.updated_time)

    def test_import_empty_and_string_sources(self):
        records = [
            _valid_record('无源', sources=[]),
            _valid_record('单源字符串', sources='https://example.com/one.mp3'),
        ]
        ok, data = utils.import_musics(records)

        self.assertTrue(ok)
        self.assertEqual(data['success_count'], 2)
        self.assertEqual(Music.objects.count(), 2)
        self.assertEqual(MusicSource.objects.count(), 1)


class ImportPartialFailureTests(TestCase):
    """部分失败：合法记录入库，非法记录被筛出且不产生半成品"""

    def test_partial_failure_returns_details_and_no_partial_data(self):
        records = [
            _valid_record('正常1', sources=['https://example.com/a.mp3']),
            {'name': '', 'singer': ['歌手']},                          # 空 name
            _valid_record('正常2'),
            {'singer': ['歌手']},                                      # 缺 name
            _valid_record('非法url', sources=['not-a-url']),            # url 非法
            'not a dict',                                              # 非对象
            {'name': '缺singer'},                                      # 缺 singer
            {'name': '空singer', 'singer': []},                        # 空歌手列表
            _valid_record('超长name', sources=[]),                     # 超长 name(>200)
            _valid_record('超长url', sources=['https://example.com/' + 'x' * 600]),  # url 超长(>500)
            _valid_record('正常3', sources=['https://example.com/c.mp3']),
        ]
        records[8]['name'] = '长' * 201
        ok, data = utils.import_musics(records)

        self.assertTrue(ok)
        self.assertEqual(data['total'], 11)
        self.assertEqual(data['success_count'], 3)
        self.assertEqual(data['failed_count'], 8)
        self.assertEqual(len(data['failures']), 8)

        # 仅 3 条正常入库，非法记录无半成品
        self.assertEqual(Music.objects.count(), 3)
        self.assertEqual(MusicSource.objects.count(), 2)
        self.assertFalse(Music.objects.filter(name='非法url').exists())
        self.assertFalse(Music.objects.filter(name='长' * 201).exists())
        self.assertFalse(Music.objects.filter(name='超长url').exists())

        # 失败明细含 index / name / msg
        names = [f['name'] for f in data['failures']]
        msgs = [f['msg'] for f in data['failures']]
        self.assertEqual(sorted(f['index'] for f in data['failures']), [1, 3, 4, 5, 6, 7, 8, 9])
        self.assertIn('非法url', names)
        self.assertTrue(any('url' in m for m in msgs))
        self.assertTrue(any('最长 200 字符' in m for m in msgs))
        self.assertTrue(any('最长 500 字符' in m for m in msgs))


class ImportAllFailureTests(TestCase):
    """全量失败：所有记录非法，数据库零写入"""

    def test_all_invalid_records(self):
        records = [
            {'singer': ['歌手']},        # 缺 name
            {'name': ''},                # 空 name
            'oops',                      # 非对象
            {'name': 'x', 'singer': []}, # 空歌手
        ]
        ok, data = utils.import_musics(records)

        self.assertTrue(ok)
        self.assertEqual(data['total'], 4)
        self.assertEqual(data['success_count'], 0)
        self.assertEqual(data['failed_count'], 4)
        self.assertEqual(Music.objects.count(), 0)
        self.assertEqual(MusicSource.objects.count(), 0)


class ImportConcurrencyTests(TransactionTestCase):
    """并发导入：多线程同时导入互不干扰"""

    def tearDown(self):
        # 先执行 TransactionTestCase 的 flush，再关闭全部连接（含并发子线程创建的），
        # 释放 SQLite 文件锁，确保测试库可被正常删除
        super().tearDown()
        connections.close_all()

    def test_concurrent_import(self):
        thread_count, per_thread = 4, 25
        errors, results = [], []

        def worker(tid):
            try:
                records = [
                    _valid_record(f'并发{tid}-{i}', ['歌手'], sources=[f'https://example.com/{tid}-{i}.mp3'])
                    for i in range(per_thread)
                ]
                ok, data = utils.import_musics(records)
                if not ok:
                    errors.append(RuntimeError(f'线程{tid} 导入失败: {data}'))
                    return
                results.append(data)
            except Exception as e:  # pragma: no cover - 仅收集异常用于断言
                errors.append(e)
            finally:
                # 关闭本线程的数据库连接：connections 为线程局部，主线程无法代关，
                # 若不关闭会占用测试库文件导致测试结束无法删除
                connections.close_all()

        threads = [threading.Thread(target=worker, args=(t,)) for t in range(thread_count)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [])
        self.assertEqual(len(results), thread_count)
        self.assertEqual(sum(r['success_count'] for r in results), thread_count * per_thread)
        self.assertEqual(Music.objects.count(), thread_count * per_thread)
        self.assertEqual(MusicSource.objects.count(), thread_count * per_thread)


class ImportApiViewTests(TestCase):
    """接口层：文件上传导入"""

    def setUp(self):
        self.client = Client()
        self.url = '/api/music/xiaoying/import'

    @staticmethod
    def _file(content, name='musics.json'):
        return SimpleUploadedFile(name, content.encode('utf-8'), content_type='application/json')

    def test_upload_valid_file(self):
        payload = '[{"name": "接口导入", "singer": ["歌手"], "music_sources": ["https://example.com/api.mp3"]}]'
        resp = self.client.post(self.url, {'file': self._file(payload)})
        body = resp.json()
        self.assertEqual(body['code'], 10000)
        self.assertEqual(body['data']['success_count'], 1)
        self.assertEqual(Music.objects.filter(name='接口导入').count(), 1)
        self.assertEqual(MusicSource.objects.count(), 1)

    def test_upload_without_file(self):
        resp = self.client.post(self.url)
        body = resp.json()
        self.assertEqual(body['code'], 20001)
        self.assertIn('file', body['msg'])

    def test_upload_invalid_json(self):
        resp = self.client.post(self.url, {'file': self._file('{bad json')})
        body = resp.json()
        self.assertEqual(body['code'], 20002)
        self.assertIn('JSON 解析失败', body['msg'])

    def test_upload_over_limit(self):
        records = [{'name': f'超限{i}', 'singer': ['歌手']} for i in range(utils.MAX_IMPORT_COUNT + 1)]
        resp = self.client.post(self.url, {'file': self._file(json.dumps(records))})
        body = resp.json()
        self.assertEqual(body['code'], 20003)
        self.assertIn('单次最多导入', body['msg'])
        self.assertEqual(Music.objects.count(), 0)
