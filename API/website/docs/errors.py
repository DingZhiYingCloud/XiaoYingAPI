"""对外错误码总表（/docs/errors/ 页面的内容源）

**只收录「接口真的会返回」的错误码**：status_code.py 里定义了一些当前
没有任何地方引用的常量（如 INSUFFICIENT_BALANCE / DATABASE_ERROR），
列出来等于承诺不存在的报错，反而误导调用方，故不收录。

码值与文案本身取自 StatusCode（单一数据源），这里只补充两样文档信息：
触发场景（什么时候会遇到）与处理建议（遇到后怎么办）。
新增/启用业务码时，把它补进 _ENTRIES 即可出现在页面上。
"""
from collections import OrderedDict

from django.utils.translation import gettext as _

from API.common.status_code import StatusCode

# (状态码, 触发场景, 处理建议)——顺序即页面展示顺序（同类别内）
_ENTRIES = (
    (StatusCode.PARAM_MISSING,
     '必填参数没有传。',
     '对照该接口「请求参数」表里标为必填的字段补齐后重试。'),
    (StatusCode.PARAM_FORMAT_ERROR,
     '参数格式不对，比如该传数字却传了文字、JSON 体无法解析。',
     '检查参数取值格式与请求体编码，并确认 Content-Type 与实际内容一致（JSON 用 application/json）。'),
    (StatusCode.PARAM_VALUE_INVALID,
     '参数值本身不合法，比如超出取值范围、传入的 ID 不存在。',
     '核对该参数文档里的取值说明后重新提交。'),

    (StatusCode.UNAUTHORIZED,
     '请求没有携带认证信息。',
     '按「签名说明」在请求头带上 APPID、时间戳与签名后重试。'),
    (StatusCode.AUTH_FAILED,
     '签名校验不通过：密钥错误、参数被改动，或时间戳已过期。',
     '用 APPSECRET 重新生成签名，确认时间戳在有效期内且参与签名的是原样参数。'),
    (StatusCode.FORBIDDEN,
     '身份合法但无权访问：项目未开通该服务，或账号被策略限制。',
     '确认项目已开通对应服务；仍有问题请联系管理员。'),

    (StatusCode.NOT_FOUND,
     '请求的路径不存在，或引用的资源不存在。',
     '核对请求 URL 与资源 ID 是否正确。'),
    (StatusCode.RATE_LIMITED,
     '短时间请求过于频繁（例如登录连续失败被临时锁定）。',
     '降低请求频率、稍后重试。'),
    (StatusCode.METHOD_NOT_ALLOWED,
     '使用了该接口不支持的 HTTP 方法。',
     '按文档标注的方法（GET / POST 等）发起请求。'),

    (StatusCode.BUSINESS_RULE_RESTRICTED,
     '违反业务规则，例如当前账号状态不允许该操作。',
     '按返回的 msg 提示处理；属于账号限制的请联系管理员。'),
    (StatusCode.STATUS_NOT_ALLOWED,
     '对象当前状态不允许执行该操作。',
     '按提示调整对象状态后再试。'),
    (StatusCode.SERVICE_MAINTENANCE,
     '该服务正在维护，命中路径的请求被统一拦截。',
     '稍后重试，或关注该服务的公告。'),
    (StatusCode.SERVICE_OFFLINE,
     '该服务已下线。',
     '改用其它可用服务或线路。'),
    (StatusCode.SERVICE_DEVELOPING,
     '该服务还在开发中，暂未对外开放。',
     '等待服务上线后再调用。'),
    (StatusCode.QUOTA_EXCEEDED,
     '项目的当日 / 当月调用量已达到配额上限。',
     '等待配额周期重置，或联系管理员调整配额。'),

    (StatusCode.EXTERNAL_API_FAILED,
     '平台调用上游第三方服务失败（上游异常或网络问题）。',
     '稍后重试；若持续失败请反馈，平台会排查上游链路。'),

    (StatusCode.INTERNAL_ERROR,
     '服务端发生未预期的内部异常。',
     '稍后重试；若持续失败请反馈。'),
    (StatusCode.SERVICE_UNAVAILABLE,
     '服务暂时不可用（维护或过载）。',
     '稍后重试。'),

    (StatusCode.UNKNOWN_ERROR,
     '发生了未归类的错误。',
     '稍后重试；若持续失败请反馈。'),
)


def error_groups():
    """按「状态码类别」分组的错误码说明（当前语言）

    每次调用现取文案：gettext 在请求期调用才能命中当前语言，
    不像文档声明那样需要在副本上翻译。
    """
    groups = OrderedDict()
    for code, scenario, suggestion in _ENTRIES:
        groups.setdefault(StatusCode.category(code), []).append({
            'code': code,
            'msg': _(StatusCode.get_message(code)),
            'scenario': _(scenario),
            'suggestion': _(suggestion),
        })
    return [{'category': _(category), 'codes': codes} for category, codes in groups.items()]
