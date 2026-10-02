"""渠道实现集合（导入本包即完成全部渠道的登记）"""
from API.apis.pay.providers.base import BasePayProvider, PayError
from API.apis.pay.providers.registry import (
    PROVIDER_CLASSES,
    build_provider,
    get_provider_class,
    provider_codes,
    provider_names,
)

__all__ = [
    'BasePayProvider',
    'PayError',
    'PROVIDER_CLASSES',
    'build_provider',
    'get_provider_class',
    'provider_codes',
    'provider_names',
]
