"""API 文档中心注册表

将各服务的文档模块（如 email.py）汇总为统一查询入口。
后续新增服务：新建 <服务>.py 定义 ServiceSpec，并在此 import 追加即可，
模板 / 视图 / 调试代调全部自动支持，无需改动。

多语言说明：各声明模块在导入时即构造 ServiceSpec 常量，若在声明处调用 gettext，
译文会被首次导入时的语言固化，故中文为源语言原样保留，渲染前统一调用 localize()
对副本做翻译（见下方 localize）。
"""
import copy

from django.utils.translation import gettext as _

from . import email as _email
from . import music as _music
from . import video_analysis as _video
from . import sms_verify as _sms_verify
from . import captcha_auth as _captcha_auth
from . import captcha_self as _captcha_self
from . import ddddocr as _ddddocr
from . import upload as _upload
from . import seo as _seo
from . import spider_verification as _spider_verification
from . import proxy_ip as _proxy_ip
from . import feedback as _feedback
from . import statistics as _statistics
from . import ai as _ai
from . import dlt as _dlt
from . import dlwz as _dlwz
from . import user_center as _user_center
from .schema import (ChannelSpec, EndpointSpec, ParamSpec, ServiceSpec)  # noqa: F401 便于外部引用

# 已接入文档的服务（顺序即 /docs/ 目录展示顺序）
_SERVICES = [
    _email.SERVICE,
    _music.SERVICE,
    _video.SERVICE,
    _sms_verify.SERVICE,
    _captcha_auth.SERVICE,
    _captcha_self.SERVICE,
    _ddddocr.SERVICE,
    _upload.SERVICE,
    _seo.SERVICE,
    _spider_verification.SERVICE,
    _proxy_ip.SERVICE,
    _feedback.SERVICE,
    _statistics.SERVICE,
    _ai.SERVICE,
    _dlt.SERVICE,
    _dlwz.SERVICE,
    _user_center.SERVICE,
]

ALL = {svc.slug: svc for svc in _SERVICES}

# 调试代调白名单：路径 -> 允许的方法集合（同一路径可支持多方法），只允许转发已声明的端点
ALL_ENDPOINTS = {}
for _svc in _SERVICES:
    for _channel in _svc.channels:
        for _ep in _channel.endpoints:
            ALL_ENDPOINTS.setdefault(_ep.path, set()).add(_ep.method)


def all_docs():
    """按声明顺序返回全部服务文档"""
    return list(_SERVICES)


def get_doc(slug: str):
    """按 slug 获取服务文档，不存在返回 None"""
    return ALL.get(slug)


def localize(spec: ServiceSpec) -> ServiceSpec:
    """返回按当前语言翻译后的服务文档「副本」

    声明模块导出的 SERVICE 是模块级常量，翻译必须发生在副本上，
    否则会污染全局（首次翻译后其它语言将读到同一份译文）。
    """
    doc = copy.deepcopy(spec)
    doc.name, doc.summary = _(doc.name), _(doc.summary)
    for channel in doc.channels:
        channel.name = _(channel.name)
        channel.provider = _(channel.provider)
        channel.note = _(channel.note)
        for endpoint in channel.endpoints:
            endpoint.name, endpoint.summary = _(endpoint.name), _(endpoint.summary)
            endpoint.notes = [_(n) for n in endpoint.notes]
            for param in endpoint.params:
                param.label, param.desc = _(param.label), _(param.desc)
                param.placeholder = _(param.placeholder)
                param.repeat_hint = _(param.repeat_hint)
                for option in (param.options or []):
                    option['label'] = _(option['label'])
    return doc
