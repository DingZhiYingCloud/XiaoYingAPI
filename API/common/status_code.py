"""
全局状态码定义

编码规则：5位纯数字，首位标识错误类别
  1xxxx — 成功
  2xxxx — 客户端错误（参数、认证、权限）
  3xxxx — 业务逻辑错误
  4xxxx — 第三方/外部服务错误
  5xxxx — 系统内部错误
  9xxxx — 未知错误

使用示例：
    from API.common import StatusCode

    # 判断是否成功
    if StatusCode.is_success(code):
        ...

    # 获取描述
    msg = StatusCode.get_message(10000)
"""

from types import MappingProxyType


class StatusCode:
    """状态码常量与工具方法"""

    # ==================== 1xxxx 成功 ====================
    SUCCESS = 10000

    # ==================== 2xxxx 客户端错误 ====================

    # 参数相关 20001-20009
    PARAM_MISSING = 20001
    PARAM_FORMAT_ERROR = 20002
    PARAM_VALUE_INVALID = 20003

    # 认证相关 20010-20019
    UNAUTHORIZED = 20010
    AUTH_FAILED = 20011
    TOKEN_EXPIRED = 20012

    # 权限相关 20020-20029
    FORBIDDEN = 20020
    ACCOUNT_DISABLED = 20021

    # 资源相关 20030-20039
    NOT_FOUND = 20030
    RESOURCE_ALREADY_EXISTS = 20031

    # 请求相关 20040-20049
    RATE_LIMITED = 20040
    METHOD_NOT_ALLOWED = 20041

    # ==================== 3xxxx 业务逻辑错误 ====================

    # 通用业务 30001-30009
    BUSINESS_RULE_RESTRICTED = 30001
    STATUS_NOT_ALLOWED = 30002
    DATA_CONFLICT = 30003

    # 资源不足 30010-30019
    INSUFFICIENT_BALANCE = 30010
    INSUFFICIENT_STOCK = 30011

    # ==================== 4xxxx 第三方/外部服务错误 ====================

    # 外部API 40001-40009
    EXTERNAL_API_FAILED = 40001
    EXTERNAL_API_TIMEOUT = 40002
    EXTERNAL_API_ABNORMAL = 40003

    # 网络相关 40010-40019
    NETWORK_ERROR = 40010
    DNS_RESOLVE_FAILED = 40011

    # ==================== 5xxxx 系统内部错误 ====================

    # 服务器 50001-50009
    INTERNAL_ERROR = 50001
    SERVICE_UNAVAILABLE = 50002

    # 数据存储 50010-50019
    DATABASE_ERROR = 50010
    CACHE_ERROR = 50011

    # 文件 50020-50029
    FILE_READ_ERROR = 50020
    FILE_WRITE_ERROR = 50021

    # 配置 50030-50039
    CONFIG_ERROR = 50030

    # ==================== 9xxxx 未知错误 ====================
    UNKNOWN_ERROR = 99999

    # ==================== 消息映射 ====================
    # 使用 MappingProxyType 包装，防止外部意外修改，增强稳定性
    _MESSAGES = MappingProxyType({
        SUCCESS: '成功',

        PARAM_MISSING: '参数缺失',
        PARAM_FORMAT_ERROR: '参数格式错误',
        PARAM_VALUE_INVALID: '参数值非法',

        UNAUTHORIZED: '未认证',
        AUTH_FAILED: '认证失败',
        TOKEN_EXPIRED: 'Token已过期',

        FORBIDDEN: '无权限',
        ACCOUNT_DISABLED: '账号已被禁用',

        NOT_FOUND: '资源不存在',
        RESOURCE_ALREADY_EXISTS: '资源已存在',

        RATE_LIMITED: '请求过于频繁',
        METHOD_NOT_ALLOWED: '请求方法不允许',

        BUSINESS_RULE_RESTRICTED: '业务规则限制',
        STATUS_NOT_ALLOWED: '当前状态不允许此操作',
        DATA_CONFLICT: '数据冲突',

        INSUFFICIENT_BALANCE: '余额不足',
        INSUFFICIENT_STOCK: '库存不足',

        EXTERNAL_API_FAILED: '外部API调用失败',
        EXTERNAL_API_TIMEOUT: '外部API调用超时',
        EXTERNAL_API_ABNORMAL: '外部API返回异常',

        NETWORK_ERROR: '网络连接失败',
        DNS_RESOLVE_FAILED: 'DNS解析失败',

        INTERNAL_ERROR: '服务器内部错误',
        SERVICE_UNAVAILABLE: '服务暂不可用',

        DATABASE_ERROR: '数据库错误',
        CACHE_ERROR: '缓存错误',

        FILE_READ_ERROR: '文件读取失败',
        FILE_WRITE_ERROR: '文件写入失败',

        CONFIG_ERROR: '配置错误',

        UNKNOWN_ERROR: '未知错误',
    })

    # ==================== 类别映射 ====================
    # 提取为类常量，避免每次调用 category() 时重复创建 dict，提升性能
    _CATEGORIES = MappingProxyType({
        1: '成功',
        2: '客户端错误',
        3: '业务逻辑错误',
        4: '第三方/外部服务错误',
        5: '系统内部错误',
        9: '未知错误',
    })

    @classmethod
    def get_message(cls, code: int) -> str:
        """根据状态码获取描述信息"""
        return cls._MESSAGES.get(code, '未知状态码')

    @classmethod
    def is_success(cls, code: int) -> bool:
        """判断状态码是否表示成功"""
        return code == cls.SUCCESS

    @classmethod
    def category(cls, code: int) -> str:
        """获取状态码所属类别"""
        first_digit = code // 10000
        return cls._CATEGORIES.get(first_digit, '未分类')