"""支付渠道注册表

**新增一个支付渠道只要动两处**：
    1. 在 `providers/` 下新建实现文件（继承 BasePayProvider）；
    2. 在本文件的 `PROVIDER_CLASSES` 里加一行 import + 一行登记。

后台「支付设置」页会按这里的渠道清单初始化/展示配置行（`PayProvider` 一行一渠道）。
"""
from API.apis.pay.providers.base import BasePayProvider
from API.apis.pay.providers.ezfp import EzfpProvider

#: 渠道标识 -> 实现类
PROVIDER_CLASSES = {
    EzfpProvider.code: EzfpProvider,
}


def get_provider_class(code: str):
    """按渠道标识取实现类（不存在返回 None）"""
    return PROVIDER_CLASSES.get((code or '').strip())


def provider_codes() -> list:
    """全部已登记的渠道标识"""
    return sorted(PROVIDER_CLASSES)


def provider_names() -> dict:
    """渠道标识 -> 展示名（后台展示用，避免各处硬编码）"""
    return {code: cls.name for code, cls in PROVIDER_CLASSES.items()}


def provider_name(code: str) -> str:
    """单个渠道的展示名（未登记的渠道原样返回 code）"""
    cls = get_provider_class(code)
    return cls.name if cls is not None else (code or '').strip()


# ==================== 展示用中文标签 ====================
#
# 后台订单列表里的「方式」列要一眼看懂（如「易支付 · 支付宝 · 跳转收银台」），
# 而不是 `ezfp jump` 这种技术值。标签一律在**调用时**取译文（模块级 gettext 会把
# 首次导入时的语言固化，见 docs/__init__.py 的同类说明）；渠道相关的标签从渠道声明里取，
# 新增渠道时不用再补一份映射。

#: 平台返回的「支付形态」-> 中文（与具体渠道无关）
PAY_FORM_LABELS = {
    'qrcode': '二维码',
    'jump': '跳转收银台',
    'html': '网页表单',
}


def pay_form_label(value: str) -> str:
    """支付形态的中文说明（qrcode / jump / html；未知取值原样返回）"""
    from django.utils.translation import gettext as _

    value = (value or '').strip()
    label = PAY_FORM_LABELS.get(value)
    return _(label) if label else value


def pay_type_label(provider_code: str, pay_type: str) -> str:
    """支付方式的中文名（取自渠道声明的 pay_types；渠道或取值不认识时原样返回）"""
    from django.utils.translation import gettext as _

    value = (pay_type or '').strip()
    cls = get_provider_class(provider_code)
    if cls is not None and value in cls.pay_types:
        return _(cls.pay_types[value])
    return value


# ==================== 支付方式品牌图标 ====================
#
# 支付方式是「品牌」，用品牌彩色 Logo 最直观（支付宝蓝 / 微信绿 …），lucide 里没有，
# 故以自托管 SVG 入库（`API/static/img/pay/`），与前端规范「第三方资源以文件入库、不连 CDN」一致。
# 键与各渠道 `pay_types` 的取值保持一致；未登记的取值回退为空串（模板不渲染图标）。

#: 支付方式 -> 图标静态路径
PAY_TYPE_ICONS = {
    'alipay': 'img/pay/alipay.svg',
    'wxpay': 'img/pay/wxpay.svg',
    'qqpay': 'img/pay/qqpay.svg',
    'bank': 'img/pay/bank.svg',
    'jdpay': 'img/pay/jdpay.svg',
    'paypal': 'img/pay/paypal.svg',
    'usdt': 'img/pay/usdt.svg',
    'stripepay': 'img/pay/stripepay.svg',
    'stripealipay': 'img/pay/stripepay.svg',
    'stripewxpay': 'img/pay/stripepay.svg',
}


def pay_type_icon(value: str) -> str:
    """支付方式图标的可直接使用的 URL（未登记返回 ''，调用方据此决定是否渲染图标）

    图标的静态路径 → URL 转换在这里统一做，模板与视图都只拿最终 URL，不必各自拼 static。
    """
    from django.templatetags.static import static

    path = PAY_TYPE_ICONS.get((value or '').strip())
    return static(path) if path else ''


def build_provider(config):
    """由 PayProvider 配置行构造渠道实例

    config 可以是模型实例，也可以是「code + 各字段」的字典（后台预览用）。
    """
    code = config.get('code') if isinstance(config, dict) else getattr(config, 'code', '')
    cls = get_provider_class(code)
    if cls is None:
        return None
    return cls(config)


__all__ = [
    'BasePayProvider',
    'PAY_FORM_LABELS',
    'PROVIDER_CLASSES',
    'build_provider',
    'get_provider_class',
    'pay_form_label',
    'pay_type_icon',
    'pay_type_label',
    'provider_codes',
    'provider_name',
    'provider_names',
]
