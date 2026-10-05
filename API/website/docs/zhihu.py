"""知乎服务文档（声明式）

约定（见 docs/__init__.py 顶部说明）：中文为源语言，**不要在声明处调用 gettext**；
渲染前由 docs.localize() 对副本逐字段翻译，译文词条在 locale/*/LC_MESSAGES 里维护。
"""
from .schema import ChannelSpec, EndpointSpec, ParamSpec, ResponseFieldSpec, ServiceSpec

SERVICE = ServiceSpec(
    slug='zhihu',
    name='知乎',
    prefix='/api/zhihu/',
    summary='知乎热榜与内容检索：热榜按排名返回当前热点问题；综合搜索按关键词返回结果（每条自带完整正文与图片）；问题 / 专栏文章详情返回正文与图片、评论、相关问题与「大家都在搜」。',
    keywords='知乎热榜API,知乎热榜接口,知乎热点,知乎榜单数据,知乎搜索API,知乎问题详情,知乎回答评论,知乎专栏文章',
    intro=[
        '知乎热榜接口，返回当前知乎热榜的排名、标题、直达链接、摘要、热度与回答数，'
        '适合做热点聚合、选题参考与内容看板。',
        '**综合搜索** `/api/zhihu/search`：按关键词搜索知乎内容，**每条结果直接带完整正文与图片**'
        '（不是摘要）、作者、赞同数与评论数，并附「大家都在搜」；用 `offset` 翻页。',
        '**登录凭据两种用法**：一是在请求里带上 `cookie`（你自己的知乎登录 Cookie，'
        '仅本次生效、我们不存储）；不带则回落到**平台统一托管**的账号 —— '
        '平台在后台「账号管理」维护知乎账号与登录 Cookie，接口自动取一份可用凭据去访问。'
        '在文档页右侧栏「本机凭据」粘贴并「保存到本机浏览器」，在线调试会自动带上。'
        '若平台托管的凭据失效，接口会明确提示需要重新登录，并把该账号标记为「已过期」。',
        '**问题详情** `/api/zhihu/question`：传问题 ID（或问题网页地址）即可拿到问题正文与其中'
        '的图片、回答列表（含正文图片与各自的热门评论）、问题本身的评论、相关问题与'
        '「大家都在搜」；回答条数与评论条数都可用参数调整。',
        '**专栏文章详情** `/api/zhihu/article`：传文章 ID（或文章网页地址）即可拿到**完整正文**'
        '与其中的图片、评论与「大家都在搜」。文章页只有这三个模块 —— 没有「回答列表」和'
        '「相关问题」（后者是问题页专有）。',
        '`/api/zhihu/check` 用于校验一份知乎凭据是否仍然有效：带上 `cookie` 就校验你自己那份'
        '（完全不碰平台账号），不带则校验平台托管的账号并把结果回写到账号状态。',
    ],
    channels=[
        ChannelSpec(
            slug='zhihu',
            name='知乎',
            provider='知乎（zhihu.com）',
            auth_note='auth',
            note='数据来自知乎官方 web 接口；调用方可自带登录 Cookie，不传则用平台托管的账号。',
            endpoints=[
                EndpointSpec(
                    slug='hot',
                    name='热榜',
                    method='POST',
                    path='/api/zhihu/hot',
                    summary='获取知乎热榜（默认 50 条，最多 50 条）。',
                    params=[
                        ParamSpec('limit', '返回条数', kind='number', default='50',
                                  placeholder='如 50',
                                  desc='可选，1~50，默认 50。超出范围返回参数值非法。'),
                        ParamSpec('cookie', '知乎登录 Cookie', kind='textarea', local=True,
                                  placeholder='在右侧栏「本机凭据」粘贴并保存到本机',
                                  desc='可选。填了就用你这份 Cookie 访问（仅本次生效、不落库、'
                                       '不会上传给我们）；留空则用平台统一托管的账号。'),
                    ],
                    notes=[
                        '热度为知乎原始文案（如「1370 万热度」），未做数值化处理，避免口径误读。',
                        '`url` 是可在浏览器直接打开的网页地址；`question_id` 为知乎问题 ID。',
                        '也接受 GET（此时参数走 query 串）；因知乎 Cookie 较长，推荐用 POST 放表单体。',
                    ],
                    response_fields=[
                        ResponseFieldSpec('count', 'int', '本次返回的条数'),
                        ResponseFieldSpec('list[].rank', 'int', '排名，从 1 开始'),
                        ResponseFieldSpec('list[].title', 'string', '标题'),
                        ResponseFieldSpec('list[].url', 'string', '网页地址（可直接打开）'),
                        ResponseFieldSpec('list[].excerpt', 'string', '摘要（可能为空）'),
                        ResponseFieldSpec('list[].hot', 'string', '热度文案，如「1370 万热度」'),
                        ResponseFieldSpec('list[].answer_count', 'int', '回答数（可能为 0）'),
                        ResponseFieldSpec('list[].question_id', 'int', '知乎问题 ID'),
                        ResponseFieldSpec('list[].cover', 'string', '封面图地址（可能为空）'),
                    ],
                ),
                EndpointSpec(
                    slug='question',
                    name='问题详情',
                    method='POST',
                    path='/api/zhihu/question',
                    summary='问题详情：问题正文与图片、回答（含图片与评论）、问题评论、相关问题、大家都在搜。',
                    params=[
                        ParamSpec('question_id', '问题 ID 或网页地址', required=True,
                                  placeholder='如 2089437755591713926',
                                  desc='必填。知乎问题 ID（纯数字），也可以直接填问题网页地址'
                                       '（形如 https://www.zhihu.com/question/2089437755591713926）。'),
                        ParamSpec('answer_limit', '回答条数', kind='number', default='5',
                                  placeholder='如 5',
                                  desc='可选，1~20，默认 5。返回多少条回答。'),
                        ParamSpec('comment_limit', '每条回答的评论数', kind='number', default='3',
                                  placeholder='如 3',
                                  desc='可选，0~20，默认 3。每条回答返回多少条热门评论（0 = 不取）。'),
                        ParamSpec('question_comment_limit', '问题评论数', kind='number',
                                  default='10', placeholder='如 10',
                                  desc='可选，0~20，默认 10。问题本身的评论返回多少条（0 = 不取）。'),
                        ParamSpec('cookie', '知乎登录 Cookie', kind='textarea', local=True,
                                  placeholder='在右侧栏「本机凭据」粘贴并保存到本机',
                                  desc='可选。填了就用你这份 Cookie 访问（仅本次生效、不落库、'
                                       '不会上传给我们）；留空则用平台统一托管的账号。'),
                    ],
                    notes=[
                        '**图片**：问题正文与回答正文都同时给出 HTML 原文（`detail` / `content`，'
                        '可直接渲染）与抽好的 `images` 图片地址数组（原图优先、已去重）。',
                        '**评论**：问题评论在 `question.comments`，每条回答的评论在该回答的 '
                        '`comments` 里；每条评论会内联最多 3 条子评论（回复）。',
                        '`answer_count` / `comment_count` 是**总数**，不等于本次返回的条数 —— '
                        '本次条数由 `answer_limit` / `comment_limit` 决定。',
                        '「相关问题」由知乎动态给出，条数不固定（最多 5 条）；「大家都在搜」固定 10 条，'
                        '并附带可直接打开的知乎搜索页地址。',
                        '问题本体（标题 / 正文 / 话题 / 计数）解析自问题页内嵌数据'
                        '（知乎该接口带签名校验，无法直取）；解析失败时接口会明确报错。',
                        '也接受 GET（此时参数走 query 串）；因知乎 Cookie 较长，推荐用 POST 放表单体。',
                    ],
                    response_fields=[
                        ResponseFieldSpec('question.id', 'string', '问题 ID'),
                        ResponseFieldSpec('question.title', 'string', '标题'),
                        ResponseFieldSpec('question.url', 'string', '问题网页地址'),
                        ResponseFieldSpec('question.detail', 'string', '问题正文 HTML（原样保留）'),
                        ResponseFieldSpec('question.images', 'array', '问题正文里的图片地址'),
                        ResponseFieldSpec('question.excerpt', 'string', '正文摘要'),
                        ResponseFieldSpec('question.topics[].name', 'string', '话题名'),
                        ResponseFieldSpec('question.topics[].url', 'string', '话题网页地址'),
                        ResponseFieldSpec('question.answer_count', 'int', '回答总数'),
                        ResponseFieldSpec('question.follower_count', 'int', '关注者数'),
                        ResponseFieldSpec('question.comment_count', 'int', '评论总数'),
                        ResponseFieldSpec('question.visit_count', 'int', '被浏览数'),
                        ResponseFieldSpec('question.created_time', 'int', '创建时间（Unix 秒）'),
                        ResponseFieldSpec('question.updated_time', 'int', '更新时间（Unix 秒）'),
                        ResponseFieldSpec('question.comments[]', 'array', '问题评论（结构见下）'),
                        ResponseFieldSpec('comments[].id', 'string', '评论 ID'),
                        ResponseFieldSpec('comments[].content', 'string', '评论正文（纯文本）'),
                        ResponseFieldSpec('comments[].author.name', 'string', '评论者昵称'),
                        ResponseFieldSpec('comments[].like_count', 'int', '点赞数'),
                        ResponseFieldSpec('comments[].child_comment_count', 'int', '子评论总数'),
                        ResponseFieldSpec('comments[].reply_to_author', 'string', '回复的对象（子评论才有）'),
                        ResponseFieldSpec('comments[].child_comments[]', 'array',
                                          '内联的子评论（最多 3 条，结构与父评论一致）'),
                        ResponseFieldSpec('answers[].id', 'string', '回答 ID'),
                        ResponseFieldSpec('answers[].url', 'string', '回答网页地址'),
                        ResponseFieldSpec('answers[].content', 'string', '回答正文 HTML'),
                        ResponseFieldSpec('answers[].images', 'array', '回答正文里的图片地址'),
                        ResponseFieldSpec('answers[].excerpt', 'string', '回答摘要'),
                        ResponseFieldSpec('answers[].author.name', 'string', '回答者昵称'),
                        ResponseFieldSpec('answers[].author.url', 'string', '回答者主页地址'),
                        ResponseFieldSpec('answers[].voteup_count', 'int', '赞同数'),
                        ResponseFieldSpec('answers[].comment_count', 'int', '该回答的评论总数'),
                        ResponseFieldSpec('answers[].comments[]', 'array',
                                          '该回答的评论（结构与 question.comments[] 一致）'),
                        ResponseFieldSpec('related_questions[].title', 'string', '相关问题标题'),
                        ResponseFieldSpec('related_questions[].url', 'string', '相关问题网页地址'),
                        ResponseFieldSpec('related_questions[].answer_count', 'int', '回答数'),
                        ResponseFieldSpec('related_questions[].follower_count', 'int', '关注者数'),
                        ResponseFieldSpec('hot_searches[].query', 'string', '搜索词'),
                        ResponseFieldSpec('hot_searches[].hot', 'int', '热度值'),
                        ResponseFieldSpec('hot_searches[].hot_show', 'string', '热度文案（如「648 万」）'),
                        ResponseFieldSpec('hot_searches[].url', 'string', '知乎搜索页地址'),
                    ],
                ),
                EndpointSpec(
                    slug='article',
                    name='专栏文章详情',
                    method='POST',
                    path='/api/zhihu/article',
                    summary='知乎专栏文章详情：完整正文与图片、评论、大家都在搜。',
                    params=[
                        ParamSpec('article_id', '文章 ID 或网页地址', required=True,
                                  placeholder='如 608180793',
                                  desc='必填。知乎文章 ID（纯数字），也可以直接填文章网页地址'
                                       '（形如 https://zhuanlan.zhihu.com/p/608180793）。'),
                        ParamSpec('comment_limit', '评论数', kind='number', default='10',
                                  placeholder='如 10',
                                  desc='可选，0~20，默认 10。返回多少条热门评论（0 = 不取）。'),
                        ParamSpec('cookie', '知乎登录 Cookie', kind='textarea', local=True,
                                  placeholder='在右侧栏「本机凭据」粘贴并保存到本机',
                                  desc='可选。填了就用你这份 Cookie 访问（仅本次生效、不落库、'
                                       '不会上传给我们）；留空则用平台统一托管的账号。'),
                    ],
                    notes=[
                        '**正文是全文**：取的是文章页内嵌的完整正文，不是摘要；'
                        '`content_truncated` 为 `true` 时才表示知乎把超长文章的正文截断了（罕见）。',
                        '**图片**：`content` 是 HTML 原文（可直接渲染），`images` 是抽好的图片地址'
                        '数组（原图优先、已去重）。',
                        '**文章页只有三个模块**：正文、评论、大家都在搜 —— 没有「回答列表」与'
                        '「相关问题」（后者是问题页专有）。',
                        '`comment_count` 是评论**总数**，不等于本次返回的条数（本次条数由'
                        '`comment_limit` 决定）。',
                        '也接受 GET（此时参数走 query 串）；因知乎 Cookie 较长，推荐用 POST 放表单体。',
                    ],
                    response_fields=[
                        ResponseFieldSpec('article.id', 'string', '文章 ID'),
                        ResponseFieldSpec('article.title', 'string', '标题'),
                        ResponseFieldSpec('article.url', 'string', '文章网页地址'),
                        ResponseFieldSpec('article.content', 'string',
                                          '文章正文 HTML（原样保留，可含图片 / 代码块 / 引用）'),
                        ResponseFieldSpec('article.images', 'array', '正文里的图片地址'),
                        ResponseFieldSpec('article.excerpt', 'string', '摘要'),
                        ResponseFieldSpec('article.topics[].name', 'string', '话题名'),
                        ResponseFieldSpec('article.topics[].url', 'string', '话题网页地址'),
                        ResponseFieldSpec('article.author.name', 'string', '作者昵称'),
                        ResponseFieldSpec('article.author.url', 'string', '作者主页地址'),
                        ResponseFieldSpec('article.voteup_count', 'int', '赞同数'),
                        ResponseFieldSpec('article.comment_count', 'int', '评论总数'),
                        ResponseFieldSpec('article.liked_count', 'int', '「喜欢」数'),
                        ResponseFieldSpec('article.favlists_count', 'int', '收藏数'),
                        ResponseFieldSpec('article.content_truncated', 'bool',
                                          '正文是否被知乎截断（true 表示拿到的不是全文）'),
                        ResponseFieldSpec('article.created_time', 'int', '发布时间（Unix 秒）'),
                        ResponseFieldSpec('article.updated_time', 'int', '更新时间（Unix 秒）'),
                        ResponseFieldSpec('article.comments[]', 'array',
                                          '评论（结构与 question.comments[] 一致）'),
                        ResponseFieldSpec('hot_searches[].query', 'string', '搜索词'),
                        ResponseFieldSpec('hot_searches[].url', 'string', '知乎搜索页地址'),
                    ],
                ),
                EndpointSpec(
                    slug='search',
                    name='综合搜索',
                    method='POST',
                    path='/api/zhihu/search',
                    summary='知乎综合搜索：结果列表（每条自带完整正文与图片）+「大家都在搜」。',
                    params=[
                        ParamSpec('q', '搜索关键词', required=True,
                                  placeholder='如 学生妹',
                                  desc='必填。要搜索的关键词。'),
                        ParamSpec('limit', '返回条数', kind='number', default='20',
                                  placeholder='如 20',
                                  desc='可选，1~20，默认 20（知乎单页上限就是 20 条）。'),
                        ParamSpec('offset', '翻页偏移', kind='number', default='0',
                                  placeholder='如 0',
                                  desc='可选，0~1000，默认 0。翻页时把上一次返回的 `next_offset` 填进来。'),
                        ParamSpec('cookie', '知乎登录 Cookie', kind='textarea', local=True,
                                  placeholder='在右侧栏「本机凭据」粘贴并保存到本机',
                                  desc='可选。填了就用你这份 Cookie 访问（仅本次生效、不落库、'
                                       '不会上传给我们）；留空则用平台统一托管的账号。'),
                    ],
                    notes=[
                        '**每条结果直接带完整正文**（`content`，实测最长上万字，不是摘要），'
                        '所以「阅读全文」不需要再逐条回源。',
                        '结果类型有 `answer`（回答）/ `article`（专栏文章）/ `zvideo`（视频）；'
                        '视频没有正文，`content` 为空字符串。回答会带 `question`（所属问题），'
                        '文章与视频为 `null`。',
                        '**评论只给数量**（`comment_count`，即页面上的「N 条评论」），不逐条回源 —— '
                        '否则一次搜索要打几十个请求；要评论内容请用问题详情 / 专栏文章详情接口。',
                        '标题与摘要里的 `<em>` 高亮标签已去掉、HTML 实体已还原，是可直接展示的纯文本。',
                        '**翻页**：把返回的 `next_offset` 作为下一次的 `offset`；`is_end` 为 `true` 时 '
                        '`next_offset` 为 `null`，表示没有下一页了。',
                        '也接受 GET（此时参数走 query 串）；因知乎 Cookie 较长，推荐用 POST 放表单体。',
                    ],
                    response_fields=[
                        ResponseFieldSpec('count', 'int', '本次返回的条数'),
                        ResponseFieldSpec('is_end', 'bool', '是否已到最后一页'),
                        ResponseFieldSpec('next_offset', 'int', '下一页的 offset（已是最后一页时为 null）'),
                        ResponseFieldSpec('list[].index', 'int', '本页内的序号，从 1 开始'),
                        ResponseFieldSpec('list[].type', 'string',
                                          '结果类型：answer / article / zvideo'),
                        ResponseFieldSpec('list[].id', 'string', '内容 ID'),
                        ResponseFieldSpec('list[].title', 'string', '标题（已去高亮标签）'),
                        ResponseFieldSpec('list[].url', 'string', '网页地址（可直接打开）'),
                        ResponseFieldSpec('list[].content', 'string',
                                          '完整正文 HTML（视频为空）'),
                        ResponseFieldSpec('list[].images', 'array', '正文里的图片地址'),
                        ResponseFieldSpec('list[].excerpt', 'string', '摘要（已去高亮标签）'),
                        ResponseFieldSpec('list[].author.name', 'string', '作者昵称'),
                        ResponseFieldSpec('list[].author.url', 'string', '作者主页地址'),
                        ResponseFieldSpec('list[].voteup_count', 'int', '赞同数'),
                        ResponseFieldSpec('list[].comment_count', 'int', '评论数'),
                        ResponseFieldSpec('list[].created_time', 'int', '发布时间（Unix 秒）'),
                        ResponseFieldSpec('list[].question.title', 'string',
                                          '回答所属问题的标题（非回答时为空）'),
                        ResponseFieldSpec('hot_searches[].query', 'string', '搜索词'),
                        ResponseFieldSpec('hot_searches[].url', 'string', '知乎搜索页地址'),
                    ],
                ),
                EndpointSpec(
                    slug='check',
                    name='校验登录凭据',
                    method='POST',
                    path='/api/zhihu/check',
                    summary='校验知乎登录凭据是否有效（自带 cookie 校验你自己那份，否则校验平台托管的账号）。',
                    params=[
                        ParamSpec('cookie', '知乎登录 Cookie', kind='textarea', local=True,
                                  placeholder='在右侧栏「本机凭据」粘贴并保存到本机',
                                  desc='可选。填了就只校验你这份（不碰平台账号、不回写任何状态）；'
                                       '留空则校验平台托管的账号并把结果回写其状态。'),
                    ],
                    notes=[
                        '凭据无效**不算接口调用失败**：仍返回成功码，把 `valid=false` 与原因放在 data 里，'
                        '由调用方自行决定是否提示用户重新登录。',
                        '校验平台托管的账号时会更新其「凭据状态」与「最近校验结果」，'
                        '在后台「账号管理」页可直接看到；自带 Cookie 校验不涉及平台账号。',
                        '也接受 GET（此时参数走 query 串）；因知乎 Cookie 较长，推荐用 POST 放表单体。',
                    ],
                    response_fields=[
                        ResponseFieldSpec('valid', 'bool', '凭据是否有效'),
                        ResponseFieldSpec('account', 'string', '被校验的账号标识（自带 Cookie 校验时为空）'),
                        ResponseFieldSpec('message', 'string', '校验说明（有效时含登录用户名）'),
                    ],
                ),
            ],
        ),
    ],
)
