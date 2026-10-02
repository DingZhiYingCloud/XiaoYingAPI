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
    'PROVIDER_CLASSES',
    'build_provider',
    'get_provider_class',
    'provider_codes',
    'provider_names',
]
