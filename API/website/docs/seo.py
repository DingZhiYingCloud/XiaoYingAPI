"""SEO 服务 - 接口文档与在线调试数据

数据与 API/apis/seo/ 实际实现对齐（分类树 /api/seo/ 为需签名）：
- 友情链接 friend_links：站点友情链接集合的 RESTful 增删改查。
后续接入更多 SEO 能力（robots/sitemap/外链检测等）时在 channels 追加即可。
"""
from .schema import ChannelSpec, EndpointSpec, ParamSpec, ServiceSpec

# 状态选择：启用/禁用
_STATUS_SEL = [
    {'value': 'true', 'label': 'true（启用，默认）'},
    {'value': 'false', 'label': 'false（禁用）'},
]

# 基础展示字段
_BASE_FIELDS = {
    'description': ParamSpec('description', '网站描述', kind='textarea',
                             placeholder='一句话介绍该网站', desc='选填：用于 SEO 友链展示'),
    'logo': ParamSpec('logo', 'Logo 链接', kind='text',
                      placeholder='https://example.com/logo.png', desc='选填：网站 logo 完整 URL'),
    'category': ParamSpec('category', '分类', kind='text',
                          placeholder='如：技术 / 工具 / 导航', desc='选填：便于按类目筛选'),
    'contact': ParamSpec('contact', '联系方式', kind='text',
                         placeholder='QQ / 微信 / 邮箱', desc='选填'),
    'sort': ParamSpec('sort', '排序权重', kind='number', default='0',
                      desc='选填：越大越靠前，默认 0'),
    'status': ParamSpec('status', '启用状态', kind='select', options=_STATUS_SEL,
                        default='true', desc='选填：默认启用'),
}


def _link_id_param():
    return ParamSpec('link_id', '友情链接 ID', kind='number', required=True,
                     placeholder='如：1', desc='路径参数：友情链接主键 ID（创建/列表返回）')


SERVICE = ServiceSpec(
    slug='seo',
    name='SEO 服务',
    prefix='/api/seo/',
    summary='SEO 周边能力：友情链接集合的统一管理（列表/详情/新增/更新/删除），便于站点外链建设。当前接入友情链接线路。',
    channels=[
        ChannelSpec(
            slug='friend_links',
            name='友情链接',
            provider='站点友情链接库（seo_friend_link）',
            auth_note='auth',
            note='RESTful：GET/POST 作用于集合，GET/PATCH/DELETE 按数字主键 id 操作单条。',
            endpoints=[
                EndpointSpec('list', '友情链接列表', 'GET', '/api/seo/friend_links',
                             summary='查询全部友情链接，支持关键词/分类/状态筛选。',
                             params=[
                                 ParamSpec('keyword', '关键词', kind='text',
                                           placeholder='名称 / URL / 描述', desc='选填：模糊匹配名称/链接/描述'),
                                 ParamSpec('category', '分类', kind='text', desc='选填：分类精确匹配'),
                                 ParamSpec('status', '状态过滤', kind='select',
                                           options=[{'value': '', 'label': '全部（不传）'},
                                                    {'value': 'true', 'label': 'true（启用）'},
                                                    {'value': 'false', 'label': 'false（禁用）'}],
                                           desc='选填：true/false'),
                             ],
                             notes=['返回 data={items, total}，items 按 sort 降序排列。']),
                EndpointSpec('create', '创建友情链接', 'POST', '/api/seo/friend_links',
                             summary='新增一条友情链接（name 必填、url 必填且全局唯一）。',
                             params=[
                                 ParamSpec('name', '网站名称', kind='text', required=True,
                                           placeholder='如：小影API', desc='必填：网站名称（可重复）'),
                                 ParamSpec('url', '网站链接', kind='text', required=True,
                                           placeholder='https://example.com',
                                           desc='必填：完整 URL，全局唯一'),
                                 _BASE_FIELDS['description'],
                                 _BASE_FIELDS['logo'],
                                 _BASE_FIELDS['category'],
                                 _BASE_FIELDS['contact'],
                                 _BASE_FIELDS['sort'],
                                 _BASE_FIELDS['status'],
                             ],
                             notes=['url 已存在时返回数据冲突错误。']),
                EndpointSpec('detail', '获取单条', 'GET', '/api/seo/friend_links/<id>',
                             summary='按主键 id 获取一条友情链接详情。',
                             params=[_link_id_param()]),
                EndpointSpec('update', '更新友情链接', 'PATCH', '/api/seo/friend_links/<id>',
                             summary='部分字段更新：只更新本次传入的字段，未传字段保持不变。',
                             params=[
                                 _link_id_param(),
                                 ParamSpec('name', '网站名称', kind='text', desc='选填：新名称'),
                                 ParamSpec('url', '网站链接', kind='text',
                                           placeholder='https://example.com', desc='选填：新链接'),
                                 _BASE_FIELDS['description'],
                                 _BASE_FIELDS['logo'],
                                 _BASE_FIELDS['category'],
                                 _BASE_FIELDS['contact'],
                                 _BASE_FIELDS['sort'],
                                 _BASE_FIELDS['status'],
                             ]),
                EndpointSpec('delete', '删除友情链接', 'DELETE', '/api/seo/friend_links/<id>',
                             summary='按主键 id 删除一条友情链接。',
                             params=[_link_id_param()]),
            ],
        ),
    ],
)
