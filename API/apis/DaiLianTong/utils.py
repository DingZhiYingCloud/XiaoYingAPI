"""代练通 DaiLianTong 爬虫调用封装

本模块在 sys.path 中注入爬虫目录后，导入原始爬虫类进行包装:
- 每次调用创建新的爬虫实例（无状态、线程安全）
- 统一捕获异常，返回 (success, data_or_msg) 二元组
"""
import sys
import os

# 注入爬虫目录到 sys.path（因为 home.py 使用相对 from utils import ...）
_SPIDER_DIR = os.path.join(os.path.dirname(__file__), '..', '..', '..',
                           'SpiderServices', 'DaiLianTong')
_SPIDER_DIR = os.path.normpath(_SPIDER_DIR)
if _SPIDER_DIR not in sys.path:
    sys.path.insert(0, _SPIDER_DIR)

from home import DaiLianTongService


def _call(method_name, **kwargs):
    """通用爬虫调用包装

    :param method_name: 爬虫方法名
    :param kwargs: 传给爬虫方法的参数
    :return: (True, data) 或 (False, error_msg)
    """
    spider = DaiLianTongService()
    try:
        result = getattr(spider, method_name)(**kwargs)
        return True, result
    except Exception as e:
        return False, f'{method_name} 调用异常: {e}'


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
    return _call('get_user_info', user_id=user_id, token=token)


def set_contact(contact, user_id, token, set_contact_type="qq"):
    """设置联系方式"""
    return _call('set_contact', contact=contact, user_id=user_id,
                 token=token, set_contact_type=set_contact_type)


def set_mysign(mysign, user_id):
    """设置个性签名（无需 token）"""
    return _call('set_mysign', mysign=mysign, user_id=user_id)


def change_password(old_password, new_password, user_id, login_id, uid, token):
    """修改密码"""
    return _call('change_password', old_password=old_password,
                 new_password=new_password, user_id=user_id,
                 login_id=login_id, uid=uid, token=token)


def sign_in(user_id):
    """签到"""
    return _call('sign_in', user_id=user_id)


def get_real_name_info(user_id):
    """获取实名认证信息"""
    return _call('get_my_real_name_info', user_id=user_id)


# ---------- 订单 ----------

def get_public_order_list(user_id, token, page_index=1, page_size=20,
                          game_id=107, price_str="10_20", is_pub=1,
                          search_str="", pg_type=0, filter_sensitive=False):
    """获取公共订单列表"""
    return _call('get_public_order_list', user_id=user_id, token=token,
                 page_index=page_index, page_size=page_size, game_id=game_id,
                 price_str=price_str, is_pub=is_pub, search_str=search_str,
                 pg_type=pg_type, filter_sensitive=filter_sensitive)


def get_order_detail(user_id, token, order_id):
    """获取订单详情"""
    return _call('get_order_detail', user_id=user_id, token=token,
                 order_id=order_id)


def receive_order(order_id, pay_pass, uid, token, user_id):
    """接收订单"""
    return _call('receive_order', order_id=order_id, pay_pass=pay_pass,
                 uid=uid, token=token, user_id=user_id)


def publish_order(title, uid, price, time_limit, token, user_id,
                  ensure1, ensure2, game_mobile, pay_pass,
                  game_account, game_password, game_author_name,
                  hero_count=10,
                  requirements="1、未经同意请勿动用账号点券、物品，不要联系或回复好友信息\n\n2、切勿使用外挂，不允许打广告、挂机、恶意骂人等恶意行为",
                  zone_serverID='107103017095500'):
    """发布订单"""
    return _call('publish_order', title=title, uid=uid, price=price,
                 time_limit=time_limit, token=token, user_id=user_id,
                 ensure1=ensure1, ensure2=ensure2, game_mobile=game_mobile,
                 pay_pass=pay_pass, game_account=game_account,
                 game_password=game_password, game_author_name=game_author_name,
                 hero_count=hero_count, requirements=requirements,
                 zone_serverID=zone_serverID)


def delete_order(order_id, token, user_id, reason="不用了"):
    """删除订单"""
    return _call('delete_order', order_id=order_id, token=token,
                 user_id=user_id, reason=reason)


def get_my_order(token, user_id, page_index="1", page_size="20",
                 over_days="-99", search_str=""):
    """获取我的订单"""
    return _call('get_my_order', token=token, user_id=user_id,
                 page_index=page_index, page_size=page_size,
                 over_days=over_days, search_str=search_str)


def upload_image_in_comment(token, user_id, image_path, order_id):
    """在订单留言中上传图片"""
    return _call('upload_image_in_order_comment', token=token,
                 user_id=user_id, image_path=image_path, order_id=order_id)


# ---------- 头像 ----------

def upload_avatar(user_id, image_path):
    """上传头像（无需 token）"""
    return _call('upload_own_avatar', user_id=user_id, image_path=image_path)
