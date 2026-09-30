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
    - dynamic_options 用于「下拉选项来自运行期数据」（如 AI 模型清单存在数据库里）：
      此处只写提供者的名字（见 docs/OPTION_LOADERS 注册表），渲染前由文档视图按名取值
      填进 options。静态选项（options 已写死）不要用它。
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
    dynamic_options: str = ''


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
    # 标记该端点返回可播放媒体地址（如 m3u8）：文档页会渲染在线播放器，
    # 发送请求成功后自动取响应中的 m3u8 播放，也支持手动粘贴地址测试
    player: bool = False
    # 图片解码类端点的「解密说明」正文（段落列表）：非空时文档页会渲染图片解码预览面板
    # （可粘贴加密图片地址→服务端解码后直接显示图片）与「解密说明」按钮，点击弹出详细说明。
    # 段落内换行会原样保留渲染，便于书写多行步骤或代码片段。
    image_help: List[str] = field(default_factory=list)
    # 「一键填写」按钮：填「凭据生成接口」的路径。非空时文档页在本端点表单上方渲染该按钮，
    # 点击后调用该接口取一组用户名/邮箱/密码，自动填入本端点表单的对应输入框。
    auto_fill_path: str = ''
    # 批量注册面板：填「批量注册接口」的路径。非空时文档页在本端点下渲染批量注册面板
    # （填数量 → 取本端点验证码 → 每张验证码配一个输入框 → 一键注册），
    # 用户名/邮箱/密码由批量注册接口在服务端生成。
    batch_register_path: str = ''
    # 路径参数映射：{URL 占位符: 表单参数名}，如 {'uuid': 'account_id'} 表示
    # path 里的 <uuid> 由表单字段 account_id 的值替换。文档页在线调试器据此把
    # 用户填写的路径参数拼进真实 URL（不声明则占位符无法替换）。
    path_params: Dict[str, str] = field(default_factory=dict)
    # 配套工具页入口：填本站工具页路径（按「/<服务>/post/」约定归到服务命名空间，如 /haijiao/post/）时，
    # 文档页会在本端点卡片上渲染一个跳转按钮，便于从文档直接进入可视化工具页；tool_label 为按钮文案。
    tool_path: str = ''
    tool_label: str = ''
    # 礼物选择器：填「礼物列表接口」路径（如 /api/haijiao/gift/list）。非空时文档页在本端点表单上方
    # 渲染礼物面板（金币 / 钻石两栏，含图片、名称、价格），点选即把礼物 ID 填进表单的 item_id。
    gift_picker_path: str = ''


@dataclass
class ChannelSpec:
    """一条线路/平台（同一服务下的不同来源，如 v1 / VMEmail，或未来的其他平台）

    auth_note 仅用于展示提示（open=开放无需签名 / auth=需签名 / inherit=跟随上级），
    实际鉴权由后端「服务策略」（ApiServicePolicy，服务→线路→端点逐级继承）决定，
    调试器以真实请求结果为准。
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
    # 额外的 SEO 关键词（可选，逗号分隔的短语，如 '音乐源接口'）：
    # 文档页的 <meta keywords> 默认是「服务名,接口文档,小影API」，配了本项会追加在后面，
    # 用于补充服务名本身覆盖不到的长尾词。留空则行为与从前完全一致。
    keywords: str = ''
    # 服务正文说明（SEO 用）：段落列表，渲染在文档页「服务说明」区块。
    # 目的是给每个服务页提供一段独有的正文，避免整页只有参数表这类模板化内容而
    # 被搜索引擎判为薄内容。中文为源语言，渲染前由 docs.localize() 逐段翻译。
    intro: List[str] = field(default_factory=list)
    # 库内账号搜索接口路径（如 /api/haijiao/accounts）。声明后，本服务下**带 account_id 参数**的
    # 端点会自动渲染「账号选择器」：输入关键词 → 列出匹配的库内账号 → 点选即填入 account_id / user_id。
    account_search_path: str = ''
    channels: List[ChannelSpec] = field(default_factory=list)
