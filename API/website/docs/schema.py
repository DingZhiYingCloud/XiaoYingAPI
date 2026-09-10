"""API 文档中心 - 可扩展文档数据模型

设计目标（地基）：后续每个 API 服务 + 每条“线路/平台”都通过声明式数据接入，
无需改动视图与模板：

    服务(ServiceSpec) ──1:N──> 线路/平台(ChannelSpec) ──1:N──> 端点(EndpointSpec)
                                     │
                                     └──0:N──> 参数(ParamSpec)

- 邮箱示例：服务=邮箱服务；线路=邮箱v1(发信) / VMEmail(临时邮箱)；端点=send/generate/emails
- 未来新增：任意服务新增线路（如虚拟邮箱接收平台 B）或新增端点，只需在此模块体系下
  追加声明即可，通用模板/调试器自动渲染。
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class ParamSpec:
    """端点请求参数描述

    kind 支持：text / email / password / number / textarea / select / file
    - repeatable=True 表示同一参数可传多个值（表单 getlist），repeat_hint 说明分隔写法
      （服务端代理会把换行/逗号拆成多个同名参数）。
    - kind='file' 表示 multipart 文件字段（页面渲染 <input type="file">），
      accept 为可选的文件类型提示（如 image/* / video/*），仅作前端过滤提示。
    """
    name: str
    label: str
    kind: str = 'text'
    required: bool = False
    default: str = ''
    placeholder: str = ''
    desc: str = ''
    options: Optional[List[Dict[str, str]]] = None  # select: [{value,label}]
    repeatable: bool = False
    repeat_hint: str = ''
    accept: str = ''


@dataclass
class EndpointSpec:
    """单个接口端点描述（path 为完整 API 路径，如 /api/email/v1/send）"""
    slug: str
    name: str
    method: str  # GET / POST
    path: str
    summary: str = ''
    params: List[ParamSpec] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    # 累计调用次数：运行时由文档视图按统计数据填入（仅展示用，声明处无需设置）
    call_count: int = 0


@dataclass
class ChannelSpec:
    """一条线路/平台（同一服务下的不同来源，如 v1 / VMEmail，或未来的其他平台）

    auth_note 仅用于展示提示（open=开放无需签名 / auth=需签名 / inherit=跟随上级），
    实际鉴权仍由后端 ApiCategory 分类树决定，调试器以真实请求结果为准。
    """
    slug: str
    name: str
    provider: str = ''        # 线路/平台说明，如 “VMEmail(minmail.app) 临时邮箱”
    auth_note: str = ''       # open / auth / inherit
    note: str = ''
    endpoints: List[EndpointSpec] = field(default_factory=list)


@dataclass
class ServiceSpec:
    """一个 API 服务（对应 /api/ 下的一个前缀）"""
    slug: str
    name: str
    prefix: str              # 如 /api/email/
    summary: str = ''
    channels: List[ChannelSpec] = field(default_factory=list)
