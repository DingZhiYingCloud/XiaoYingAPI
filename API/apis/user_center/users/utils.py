"""用户中心 - 用户业务逻辑

功能：
    register_user   - 注册（系统分配纯数字账号 6-12 位，全局唯一）
    login_user      - 登录（账号+密码，签发绑定项目的 Token）
    logout_user     - 退出（删除 Token）
    get_user_info   - 获取用户信息（校验 Token）
    verify_token    - 验证 Token（供子项目调用，返回用户身份）

所有函数返回 (success, data_or_msg) 二元组，异常内部捕获，调用方无需 try/except。
"""
import random
import secrets
from datetime import timedelta

from django.contrib.auth.hashers import check_password, make_password
from django.db import IntegrityError
from django.utils import timezone

from API.models import User, UserApp, UserToken

# 系统分配账号长度范围
ACCOUNT_MIN_LEN = 6
ACCOUNT_MAX_LEN = 12

# 密码长度约束
PASSWORD_MIN_LEN = 6
PASSWORD_MAX_LEN = 64

# 用户名长度约束
USERNAME_MAX_LEN = 50

# 生成账号最大重试次数（避免极端并发下唯一冲突死循环）
ACCOUNT_RETRY_TIMES = 20


def generate_account() -> str:
    """随机生成全局唯一的纯数字账号（6-12 位，首位非 0）"""
    for _ in range(ACCOUNT_RETRY_TIMES):
        length = random.randint(ACCOUNT_MIN_LEN, ACCOUNT_MAX_LEN)
        if length == 1:
            first = random.choice('123456789')
        else:
            first = random.choice('123456789')
            rest = ''.join(random.choice('0123456789') for _ in range(length - 1))
            first += rest
        if not User.objects.filter(account=first).exists():
            return first
    return None


def _parse_credentials(username, password):
    """校验并清洗注册/登录的账号密码参数，返回 (ok, username, password, err_msg)"""
    username = (username or '').strip()
    password = (password or '').strip()
    if not username:
        return False, None, None, '参数缺失: username(用户名)'
    if len(username) > USERNAME_MAX_LEN:
        return False, None, None, f'参数格式错误: username 长度不能超过 {USERNAME_MAX_LEN} 字符'
    if not password:
        return False, None, None, '参数缺失: password(密码)'
    if not (PASSWORD_MIN_LEN <= len(password) <= PASSWORD_MAX_LEN):
        return False, None, None, f'参数格式错误: password 长度必须在 {PASSWORD_MIN_LEN}-{PASSWORD_MAX_LEN} 字符之间'
    return True, username, password, None


def register_user(app, username, password):
    """用户注册：用户名 + 密码，系统分配唯一账号

    :return: (True, {user_id, account, username}) 或 (False, err_msg)
    """
    ok, username, password, err = _parse_credentials(username, password)
    if not ok:
        return False, err

    # 极端并发下账号唯一冲突时最多重试 3 次
    for _ in range(3):
        account = generate_account()
        if not account:
            return False, '系统繁忙: 账号生成失败，请重试'

        try:
            user = User.objects.create(
                account=account,
                username=username,
                password=make_password(password),
                status=True,
            )
            return True, {
                'user_id': str(user.id),
                'account': user.account,
                'username': user.username,
            }
        except IntegrityError:
            continue  # 账号唯一冲突，重新生成重试
        except Exception as e:
            return False, f'注册失败: {e}'

    return False, '注册失败: 账号唯一冲突，请重试'


def login_user(app, account, password):
    """用户登录：账号 + 密码，签发绑定该项目的 Token

    :return: (True, {user_id, account, username, token, expire_time}) 或 (False, err_msg)
    """
    account = (account or '').strip()
    password = (password or '').strip()
    if not account:
        return False, '参数缺失: account(账号)'
    if not password:
        return False, '参数缺失: password(密码)'

    try:
        user = User.objects.get(account=account)
    except User.DoesNotExist:
        # 不暴露账号是否存在，统一提示
        return False, '账号或密码错误'
    except Exception as e:
        return False, f'登录失败: {e}'

    if not user.status:
        return False, '账号已被封禁'
    if not check_password(password, user.password):
        return False, '账号或密码错误'

    # 签发绑定项目的 Token
    token = secrets.token_hex(32)
    expire_time = timezone.now() + timedelta(days=app.token_expire_days)
    try:
        UserToken.objects.create(
            user=user,
            app=app,
            token=token,
            expire_time=expire_time,
        )
    except Exception as e:
        return False, f'登录失败: {e}'

    return True, {
        'user_id': str(user.id),
        'account': user.account,
        'username': user.username,
        'token': token,
        'expire_time': expire_time.strftime('%Y-%m-%d %H:%M:%S'),
    }


def logout_user(app, token):
    """用户退出：删除指定 Token（仅删除当前项目下匹配的 Token）

    :return: (True, None) 或 (False, err_msg)
    """
    token = (token or '').strip()
    if not token:
        return False, '参数缺失: token'

    try:
        deleted, _ = UserToken.objects.filter(app=app, token=token).delete()
        if deleted == 0:
            return False, 'Token 不存在或不属于当前项目'
        return True, None
    except Exception as e:
        return False, f'退出失败: {e}'


def _get_token_record(app, token):
    """查询并校验当前项目下的 Token 记录，返回 (ok, user_or_err)"""
    token = (token or '').strip()
    if not token:
        return False, '参数缺失: token'

    try:
        record = UserToken.objects.select_related('user', 'app').get(app=app, token=token)
    except UserToken.DoesNotExist:
        return False, 'Token 无效: 不存在或不属于当前项目'
    except Exception as e:
        return False, f'查询失败: {e}'

    if not record.is_valid:
        return False, 'Token 已失效: 已过期 / 用户封禁 / 项目停用'
    return True, record


def get_user_info(app, token):
    """获取用户信息（校验 Token）

    :return: (True, {user_id, account, username, expire_time}) 或 (False, err_msg)
    """
    ok, result = _get_token_record(app, token)
    if not ok:
        return False, result
    record = result
    return True, {
        'user_id': str(record.user.id),
        'account': record.user.account,
        'username': record.user.username,
        'expire_time': record.expire_time.strftime('%Y-%m-%d %H:%M:%S'),
    }


def verify_token(app, token):
    """验证 Token（供子项目调用，校验身份并返回用户信息）

    :return: (True, {valid, user_id, account, username}) 或 (False, err_msg)
    """
    ok, result = _get_token_record(app, token)
    if not ok:
        return False, result
    record = result
    # 更新最后活跃时间
    try:
        UserToken.objects.filter(id=record.id).update(last_active_time=timezone.now())
    except Exception:
        pass
    return True, {
        'valid': True,
        'user_id': str(record.user.id),
        'account': record.user.account,
        'username': record.user.username,
    }
