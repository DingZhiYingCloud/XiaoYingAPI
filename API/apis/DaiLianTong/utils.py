"""代练通 DaiLianTong 爬虫调用封装

本模块在 sys.path 中注入爬虫目录后，导入原始爬虫类进行包装:
- 每次调用创建新的爬虫实例（无状态、线程安全）
- 统一捕获异常，返回 (success, data_or_msg) 二元组
"""
import json
import logging
import sys
import os
import time

from API.apis.DaiLianTong.games import (DEFAULT_GAME_ID, enabled_games, get_profile,
                                       is_supported_game)

from API.common import platform_accounts

logger = logging.getLogger('api.dailiantong')

# 平台账号标识：默认代练通账号在超管控制台 /console/accounts/ 维护，
# 凭据（credential）约定为 JSON：{"user_id": "...", "token": "...", "uid": "USR...",
#                                 "login_id": "<登录手机号，自动重登用>", "pay_pass": "..."}
# 自动重登还需账号表里的 password 字段（AES 加密存登录密码）。
PLATFORM = 'dlt'

# 「我的订单」状态筛选：中文名 -> (Status, CancelStatus, OverDays)
# 与官网「我的订单」页筛选面板一致：进行中组 OverDays=-99、已结束组 OverDays=99。
# 供接口的 state 便捷参数使用（视图与文档共用同一份，避免两处漂移）。
MY_ORDER_STATES = {
    # 进行中
    '全部': (0, 0, -99),
    '待付款': (19, 0, -99),
    '未接手': (11, 0, -99),
    '正在代练': (12, 0, -99),
    '等待验收': (13, 0, -99),
    '订单异常': (14, 0, -99),
    '锁定订单': (15, 0, -99),
    '申请撤销中': (16, 11, -99),
    '仲裁介入中': (0, 14, -99),
    # 已结束
    '协商已处理': (0, 12, 99),
    '仲裁已处理': (0, 15, 99),
    '客服强制撤销': (0, 16, 99),
    '已结算': (17, 0, 99),
}

# 「申请撤销」账号进度（页面 pk_ProgressJson，仅用于生成撤销说明文本）
CANCEL_PROGRESS_OPTIONS = ['有进度', '无进度', '负进度', '未开始代练']
# 「申请撤销」撤销意愿（发单者视角，id -> 文案；金额占位 {amount}）
CANCEL_DESIRE_OPTIONS = {
    '0': '我愿意支付代练费',
    '1': '我要求赔偿保证金',
    '2': '仅要求退款',
}
# 撤销意愿对应的说明后缀（发单者视角）：0/1 带金额，2 为固定文案
_CANCEL_DESIRE_TEXT = {
    '0': '发单者愿意支付代练费{amount}元',
    '1': '发单者要求赔偿保证金{amount}元',
    '2': '仅要求退款（接单者退回全部保证金，发单者退回全部代练费）',
}
# 「处理撤销申请」可执行的动作（页面「撤销详情」的几种方式）
HANDLE_CANCEL_ACTIONS = {
    'agree': '同意撤销',
    'cancel': '取消撤销',
    'arbitration': '申请平台介入',
}

# 发布订单：各游戏的表单声明在 games/ 包（新增游戏看 games/__init__.py 的说明）
# 默认区服直接取「默认游戏」的声明，避免两处硬编码
DEFAULT_ZONE_SERVER_ID = get_profile(DEFAULT_GAME_ID).default_zone_server_id


def supported_game_options():
    """可供发单的游戏下拉选项：[{value: 游戏ID, label: 游戏名}]"""
    return [{'value': profile.game_id, 'label': profile.name} for profile in enabled_games()]


def game_profile(game_id):
    """取某游戏的发布配置（dict 形式，供接口层取默认值）；未支持的游戏回落默认游戏"""
    profile = get_profile(game_id)
    game_extra = next((f.default for f in profile.fields if f.key == 'game_extra'), '')
    return {'name': profile.name,
            'zone_server_id': profile.default_zone_server_id,
            'level_type2': profile.plays[0].level_type2 if profile.plays else '14',
            'game_extra': game_extra}
# 游戏/区服清单进程内缓存（文档下拉与选游戏解析用）
_GAME_ZONE_CACHE = {'ts': 0, 'data': None}
_GAME_ZONE_CACHE_TTL = 3600


def _game_zone_server_list():
    """上游「全部游戏 + 区服/服务器」清单；进程内缓存 1 小时，失败返回旧值或 []"""
    now = time.time()
    if _GAME_ZONE_CACHE['data'] and now - _GAME_ZONE_CACHE['ts'] < _GAME_ZONE_CACHE_TTL:
        return _GAME_ZONE_CACHE['data']
    ok, result = _call('get_game_zone_server_list')
    if ok and isinstance(result, dict) and result.get('code') == 0 and result.get('data'):
        _GAME_ZONE_CACHE['data'] = result['data']
        _GAME_ZONE_CACHE['ts'] = now
    return _GAME_ZONE_CACHE['data'] or []


def game_options():
    """全部游戏下拉选项：[{value: 游戏ID, label: 游戏名}]（供文档渲染）"""
    return [{'value': str(game.get('GameID')), 'label': game.get('GameName') or ''}
            for game in _game_zone_server_list() if game.get('GameID')]


def _canonical_zone(name):
    """大区名归一化：各游戏写法不一致（如 王者荣耀用「苹果WX」，其它游戏用「苹果微信」）"""
    return (name or '').strip().upper().replace('WX', '微信')


def zone_tree():
    """「游戏 → 大区 → 服务器」级联数据（文档在线调试的联动下拉用；大区名已归一化）

    返回：[{game_id, game_name, zones: [{name, servers: [{code, name}]}]}]
    """
    tree = []
    for game in _game_zone_server_list():
        zones = []
        zone_index = {}
        for zone in (game.get('ZoneList') or []):
            name = _canonical_zone(zone.get('ZoneName'))
            if not name:
                continue
            if name not in zone_index:
                zone_index[name] = {'name': name, 'servers': []}
                zones.append(zone_index[name])
            servers = zone_index[name]['servers']
            for server in (zone.get('ServerList') or []):
                code = server.get('Code')
                if code and not any(item['code'] == str(code) for item in servers):
                    servers.append({'code': str(code), 'name': server.get('ServerName') or ''})
        tree.append({'game_id': str(game.get('GameID') or ''),
                     'game_name': game.get('GameName') or '', 'zones': zones})
    return tree


def _resolve_zone_server_id(game_id, zone_server_id, zone_type=''):
    """解析最终 ZoneServerID

    优先级：显式 zone_server_id > (game_id/zone_type 匹配的首个区服) > 默认（王者荣耀·安卓QQ）。
    game_id 为空则遍历全部游戏，取第一个匹配 zone_type 的区服；无法匹配时返回 ''（由上游报错，避免发到错误的区）。
    """
    if zone_server_id:
        return zone_server_id
    # 只选了游戏（没选大区）：直接用该游戏声明里的默认区服
    if not zone_type and is_supported_game(game_id):
        return get_profile(game_id).default_zone_server_id
    want_zone = _canonical_zone(zone_type)
    for game in _game_zone_server_list():
        if game_id and str(game.get('GameID')) != str(game_id):
            continue
        for zone in (game.get('ZoneList') or []):
            if want_zone and _canonical_zone(zone.get('ZoneName')) != want_zone:
                continue
            for server in (zone.get('ServerList') or []):
                if server.get('Code'):
                    return str(server['Code'])
        if game_id:
            break
    # 指定了大区却没匹配到：不静默退回默认，返回空让上游明确报错
    if want_zone:
        return ''
    return DEFAULT_ZONE_SERVER_ID

# 注入爬虫目录到 sys.path（因为 home.py 使用相对 from utils import ...）
_SPIDER_DIR = os.path.join(os.path.dirname(__file__), '..', '..', '..',
                           'SpiderServices', 'DaiLianTong')
_SPIDER_DIR = os.path.normpath(_SPIDER_DIR)
if _SPIDER_DIR not in sys.path:
    sys.path.insert(0, _SPIDER_DIR)

from home import DaiLianTongService


def _call(method_name, **kwargs):
    """通用爬虫调用包装（含 Token 失效自动重登兜底）

    :param method_name: 爬虫方法名
    :param kwargs: 传给爬虫方法的参数
    :return: (True, data) 或 (False, error_msg)
    """
    ok, data = _invoke(method_name, kwargs)

    # Token 失效（上游返回「签名错误」）且本次是带凭据调用 → 用账号密码重登换新 Token，重试一次
    if ok and _is_signature_error(data) and kwargs.get('token'):
        fresh = _relogin()
        if fresh:
            kwargs['token'] = fresh['token']
            if kwargs.get('user_id'):
                kwargs['user_id'] = fresh['user_id']
            ok, data = _invoke(method_name, kwargs)
    return ok, data


def _invoke(method_name, kwargs):
    """真正调用爬虫方法：返回 (True, data) 或 (False, 异常说明)"""
    spider = DaiLianTongService()
    try:
        return True, getattr(spider, method_name)(**kwargs)
    except Exception as e:
        return False, f'{method_name} 调用异常: {e}'


def _is_signature_error(data) -> bool:
    """上游响应是否为「Token 失效」类错误（「签名错误」）"""
    return isinstance(data, dict) and '签名错误' in str(data.get('message') or '')


def _relogin():
    """用托管账号的手机号 + 密码重新登录代练通，刷新凭据里的 token / user_id / uid

    触发时机：调用返回「签名错误」（Token 失效）。重登成功后把新凭据写回账号表
    （状态置为有效），之后所有调用都会取到新 Token —— 无需人工更新。

    依赖账号表里的两项配置：
        · 凭据 JSON 的 `login_id`（登录手机号）
        · 账号表的 `password` 字段（登录密码，AES 加密存储）
    :return: {'user_id', 'token'} 或 None（无法重登）
    """
    from django.utils import timezone

    from API.models.Accounts.account import AccountStatus, PlatformAccount

    account = platform_accounts.get_available_account(PLATFORM)
    if account is None:
        # 账号可能已被标记过期（过期账号不在 available 里），回落到任意带凭据的账号
        account = (PlatformAccount.objects.filter(platform=PLATFORM)
                   .exclude(credential='').order_by('-updated_time').first())
    if account is None:
        return None

    data = _credential_dict(platform_accounts.credential_of(account))
    login_id = str(data.get('login_id') or '').strip()
    password = (account.password or '').strip()
    if not login_id or not password:
        logger.warning('代练通自动重登跳过：账号未配置 login_id（手机号）或 password')
        return None

    ok, res = login(login_id, password, code_type='Password')
    if not ok or not isinstance(res, dict) or res.get('code') != 0:
        logger.warning('代练通自动重登失败: %s', res)
        return None

    info = res.get('data') or {}
    token = str(info.get('Token') or '').strip()
    if not token:
        logger.warning('代练通自动重登失败：响应未含 Token')
        return None

    data.update({'user_id': str(info.get('UserID') or data.get('user_id') or '').strip(),
                 'uid': str(info.get('UID') or data.get('uid') or '').strip(),
                 'token': token})
    account.credential = json.dumps(data, ensure_ascii=False)
    account.status = AccountStatus.VALID
    account.last_login_time = timezone.now()
    account.check_message = 'Token 失效，已自动重登'
    account.save()
    logger.info('代练通已自动重登，Token 已刷新（user_id=%s）', data['user_id'])
    return {'user_id': data['user_id'], 'token': token}


def _credential_dict(credential):
    """解析平台账号「登录凭据」→ dict（约定 JSON）；格式不符返回 {}

    凭据约定：{"user_id": "<代练通用户ID>", "token": "<登录令牌>", "uid": "<USR 开头，发单哈希用>"}
    """
    try:
        data = json.loads(credential or '')
    except (json.JSONDecodeError, TypeError):
        return {}
    return data if isinstance(data, dict) else {}


def _default_credential_dict():
    """取平台托管的默认代练通账号凭据（dict）；没有则 {}

    默认账号在超管控制台 /console/accounts/ 维护（platform=dlt）。
    """
    account = platform_accounts.get_available_account(PLATFORM)
    if account is None:
        return {}
    return _credential_dict(platform_accounts.credential_of(account))


def _resolve_credentials(user_id, token):
    """user_id / token 任一为空时，回落到平台托管的默认代练通账号

    调用方两者都传则原样使用；任一为空才回落；找不到默认账号则保持匿名。
    """
    if user_id and token:
        return user_id, token
    data = _default_credential_dict()
    return (str(data.get('user_id') or '').strip() or user_id,
            str(data.get('token') or '').strip() or token)


def _resolve_user_id(user_id):
    """未传 user_id 时回落到默认账号的用户ID（用于不需要 token 的接口）"""
    if user_id:
        return user_id
    return str(_default_credential_dict().get('user_id') or '').strip() or user_id


def _resolve_uid(uid):
    """未传 uid 时回落到默认账号的 uid（USR 字符串，发单支付密码哈希用）"""
    if uid:
        return uid
    return str(_default_credential_dict().get('uid') or '').strip()


def _resolve_pay_pass(pay_pass):
    """未传支付密码时回落到默认账号凭据里的 pay_pass（全自动接单用）

    凭据约定扩展为：{"user_id": "...", "token": "...", "uid": "USR...", "pay_pass": "..."}
    """
    if pay_pass:
        return pay_pass
    return str(_default_credential_dict().get('pay_pass') or '').strip()


# ---------- 认证 ----------

def send_code(phone, use_type="17"):
    """发送验证码"""
    return _call('send_code', phone=phone, UseType=use_type)


def register(phone, code):
    """注册"""
    return _call('register', phone=phone, code=code)


def login(phone, code, code_type="VerificationCode"):
    """登录"""
    return _call('login', phone=phone, code=code, code_type=code_type)


# ---------- 用户 ----------

def get_user_info(user_id, token):
    """获取用户信息"""
    user_id, token = _resolve_credentials(user_id, token)
    return _call('get_user_info', user_id=user_id, token=token)


def get_balance(user_id='', token=''):
    """代练通账户可用余额（元）= 总资金 SumBal − 冻结资金 FreezeBal

    数据取自 `UserInfoList`（get_user_info）。接单要冻结该单双金，故发单前用它判断能否承接。
    :return: (True, {'available', 'sum', 'freeze'}) 或 (False, 错误说明)
    """
    ok, res = get_user_info(user_id, token)
    if not ok or not isinstance(res, dict) or res.get('code') != 0:
        return False, str(res)
    data = res.get('data') or {}
    try:
        total = float(data.get('SumBal'))
        freeze = float(data.get('FreezeBal'))
    except (TypeError, ValueError):
        return False, '代练通余额字段无法识别'
    return True, {'available': round(total - freeze, 2), 'sum': total, 'freeze': freeze}


def set_contact(contact, user_id, token, set_contact_type="qq"):
    """设置联系方式"""
    user_id, token = _resolve_credentials(user_id, token)
    return _call('set_contact', contact=contact, user_id=user_id,
                 token=token, set_contact_type=set_contact_type)


def set_mysign(mysign, user_id):
    """设置个性签名（无需 token）"""
    user_id = _resolve_user_id(user_id)
    return _call('set_mysign', mysign=mysign, user_id=user_id)


def change_password(old_password, new_password, user_id, login_id, uid, token):
    """修改密码"""
    user_id, token = _resolve_credentials(user_id, token)
    return _call('change_password', old_password=old_password,
                 new_password=new_password, user_id=user_id,
                 login_id=login_id, uid=uid, token=token)


def sign_in(user_id):
    """签到"""
    user_id = _resolve_user_id(user_id)
    return _call('sign_in', user_id=user_id)


def get_real_name_info(user_id):
    """获取实名认证信息"""
    user_id = _resolve_user_id(user_id)
    return _call('get_my_real_name_info', user_id=user_id)


# ---------- 游戏 ----------

def get_games():
    """获取全部游戏（含各自的公开订单数量）"""
    return _call('get_games')


def get_game_orders(game_id, page=1, page_size=20, pg_type=0,
                    order_type='', start_tier='', end_tier='', price_str='',
                    pub_cancel=0, settle_hour=0, filter_type=1,
                    sort_str='', search_str='', user_id=0, token=''):
    """按游戏ID获取该游戏的公开订单列表（分页 + 多条件筛选）"""
    user_id, token = _resolve_credentials(user_id, token)
    return _call('get_game_orders', game_id=game_id, page=page, page_size=page_size,
                 pg_type=pg_type, order_type=order_type, start_tier=start_tier,
                 end_tier=end_tier, price_str=price_str, pub_cancel=pub_cancel,
                 settle_hour=settle_hour, filter_type=filter_type,
                 sort_str=sort_str, search_str=search_str,
                 user_id=user_id, token=token)


# ---------- 搜索 ----------

def search_orders(game_id, search_str='', is_pub=9, pg_type=2, zone_id=0, server_id=0,
                  level_type2='', stier='', etier='', price_str='', pub_cancel=0,
                  settle_hour=0, filter_type=0, sort_str='', focused=-1, order_type=0,
                  pub_recommend=0, score1=0, score2=0, page=1, page_size=20,
                  user_id=0, token=''):
    """按关键词搜索订单（默认对齐官网搜索页，参数可高度自定义）"""
    user_id, token = _resolve_credentials(user_id, token)
    return _call('search_orders', game_id=game_id, search_str=search_str,
                 is_pub=is_pub, pg_type=pg_type, zone_id=zone_id, server_id=server_id,
                 level_type2=level_type2, stier=stier, etier=etier, price_str=price_str,
                 pub_cancel=pub_cancel, settle_hour=settle_hour, filter_type=filter_type,
                 sort_str=sort_str, focused=focused, order_type=order_type,
                 pub_recommend=pub_recommend, score1=score1, score2=score2,
                 page=page, page_size=page_size, user_id=user_id, token=token)


def get_hot_search_words(game_id):
    """获取某游戏的热门搜索词"""
    return _call('get_hot_search_words', game_id=game_id)


# ---------- 发布 ----------

def publish_order(title, price, time_limit, ensure1, ensure2, game_mobile,
                  game_account, game_password, game_author_name, requirements,
                  pay_pass='', uid='', game_id=0, zone_type='', zone_server_id='', level_type2='14',
                  game_extra='', mobile='', qq='', insurance=0,
                  max_claim_amount=20, order_type=0, user_id=0, token=''):
    """发布订单（自定义发布）

    区服定位优先级：zone_server_id（直接指定）→ game_id + zone_type（自动定位）
    → 默认（王者荣耀·安卓QQ）。切游戏一般只需传 game_id（+ 需要时 zone_type）。
    """
    # 未验证完成的游戏直接拒绝，避免用默认游戏的参数把订单发错
    if game_id and not is_supported_game(game_id):
        return False, (f"暂不支持该游戏（game_id={game_id}）；当前支持："
                       f"{'、'.join(profile.name for profile in enabled_games())}")

    user_id, token = _resolve_credentials(user_id, token)
    uid = _resolve_uid(uid)
    # 订单类型 / 附加信息段按游戏取默认（如铭文只属于王者荣耀，三角洲行动留空）
    profile = game_profile(game_id)
    level_type2 = level_type2 or profile['level_type2']
    game_extra = game_extra or profile['game_extra']
    zone_server_id = _resolve_zone_server_id(game_id, zone_server_id, zone_type)
    return _call('publish_order', title=title, price=price, time_limit=time_limit,
                 ensure1=ensure1, ensure2=ensure2, game_mobile=game_mobile,
                 pay_pass=pay_pass, uid=uid, game_account=game_account,
                 game_password=game_password, game_author_name=game_author_name,
                 requirements=requirements, zone_server_id=zone_server_id,
                 level_type2=level_type2, game_extra=game_extra, mobile=mobile, qq=qq,
                 insurance=insurance, max_claim_amount=max_claim_amount,
                 order_type=order_type, user_id=user_id, token=token)


# ---------- 订单 ----------

def receive_order(order_id, pay_pass='', uid='', token='', user_id=''):
    """接收订单（未传支付密码 / uid 时回落到后台默认代练通账号凭据）"""
    user_id, token = _resolve_credentials(user_id, token)
    return _call('receive_order', order_id=order_id, pay_pass=_resolve_pay_pass(pay_pass),
                 uid=_resolve_uid(uid), token=token, user_id=user_id)


def get_order_detail(order_id, user_id='', token='', is_publish='0'):
    """获取订单详情（未传凭据时回落到默认账号）

    视角（IsPublish）实测：
    - '0'：接单方视角，只有该取值才返回号主账号 GameAcc/GamePass/Actor；
    - '1'/'2'：公开视角，账号字段为空，但能读到 Status / CancelStatus（用于「原单是否还能接」）。
    """
    user_id, token = _resolve_credentials(user_id, token)
    return _call('get_order_detail', order_id=order_id, user_id=user_id, token=token,
                 is_publish=is_publish)


# 号主信息字段名（对外返回用中文键，与调用方约定一致）
OWNER_INFO_FIELDS = ('游戏名称', '客户端', '游戏账号', '密码', '角色名', '号主联系方式', '剩余时间')


def get_owner_info(order_id, user_id='', token=''):
    """获取代练通订单的「号主信息」（接单后可见；账号/密码需接单方视角）

    返回 data:
        {游戏名称, 客户端, 游戏账号, 密码, 角色名, 号主联系方式, 剩余时间}

    说明：账号/密码/角色名只有**接单方**才能看到（IsPublish=0），故调用前需先在代练通接单。
    """
    ok, res = get_order_detail(order_id, user_id, token)
    if not ok:
        return False, res
    if not isinstance(res, dict) or res.get('code') != 0:
        return False, (res.get('message') if isinstance(res, dict) else res)
    data = res.get('data') or {}
    return True, {
        '游戏名称': data.get('Game') or '',
        '客户端': data.get('Zone') or '',
        '游戏账号': data.get('GameAcc') or '',
        '密码': data.get('GamePass') or '',
        '角色名': data.get('Actor') or '',
        '号主联系方式': data.get('GameMobile') or '',
        '剩余时间': data.get('LeaveTime') if data.get('LeaveTime') not in (None, '') else data.get('TimeLimit'),
    }


def delete_order(order_id, token, user_id, reason="不用了"):
    """删除订单"""
    user_id, token = _resolve_credentials(user_id, token)
    return _call('delete_order', order_id=order_id, token=token,
                 user_id=user_id, reason=reason)


def apply_cancel_order(order_id, pay_pass, uid, token, user_id,
                       flag=0, desire='2', progress='无进度', comment='',
                       pay_level_bal=0, rep_ensure_bal=0, revoke_price=0, image=''):
    """申请撤销订单（上游 LevelOrderCancel）

    撤销说明 Comment 按页面格式拼装：撤销原因 / 目前进度 / 撤销意愿 / 补充描述 /
    进度赔偿金 等。金额与撤销意愿对应：desire=0 用 pay_level_bal、desire=1 用
    rep_ensure_bal、desire=2 无需金额。image（图片地址）非空时，撤销成功后作为
    「撤销」留言凭证上传（LevelOrderProgressAdd）。
    """
    user_id, token = _resolve_credentials(user_id, token)
    uid = _resolve_uid(uid)
    amount = pay_level_bal if desire == '0' else (rep_ensure_bal if desire == '1' else 0)
    desire_text = _CANCEL_DESIRE_TEXT.get(desire, '').format(amount=amount)
    comment_text = (f"撤销原因: |目前进度:{progress}|撤销意愿:{desire_text}"
                    f"|补充描述:{comment}|进度赔偿金:0|是否支付进度赔偿金:否"
                    f"|识别订单任务:|用户修改后订单任务:|场次胜率:")
    ok, result = _call('apply_cancel_order', order_id=order_id, pay_pass=pay_pass,
                       uid=uid, token=token, user_id=user_id, flag=flag,
                       pay_level_bal=pay_level_bal, rep_ensure_bal=rep_ensure_bal,
                       comment=comment_text, revoke_price=revoke_price)
    if not ok or not image or not isinstance(result, dict) or result.get('code') != 0:
        return ok, result
    return True, _attach_cancel_image(token, user_id, order_id, image, result)


def handle_cancel(order_id, action, pay_pass='', uid='', token='', user_id='',
                  pay_level_bal=0, rep_ensure_bal=0, comment='', image=''):
    """处理撤销申请（接单者/发单者「撤销详情」页的几种方式）

    action:
        agree       —— 同意撤销：上游 LevelOrderCancel(Flag=2)，需 pay_pass/uid
        cancel      —— 取消撤销：上游 LevelOrderCancel(Flag=1)，需 pay_pass/uid
        arbitration —— 申请平台介入：上游 LevelOrderRequestArbitration，无需支付密码

    image（图片地址）非空且操作成功后，作为「撤销」留言凭证上传（LevelOrderProgressAdd）。
    """
    user_id, token = _resolve_credentials(user_id, token)
    if action == 'arbitration':
        return _call('request_arbitration', order_id=order_id, token=token, user_id=user_id)

    flag = 2 if action == 'agree' else 1
    ok, result = _call('apply_cancel_order', order_id=order_id, pay_pass=pay_pass,
                       uid=_resolve_uid(uid), token=token, user_id=user_id, flag=flag,
                       pay_level_bal=pay_level_bal, rep_ensure_bal=rep_ensure_bal,
                       comment=comment, revoke_price=0)
    if not ok or not image or not isinstance(result, dict) or result.get('code') != 0:
        return ok, result
    return True, _attach_cancel_image(token, user_id, order_id, image, result)


def _attach_cancel_image(token, user_id, order_id, image, result):
    """撤销已提交成功后，把凭证图片以「撤销」留言上传；失败不回滚，仅在 message 上提示"""
    iok, ires = _call('upload_image_in_order_comment', token=token, user_id=user_id,
                      image_path=image, order_id=order_id, msg='撤销')
    if not iok or (isinstance(ires, dict) and ires.get('code') != 0):
        warn = ires.get('message') if isinstance(ires, dict) else ires
        result['message'] = f"{result.get('message')}（提示：撤销凭证图片上传失败：{warn}）"
    return result


def get_my_order(token, user_id, publish=1, over_days=-99, status=0, cancel_status=0,
                 game_id=0, search_str="", game_mobile="", with_tg=1,
                 page=1, page_size=20):
    """获取我的订单（我发布的 / 我接的，可多条件筛选）"""
    user_id, token = _resolve_credentials(user_id, token)
    return _call('get_my_order', token=token, user_id=user_id, publish=publish,
                 over_days=over_days, status=status, cancel_status=cancel_status,
                 game_id=game_id, search_str=search_str, game_mobile=game_mobile,
                 with_tg=with_tg, page_index=page, page_size=page_size)


def upload_image_in_comment(token, user_id, image_path, order_id, msg='留言'):
    """在订单留言中上传图片"""
    user_id, token = _resolve_credentials(user_id, token)
    return _call('upload_image_in_order_comment', token=token,
                 user_id=user_id, image_path=image_path, order_id=order_id, msg=msg)


# ---------- 头像 ----------

def upload_avatar(user_id, image_path):
    """上传头像（无需 token）"""
    user_id = _resolve_user_id(user_id)
    return _call('upload_own_avatar', user_id=user_id, image_path=image_path)
