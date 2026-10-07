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
from . import douyin as _douyin
from . import sms_verify as _sms_verify
from . import captcha_auth as _captcha_auth
from . import captcha_self as _captcha_self
from . import ddddocr as _ddddocr
from . import upload as _upload
from . import image_hosting as _image_hosting
from . import seo as _seo
from . import spider_verification as _spider_verification
from . import proxy_ip as _proxy_ip
from . import feedback as _feedback
from . import statistics as _statistics
from . import ai as _ai
from . import dlt as _dlt
from . import dlwz as _dlwz
from . import user_center as _user_center
from . import movie as _movie
from . import drama as _drama
from . import haijiao as _haijiao
from . import zhihu as _zhihu
from . import weibo as _weibo
from . import pay as _pay
from . import order_migration as _order_migration
from . import push as _push
from .schema import (ChannelSpec, EndpointSpec, ParamSpec, ResponseFieldSpec,  # noqa: F401
                     ServiceSpec)  # noqa: F401 便于外部引用

# 已接入文档的服务（顺序即 /docs/ 目录展示顺序）
_SERVICES = [
    _email.SERVICE,
    _music.SERVICE,
    _douyin.SERVICE,
    _sms_verify.SERVICE,
    _captcha_auth.SERVICE,
    _captcha_self.SERVICE,
    _ddddocr.SERVICE,
    _upload.SERVICE,
    _image_hosting.SERVICE,
    _seo.SERVICE,
    _spider_verification.SERVICE,
    _proxy_ip.SERVICE,
    _feedback.SERVICE,
    _statistics.SERVICE,
    _ai.SERVICE,
    _dlt.SERVICE,
    _dlwz.SERVICE,
    _user_center.SERVICE,
    _movie.SERVICE,
    _drama.SERVICE,
    _haijiao.SERVICE,
    _zhihu.SERVICE,
    _weibo.SERVICE,
    _pay.SERVICE,
    _order_migration.SERVICE,
    _push.SERVICE,
]

ALL = {svc.slug: svc for svc in _SERVICES}

# 调试代调白名单：路径 -> 允许的方法集合（同一路径可支持多方法），只允许转发已声明的端点
ALL_ENDPOINTS = {}
# 路径 -> 端点声明（同一路径多方法时取首个声明）：调试代调据此读取 path_params 等声明信息
ALL_ENDPOINT_SPECS = {}
for _svc in _SERVICES:
    for _channel in _svc.channels:
        for _ep in _channel.endpoints:
            ALL_ENDPOINTS.setdefault(_ep.path, set()).add(_ep.method)
            ALL_ENDPOINT_SPECS.setdefault(_ep.path, _ep)


def _ai_model_options():
    """AI 模型下拉选项（来自 ai_model 表）

    声明里只写 dynamic_options='ai_models'，渲染前由文档视图调用本函数取值。
    首项空值表示「不传 model、使用默认模型」。
    """
    from API.apis.ai.BuiltInModel import utils as ai_utils

    options = [{'value': '', 'label': _('不传（使用默认模型）')}]
    for item in ai_utils.public_models():
        label = f"{item['name']}（{item['model']}）"
        if item['is_default']:
            label += f" · {_('默认')}"
        if item['supports_vision']:
            label += f" · {_('支持视觉')}"
        if item['supports_video']:
            label += f" · {_('支持视频')}"
        if item['supports_audio']:
            label += f" · {_('支持音频')}"
        options.append({'value': item['model'], 'label': label})
    return options


def _qqbot_group_options():
    """QQBot 线路「目标号码」下拉：机器人已加入的群（调 NapCat /get_group_list）

    取不到（未配置 / 连不上 / 未加任何群）时只返回一条提示项 —— 用户可切到「手动输入」面板
    直接填群号或好友 QQ 号（下拉只为「发群」提供便利，不阻塞私聊与未列出的目标）。
    文档页每次渲染会实时取一次，故用较短超时，避免上游不可达时拖慢页面。
    """
    from API.apis.push.qqbot import utils as qqbot_utils

    options = [{'value': '', 'label': _('（请选择群聊，或切到「手动输入」）')}]
    ok, groups = qqbot_utils.list_groups(timeout=3)
    if not ok:
        return [{'value': '', 'label': _('（未取到群列表：请在控制台「QQBot」页检查配置，或切到「手动输入」）')}]
    options += [{'value': str(g.get('group_id')),
                 'label': f"{g.get('group_name') or _('未命名群')}（{g.get('group_id')}）"}
                for g in groups if g.get('group_id')]
    return options


# 动态下拉选项提供者：ParamSpec.dynamic_options 里写的名字 -> 取选项的函数
# （用于「选项来自运行期数据」的场景；静态选项请直接写在 ParamSpec.options 里）
OPTION_LOADERS = {
    'ai_models': _ai_model_options,
    'dlt_games': _dlt._dlt_game_options,
    'qqbot_groups': _qqbot_group_options,
}


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
    doc.keywords = _(doc.keywords)
    doc.intro = [_(para) for para in doc.intro]
    for channel in doc.channels:
        channel.name = _(channel.name)
        channel.provider = _(channel.provider)
        channel.note = _(channel.note)
        for endpoint in channel.endpoints:
            endpoint.name, endpoint.summary = _(endpoint.name), _(endpoint.summary)
            endpoint.notes = [_(n) for n in endpoint.notes]
            endpoint.tool_label = _(endpoint.tool_label)
            endpoint.response_note = _(endpoint.response_note)
            for field_spec in endpoint.response_fields:
                field_spec.desc = _(field_spec.desc)
            for param in endpoint.params:
                param.label, param.desc = _(param.label), _(param.desc)
                param.placeholder = _(param.placeholder)
                param.repeat_hint = _(param.repeat_hint)
                param.primary_label, param.alt_label = _(param.primary_label), _(param.alt_label)
                for option in (param.options or []):
                    option['label'] = _(option['label'])
                for option in (param.alt_options or []):
                    option['label'] = _(option['label'])
    return doc
