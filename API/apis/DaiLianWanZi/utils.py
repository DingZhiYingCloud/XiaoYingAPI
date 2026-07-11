"""代练丸子 DaiLianWanZi 爬虫调用封装

本模块通过动态 sys.path 注入 + importlib 加载爬虫类，
避免模块名冲突（与 DaiLianTong 都叫 home.py）。
"""
import sys
import os
import importlib

# 爬虫目录绝对路径
_SPIDER_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), '..', '..', '..',
                 'SpiderServices', 'DaiLianWanZi')
)

_UNIQUE_MODULE = "dlwz_spider_home"


def _import_spider():
    """动态导入爬虫模块，返回 DaiLianWanZiService 类"""
    # 清理可能冲突的已有模块缓存
    sys.modules.pop(_UNIQUE_MODULE, None)
    sys.modules.pop("home", None)

    # 将爬虫目录加入 sys.path
    if _SPIDER_DIR not in sys.path:
        sys.path.insert(0, _SPIDER_DIR)

    # 动态加载 home.py 并赋予唯一模块名
    spec = importlib.util.spec_from_file_location(
        _UNIQUE_MODULE,
        os.path.join(_SPIDER_DIR, "home.py"),
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[_UNIQUE_MODULE] = module

    # 设置 __package__ 使 home.py 中的相对导入 from .utils import ... 正常工作
    # Python 会将 .utils 解析为 dlwz_spider_home.utils
    module.__package__ = _UNIQUE_MODULE

    # 预加载 utils 子模块，使其可通过 dlwz_spider_home.utils 找到
    utils_path = os.path.join(_SPIDER_DIR, "utils.py")
    utils_spec = importlib.util.spec_from_file_location(
        f"{_UNIQUE_MODULE}.utils",
        utils_path,
    )
    if utils_spec:
        utils_module = importlib.util.module_from_spec(utils_spec)
        sys.modules[f"{_UNIQUE_MODULE}.utils"] = utils_module
        utils_module.__package__ = _UNIQUE_MODULE
        utils_spec.loader.exec_module(utils_module)

    module.__path__ = [_SPIDER_DIR]
    spec.loader.exec_module(module)

    return module.DaiLianWanZiService


_dlwz_service_class = _import_spider()


def _call(method_name, **kwargs):
    """通用爬虫调用包装

    :param method_name: 爬虫方法名
    :param kwargs: 传给爬虫方法的参数
    :return: (True, data_dict) 或 (False, error_msg)
    """
    spider = _dlwz_service_class()
    try:
        result = getattr(spider, method_name)(**kwargs)
        return True, result
    except Exception as e:
        return False, f'{method_name} 调用异常: {e}'


# ---------- 认证 ----------

def send_code(phone):
    """发送短信验证码"""
    return _call('send_code', phone=phone)


def login(phone, code, code_type="VerificationCode"):
    """登录"""
    return _call('login', phone=phone, code=code, code_type=code_type)


# ---------- 用户 ----------

def get_user_info(authorization):
    """获取用户信息"""
    return _call('get_user_info', authorization=authorization)


def upload_own_avatar(image, authorization):
    """上传头像"""
    return _call('upload_own_avatar', image=image, authorization=authorization)


def set_mysign(authorization, username, **kwargs):
    """设置个性信息（签名/QQ号等）"""
    return _call('set_mysign', authorization=authorization, username=username, **kwargs)


def get_real_name_info(authorization):
    """获取实名认证信息"""
    return _call('get_my_real_name_info', authorization=authorization)


def sign_in(authorization):
    """签到"""
    return _call('sign_in', authorization=authorization)


# ---------- 订单 ----------

def get_public_order_list(authorization, price_gt=10, price_lt=50,
                          page_no=1, page_size=30, game_id=1):
    """获取公共订单列表"""
    return _call('get_public_order_list', authorization=authorization,
                 price_gt=price_gt, price_lt=price_lt,
                 page_no=page_no, page_size=page_size, game_id=game_id)


def search_order(authorization, keyword, page_no=1, page_size=10):
    """搜索订单"""
    return _call('search_order', authorization=authorization, keyword=keyword,
                 page_no=page_no, page_size=page_size)


def get_order_detail(authorization, order_id):
    """获取订单详情"""
    return _call('get_order_detail', authorization=authorization, order_id=order_id)


def publish_order(authorization, title, amount, hour,
                  security_deposit, efficiency_deposit,
                  player_phone="3837190115",
                  contact_phone="3837190115",
                  game_region_name="安卓QQ",
                  hero_number="",
                  requirement="代练要求",
                  explain_text="代练说明",
                  game_account="扫码上号",
                  game_password="扫码上号",
                  contact_qq="扫码上号",
                  game_role="扫码上号",
                  game_id=1,
                  game_server_id=122,
                  game_region_id=2,
                  game_icon="https://files.llwanzi.com/zympYphpKVhaHN1685523686230531.png",
                  game_name="王者",
                  game_leveling_type_name="排位"):
    """发布订单"""
    return _call('publish_order', authorization=authorization, title=title,
                 amount=amount, hour=hour,
                 securityDeposit=security_deposit,
                 efficiencyDeposit=efficiency_deposit,
                 playerPhone=player_phone, contactPhone=contact_phone,
                 gameRegionName=game_region_name, heroNumber=hero_number,
                 requirement=requirement, explain=explain_text,
                 gameAccount=game_account, gamePassword=game_password,
                 contactQq=contact_qq, gameRole=game_role,
                 gameId=game_id, gameServerId=game_server_id,
                 gameRegionId=game_region_id, gameIcon=game_icon,
                 gameName=game_name,
                 gameLevelingTypeName=game_leveling_type_name)


def cancel_order(order_id, authorization=None):
    """取消订单"""
    return _call('cancel_order', orderId=order_id, authorization=authorization)


# ---------- 财务 ----------

def get_my_balance(authorization=None):
    """获取余额"""
    return _call('get_my_balance', authorization=authorization)
