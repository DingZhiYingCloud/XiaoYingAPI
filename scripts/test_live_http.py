"""真实 HTTP 环境完整验证脚本（对运行中的服务器发真实请求）

覆盖：
    1. open 节点（captcha 开放集成）无签名访问   -> 正常业务返回
    2. 认证分类无签名访问        -> 20011 签名参数缺失（复现用户反馈）
    3. 认证分类带正确签名访问    -> 正常业务返回
    4. 认证分类带错误签名        -> 20011 签名不匹配
    5. 认证分类带过期时间戳      -> 20011 签名过期
    6. 认证分类未注册 app_id     -> 20011 未注册
    7. 停用项目签名访问          -> 20011 停用
    8. open 节点带签名访问       -> 不受影响，正常返回
    9. 认证分类 POST 表单带签名  -> 正常业务返回
   10. 认证分类带签名访问不存在路径 -> JSON 404（非认证错误）
"""
import json
import os
import secrets
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'XiaoYingAPI.settings')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import django

django.setup()

from API.models import UserApp
from API.apis.user_center.sign import build_sign

BASE = 'http://127.0.0.1:10001'
_stats = {'pass': 0, 'fail': 0}


def check(name, cond, extra=''):
    if cond:
        _stats['pass'] += 1
        print(f'  [PASS] {name}')
    else:
        _stats['fail'] += 1
        print(f'  [FAIL] {name} {extra}')


def request(method, path, params=None, app=None, sign=True):
    """发送真实 HTTP 请求；sign=True 时自动附加并计算签名参数"""
    p = {}
    if sign:
        p = {
            'app_id': app.app_id,
            'timestamp': str(int(time.time())),
            'nonce': secrets.token_hex(8),
        }
        if params:
            p.update(params)
        p['sign'] = build_sign(p, app.app_secret)
    elif params:
        p = params
    url = BASE + path
    if method == 'GET':
        if p:
            url += '?' + urllib.parse.urlencode(p)
        data = None
    else:
        data = urllib.parse.urlencode(p).encode()
    req = urllib.request.Request(url, data=data, method=method)
    try:
        resp = urllib.request.urlopen(req, timeout=10)
        return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode())
        except Exception:
            return e.code, {}
    except Exception as e:
        return 0, {'msg': str(e)}


def main():
    print(f'真实 HTTP 验证开始 -> {BASE}')
    app = UserApp.objects.create(name=f'LIVE{int(time.time())}', token_expire_days=7, status=True)
    try:
        # 1. 显式 open 节点（captcha_auth/aliyun 开放集成，config 供 H5 前端初始化）：无签名直接通过
        st, r = request('GET', '/api/captcha_auth/aliyun/config', sign=False)
        check('open 节点-无签名访问正常返回', st == 200 and r.get('code') == 10000, f'st={st} r={r}')

        # 2. 认证分类（music 已设 auth）：无签名 -> 20011 签名参数缺失（复现用户反馈）
        st, r = request('GET', '/api/music/xiaoying/musics', sign=False)
        check('认证分类-无签名被拦截(20011)', r.get('code') == 20011, f'st={st} r={r}')
        check('拦截提示为签名参数缺失', '签名参数缺失' in (r.get('msg') or ''), f'msg={r.get("msg")}')

        # 3. 认证分类（music）：带正确签名 -> 触达业务层（非 20011）
        st, r = request('GET', '/api/music/xiaoying/musics', app=app)
        check('认证分类-带签名正常通过', r.get('code') != 20011, f'st={st} code={r.get("code")}')

        # 4. 认证分类（user_center）：带签名 -> 业务正常
        st, r = request('GET', '/api/user_center/projects/info', app=app)
        check('认证分类(user_center)-带签名正常', r.get('code') == 10000, f'st={st} r={r}')

        # 5. 错误签名
        bad = {'app_id': app.app_id, 'timestamp': str(int(time.time())),
               'nonce': secrets.token_hex(8), 'sign': '0' * 64}
        st, r = request('GET', '/api/music/xiaoying/musics', params=bad, sign=False)
        check('认证分类-错误签名被拦截', r.get('code') == 20011 and '不匹配' in (r.get('msg') or ''), f'msg={r.get("msg")}')

        # 6. 过期时间戳（10 分钟前）
        old = {'app_id': app.app_id, 'timestamp': str(int(time.time()) - 600),
               'nonce': secrets.token_hex(8)}
        old['sign'] = build_sign(old, app.app_secret)
        st, r = request('GET', '/api/music/xiaoying/musics', params=old, sign=False)
        check('认证分类-过期时间戳被拦截', r.get('code') == 20011 and '过期' in (r.get('msg') or ''), f'msg={r.get("msg")}')

        # 7. 未注册 app_id
        ghost = {'app_id': 'app_ghost' * 4, 'timestamp': str(int(time.time())), 'nonce': secrets.token_hex(8)}
        ghost['sign'] = build_sign(ghost, 'sk_fake')
        st, r = request('GET', '/api/music/xiaoying/musics', params=ghost, sign=False)
        check('认证分类-未注册app_id被拦截', r.get('code') == 20011 and '未注册' in (r.get('msg') or ''), f'msg={r.get("msg")}')

        # 8. 停用项目
        app.status = False
        app.save()
        st, r = request('GET', '/api/music/xiaoying/musics', app=app)
        check('认证分类-停用项目被拦截', r.get('code') == 20011 and '停用' in (r.get('msg') or ''), f'msg={r.get("msg")}')
        app.status = True
        app.save()

        # 9. open 节点带签名访问也不受影响
        st, r = request('GET', '/api/captcha_auth/aliyun/config', app=app)
        check('open 节点-带签名同样正常', r.get('code') == 10000, f'code={r.get("code")}')

        # 10. 认证分类 POST 表单带签名：中间件放行到达业务层
        # 登录对「不存在的账号」返回 20011（业务认证失败，不暴露细节）；
        # 只要 msg 不是「接口未配置项目认证」，即证明中间件已放行（auth_app 已挂载）
        st, r = request('POST', '/api/user_center/users/login',
                        params={'account': '0', 'password': 'x'}, app=app)
        check('认证分类-POST表单签名通过(到达业务层)', r.get('code') == 20011 and '项目认证' not in (r.get('msg') or ''),
              f'code={r.get("code")} msg={r.get("msg")}')

        # 11. 认证分类带签名访问不存在路径 -> JSON 404
        st, r = request('GET', '/api/music/not_exists_xyz', app=app)
        check('认证分类-签名通过后404兜底JSON', st == 404 and r.get('code') != 20011, f'st={st} r={r}')
    finally:
        UserApp.objects.filter(id=app.id).delete()
        print(f'\n清理测试项目完成')

    total = _stats['pass'] + _stats['fail']
    print(f'\n========== 汇总 ==========')
    print(f'通过: {_stats["pass"]}  |  失败: {_stats["fail"]}  |  总计: {total}')
    sys.exit(1 if _stats['fail'] else 0)


if __name__ == '__main__':
    main()
