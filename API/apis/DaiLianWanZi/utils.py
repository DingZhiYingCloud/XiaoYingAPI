"""代练丸子 DaiLianWanZi 爬虫调用封装

本模块通过动态 sys.path 注入 + importlib 加载爬虫类，
避免模块名冲突（与 DaiLianTong 都叫 home.py）。

认证口径（与代练通一致）：调用方未传 authorization 时，自动回落到后台
「账号管理」(/console/accounts/) 里代练丸子（platform=dlwz）的托管账号；
托管的「登录凭据」按爬虫层的 parse_credential 动态解析出 accessToken。
"""
import sys
import os
import importlib

from API.common import platform_accounts
from API.apis.DaiLianWanZi.games import get_preset

# 爬虫目录绝对路径
_SPIDER_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), '..', '..', '..',
                 'SpiderServices', 'DaiLianWanZi')
)

_UNIQUE_MODULE = "dlwz_spider_home"


def _load_spider_module(fname):
    """把 SpiderServices/DaiLianWanZi/<fname>.py 以唯一模块名动态加载，返回模块对象

    爬虫的 home.py（打手版）/ business.py（商家版）都用相对导入（from .utils import ...），
    故统一以 _UNIQUE_MODULE 作包名，并把 utils 预加载进 sys.modules，使 .utils 能正确解析。
    """
    module_name = _UNIQUE_MODULE if fname == "home" else f"{_UNIQUE_MODULE}.{fname}"
    spec = importlib.util.spec_from_file_location(
        module_name, os.path.join(_SPIDER_DIR, f"{fname}.py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    module.__package__ = _UNIQUE_MODULE
    module.__path__ = [_SPIDER_DIR]
    spec.loader.exec_module(module)
    return module


def _import_spiders():
    """动态导入打手版（home）与商家版（business）两个爬虫模块

    注意通用模块名 `home` 的污染：本服务的 home.py 内部用 `from home import DdddocrRecognizer`
    导入同项目的验证码爬虫，加载后 `sys.modules['home']` 会被换成验证码模块；若不还原，
    其它同样写 `from home import ...` 的爬虫（如代练通 `from home import DaiLianTongService`）
    在本服务之后加载时会导入失败。故这里**先暂存、加载完再还原**（与 DdddocrRecognizer
    加载器暂存/还原 `utils` 是同一手法），使本服务加载前后对外的 `sys.modules['home']` 保持一致。

    :return: (utils 模块, home 模块, business 模块)
    """
    # 暂存外部已有的通用名 home（随后 pop 掉，强制 home.py 内的 `from home import`
    # 按 sys.path 重新解析到验证码爬虫，而非误用别处缓存的 home）
    original_home = sys.modules.pop("home", None)

    # 清理本服务自己的模块缓存
    for name in (_UNIQUE_MODULE, f"{_UNIQUE_MODULE}.utils", f"{_UNIQUE_MODULE}.business"):
        sys.modules.pop(name, None)

    # 将爬虫目录加入 sys.path
    if _SPIDER_DIR not in sys.path:
        sys.path.insert(0, _SPIDER_DIR)

    try:
        # 预加载 utils 子模块，使其可通过 dlwz_spider_home.utils 找到
        utils_spec = importlib.util.spec_from_file_location(
            f"{_UNIQUE_MODULE}.utils", os.path.join(_SPIDER_DIR, "utils.py"))
        utils_module = importlib.util.module_from_spec(utils_spec)
        sys.modules[f"{_UNIQUE_MODULE}.utils"] = utils_module
        utils_module.__package__ = _UNIQUE_MODULE
        utils_spec.loader.exec_module(utils_module)

        home_module = _load_spider_module("home")
        business_module = _load_spider_module("business")
    finally:
        # 还原：本服务加载期间不得把通用名 home 留在验证码爬虫上
        if original_home is not None:
            sys.modules["home"] = original_home
        else:
            sys.modules.pop("home", None)

    return (utils_module, home_module, business_module)


# 爬虫 utils 子模块（与爬虫类同源加载），复用其凭据解析函数，避免两处实现解析口径
_spider_utils, _spider_home, _spider_business = _import_spiders()
# 打手版（home）/ 商家版（business）爬虫类
_dlwz_service_class = _spider_home.DaiLianWanZiService
_dlwz_business_class = _spider_business.DaiLianWanZiBusinessService

# 平台账号标识：默认代练丸子账号在超管控制台 /console/accounts/ 维护（platform=dlwz）
PLATFORM = 'dlwz'


def _default_authorization():
    """取平台托管的默认代练丸子账号令牌；没有则空串

    凭据为登录接口返回的 JSON，动态解析出 accessToken（见爬虫 utils.parse_credential）。
    """
    account = platform_accounts.get_available_account(PLATFORM)
    if account is None:
        return ''
    return _spider_utils.credential_authorization(platform_accounts.credential_of(account))


def _resolve_authorization(authorization):
    """调用方未传 authorization 时，回落到后台托管的默认代练丸子账号"""
    return authorization or _default_authorization()


def _call_with(service_class, method_name, **kwargs):
    """通用爬虫调用包装

    :param service_class: 爬虫类（打手版 / 商家版）
    :param method_name: 爬虫方法名
    :param kwargs: 传给爬虫方法的参数
    :return: (True, data_dict) 或 (False, error_msg)
    """
    spider = service_class()
    try:
        result = getattr(spider, method_name)(**kwargs)
        return True, result
    except Exception as e:
        return False, f'{method_name} 调用异常: {e}'


def _call(method_name, **kwargs):
    """调用打手版（home）爬虫"""
    return _call_with(_dlwz_service_class, method_name, **kwargs)


def _call_business(method_name, **kwargs):
    """调用商家版（business）爬虫"""
    return _call_with(_dlwz_business_class, method_name, **kwargs)


# ---------- 认证 ----------

def send_code(phone):
    """发送短信验证码"""
    return _call('send_code', phone=phone)


def login(phone, code, code_type="VerificationCode"):
    """登录"""
    return _call('login', phone=phone, code=code, code_type=code_type)


# ---------- 用户 ----------

def get_user_info(authorization=''):
    """获取用户信息（未传 authorization 时用后台默认账号）"""
    return _call('get_user_info', authorization=_resolve_authorization(authorization))


def upload_own_avatar(image, authorization=''):
    """上传头像（未传 authorization 时用后台默认账号）"""
    return _call('upload_own_avatar', image=image,
                 authorization=_resolve_authorization(authorization))


def set_mysign(authorization, username, **kwargs):
    """设置个性信息（签名/QQ号等；未传 authorization 时用后台默认账号）"""
    return _call('set_mysign', authorization=_resolve_authorization(authorization),
                 username=username, **kwargs)


def get_real_name_info(authorization=''):
    """获取实名认证信息（未传 authorization 时用后台默认账号）"""
    return _call('get_my_real_name_info',
                 authorization=_resolve_authorization(authorization))


def sign_in(authorization=''):
    """签到（未传 authorization 时用后台默认账号）"""
    return _call('sign_in', authorization=_resolve_authorization(authorization))


# ---------- 财务 ----------

def get_my_balance(authorization=None):
    """获取余额（未传 authorization 时用后台默认账号）"""
    return _call('get_my_balance', authorization=_resolve_authorization(authorization))


def get_balance(authorization=None):
    """代练丸子可用余额（元），取自「我的余额」的 balance 字段

    发单即从商家余额扣款（双金由接单方冻结），故发单前用它判断能否发布。
    :return: (True, {'available', 'frozen'}) 或 (False, 错误说明)
    """
    ok, res = get_my_balance(authorization)
    if not ok or not isinstance(res, dict) or res.get('code') != 0:
        return False, str(res)
    inner = ((res.get('data') or {}).get('data')) or {}
    try:
        available = float(inner.get('balance'))
        frozen = float(inner.get('frozen') or 0)
    except (TypeError, ValueError):
        return False, '丸子余额字段无法识别'
    return True, {'available': round(available, 2), 'frozen': frozen}


# ---------- 商家版 · 我的订单 ----------

def get_order_tabs(authorization=''):
    """获取商家版订单分类（未传 authorization 时用后台默认账号）"""
    return _call_business('get_order_tabs', authorization=_resolve_authorization(authorization))


def get_my_orders(authorization='', table_type=0, keyword='', page=1, page_size=20):
    """获取商家版我的订单（未传 authorization 时用后台默认账号）"""
    return _call_business('get_my_orders', authorization=_resolve_authorization(authorization),
                          table_type=table_type, keyword=keyword, page=page, page_size=page_size)


def cancel_order(trade_no, authorization=''):
    """取消商家版已发布的订单（未传 authorization 时用后台默认账号）"""
    return _call_business('cancel_order', authorization=_resolve_authorization(authorization),
                          trade_no=trade_no)


# ---------- 商家版 · 接单大厅 ----------

def search_orders(keyword='', game_id='', page=1, page_size=20, authorization=''):
    """搜索接单大厅订单（未传 authorization 时用后台默认账号）"""
    return _call_business('search_orders', authorization=_resolve_authorization(authorization),
                          keyword=keyword, game_id=game_id, page=page, page_size=page_size)


def get_hall_order(trade_no, authorization=''):
    """大厅订单详情（接单前查看；未传 authorization 时用后台默认账号）"""
    return _call_business('get_hall_order', authorization=_resolve_authorization(authorization),
                          trade_no=trade_no)


def get_search_words(authorization=''):
    """大厅热搜词（未传 authorization 时用后台默认账号）"""
    return _call_business('get_search_words', authorization=_resolve_authorization(authorization))


def take_password_check(trade_no, take_password, authorization=''):
    """接单密码校验（未传 authorization 时用后台默认账号）"""
    return _call_business('take_password_check',
                          authorization=_resolve_authorization(authorization),
                          trade_no=trade_no, take_password=take_password)


def take_order(trade_no, pay_password, take_password='', authorization=''):
    """接单（会真实接手并从接单方冻结双金；未传 authorization 时用后台默认账号）"""
    return _call_business('take_order', authorization=_resolve_authorization(authorization),
                          trade_no=trade_no, take_password=take_password,
                          pay_password=pay_password)


# ---------- 商家版 · 撤销 / 仲裁 ----------

def apply_revocation(trade_no, initiator, reason, image_urls, deposit=0, pay_amount=0,
                     if_auto_arbitrate=0, authorization=''):
    """申请撤销（image_urls 为凭证图片URL列表；未传 authorization 时用后台默认账号）"""
    return _call_business('apply_revocation', authorization=_resolve_authorization(authorization),
                          trade_no=trade_no, initiator=initiator, reason=reason,
                          image_urls=image_urls, deposit=deposit, pay_amount=pay_amount,
                          if_auto_arbitrate=if_auto_arbitrate)


def agree_revocation(trade_no, pay_password='', authorization=''):
    """同意撤销（pay_password 发单方必填；未传 authorization 时用后台默认账号）"""
    return _call_business('agree_revocation', authorization=_resolve_authorization(authorization),
                          trade_no=trade_no, pay_password=pay_password)


def cancel_revocation(trade_no, authorization=''):
    """取消撤销（未传 authorization 时用后台默认账号）"""
    return _call_business('cancel_revocation', authorization=_resolve_authorization(authorization),
                          trade_no=trade_no)


def apply_arbitration(trade_no, initiator, reason, image_urls, amount=0, deposit=0, opera_type=0,
                      authorization=''):
    """申请仲裁（image_urls 为举证图片URL列表；未传 authorization 时用后台默认账号）"""
    return _call_business('apply_arbitration', authorization=_resolve_authorization(authorization),
                          trade_no=trade_no, initiator=initiator, reason=reason,
                          image_urls=image_urls, amount=amount, deposit=deposit,
                          opera_type=opera_type)


# ---------- 商家版 · 发单 ----------

def get_games(authorization=''):
    """获取全部游戏（仅 game_id + game_name；未传 authorization 时用后台默认账号）"""
    return _call_business('get_games', authorization=_resolve_authorization(authorization))


def get_order_options(game_id, authorization='', leveling_type_id=''):
    """发单可选项：大区 + 代练类型 +（指定代练类型时）子类型字段"""
    return _call_business('get_order_options', authorization=_resolve_authorization(authorization),
                          game_id=game_id, leveling_type_id=leveling_type_id)


def publish_order(game_id, tasks=None, amount=None, hour=None,
                  security_deposit=None, efficiency_deposit=None,
                  region_name='', leveling_type_name='',
                  login_method=None, game_account='', game_password='', game_role='',
                  player_phone='', contact_phone='', contact_qq='',
                  title='', subtitle='', explain='', requirement='',
                  take_password='', hero_name='', price_index=None, authorization='',
                  take_level=None, perf_rate=0, take_count=0, use_tier=True):
    """发布订单（商家版）

    未传的字段用该游戏的预设默认值（见 games.py）；未传 authorization 时用后台默认账号。
    """
    preset = get_preset(game_id)
    return _call_business(
        'publish_order',
        authorization=_resolve_authorization(authorization),
        game_id=preset.game_id,
        tasks=tasks if tasks is not None else preset.tasks,
        amount=preset.amount if amount is None else amount,
        hour=preset.hour if hour is None else hour,
        security_deposit=preset.security_deposit if security_deposit is None else security_deposit,
        efficiency_deposit=preset.efficiency_deposit if efficiency_deposit is None else efficiency_deposit,
        region_name=region_name or preset.region_name,
        leveling_type_name=leveling_type_name or preset.leveling_type_name,
        login_method=preset.login_method if login_method is None else login_method,
        game_account=game_account or preset.game_account,
        game_password=game_password or preset.game_password,
        game_role=game_role or preset.game_role,
        player_phone=player_phone or preset.player_phone,
        contact_phone=contact_phone or preset.contact_phone,
        contact_qq=contact_qq or preset.contact_qq,
        title=title, subtitle=subtitle, explain=explain, requirement=requirement,
        take_password=take_password, hero_name=hero_name,
        title_suffix=preset.title_suffix,
        price_index=preset.price_index if price_index is None else price_index,
        take_level=take_level, perf_rate=perf_rate, take_count=take_count,
        use_tier=use_tier,
    )
