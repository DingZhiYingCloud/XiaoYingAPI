"""知乎爬虫 - 常量与工具

只放常量与纯函数，不发起网络请求（请求都在 main.py）。
"""
import re
from html import unescape
from urllib.parse import quote

BASE_URL = 'https://www.zhihu.com'
# 热榜（web API）：带登录 Cookie 即可直接取 JSON，实测无需额外的 x-zse-96 签名
HOT_API = f'{BASE_URL}/api/v3/feed/topstory/hot-lists/total'
# 当前登录用户信息：用来判断「这份 Cookie 还有没有效」
ME_API = f'{BASE_URL}/api/v4/me'
# 「大家都在搜」（热搜榜）：带上内容上下文时返回与该内容相关的搜索词
HOT_SEARCH_API = f'{BASE_URL}/api/v4/search/hot_search'
# 综合搜索（实测带 Cookie 直接可用，不需要签名）；结果里已含完整正文
SEARCH_API = f'{BASE_URL}/api/v4/search_v3'

USER_AGENT = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
              '(KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36')

DEFAULT_TIMEOUT = 20
# 热榜条数上限（知乎接口实测按当前榜单条数返回，最多 50）
MAX_LIMIT = 50
# 详情接口的条数上限：回答与评论都限制在这个范围内（避免调用方一次拉太多）
MAX_ANSWERS = 20
MAX_COMMENTS = 20
# 每个回答/问题最多返回几条子评论（知乎接口会把部分子评论内联在父评论里）
MAX_CHILD_COMMENTS = 3
# 搜索：知乎单页最多 20 条；翻页偏移给个上限，避免拿着超大 offset 反复空跑
MAX_SEARCH_LIMIT = 20
MAX_SEARCH_OFFSET = 1000


def build_headers(referer='https://www.zhihu.com/hot'):
    """构造请求头（Cookie 由调用方单独带上）"""
    return {
        'User-Agent': USER_AGENT,
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'zh-CN,zh;q=0.9',
        'Referer': referer,
    }


def question_url(question_id) -> str:
    """知乎问题 ID → 网页地址"""
    return f'{BASE_URL}/question/{question_id}'


def article_url(article_id) -> str:
    """知乎专栏文章 ID → 网页地址"""
    return f'https://zhuanlan.zhihu.com/p/{article_id}'


def answer_url(question_id, answer_id) -> str:
    """问题 ID + 回答 ID → 回答网页地址"""
    return f'{BASE_URL}/question/{question_id}/answer/{answer_id}'


def topic_url(topic_id) -> str:
    return f'{BASE_URL}/topic/{topic_id}'


def search_url(keyword) -> str:
    """搜索词 → 知乎搜索页地址（「大家都在搜」里给出可直接打开的链接）"""
    return f'{BASE_URL}/search?type=content&q={quote(keyword or "")}'


def search_result_url(kind, target_id, question_id='') -> str:
    """搜索结果里「这一条」的网页地址（知乎返回的 object.url 是 API 地址，不能直接用）"""
    if not kind or not target_id:
        return ''
    if kind == 'answer' and question_id:
        return answer_url(question_id, target_id)
    if kind == 'article':
        return article_url(target_id)
    if kind == 'zvideo':
        return f'{BASE_URL}/zvideo/{target_id}'
    return f'{BASE_URL}/{kind}/{target_id}'


TAG_RE = re.compile(r'<[^>]+>')


def strip_html(text) -> str:
    """去掉 HTML 标签并还原实体

    搜索结果的标题 / 摘要里带 `<em>` 高亮标签（如「看完<em>学生妹</em>提供的快餐事件」），
    作为对外数据要去掉标签、还原 `&quot;` 这类实体。
    """
    if not text:
        return ''
    return unescape(TAG_RE.sub('', str(text))).strip()


def question_answers_api(question_id) -> str:
    """回答列表接口"""
    return f'{BASE_URL}/api/v4/questions/{question_id}/answers'


def similar_questions_api(question_id) -> str:
    """相关问题接口"""
    return f'{BASE_URL}/api/v4/questions/{question_id}/similar-questions'


def root_comment_api(kind, target_id) -> str:
    """根评论接口；kind 取 'questions' / 'answers' / 'articles'

    注意是**单数** `root_comment` —— 复数 `root_comments` 是 v4 老接口且路由不存在。
    """
    return f'{BASE_URL}/api/v4/comment_v5/{kind}/{target_id}/root_comment'


# 回答列表要带回的字段（content 里含正文与图片）
ANSWERS_INCLUDE = ('data[*].content,excerpt,voteup_count,comment_count,created_time,'
                   'updated_time,author.name,author.headline,author.avatar_url,'
                   'author.url_token,question.id')
# 相关问题要带回的字段
SIMILAR_INCLUDE = 'data[*].answer_count,author,follower_count'

# 「网页地址 → ID」用的数字片段；/p/ 是专栏文章的路径（zhuanlan.zhihu.com/p/xxx）
DIGITS_RE = re.compile(r'(\d{6,})')
ARTICLE_PATH_RE = re.compile(r'/p/(\d{6,})')


def _id_of(raw, preferred=None) -> str:
    """从「纯 ID」或「网页地址」里取数字 ID；preferred 用于优先匹配特定路径（如 /p/）"""
    text = (raw or '').strip()
    if not text:
        return ''
    if text.isdigit():
        return text
    matched = (preferred.search(text) if preferred else None) or DIGITS_RE.search(text)
    return matched.group(1) if matched else ''


def question_id_of(raw) -> str:
    """把「问题 ID」或「问题网页地址」归一成问题 ID；取不到返回空串

    例：2089437755591713926 / https://www.zhihu.com/question/2089437755591713926
    """
    return _id_of(raw)


def article_id_of(raw) -> str:
    """把「文章 ID」或「文章网页地址」归一成文章 ID；取不到返回空串

    例：608180793 / https://zhuanlan.zhihu.com/p/608180793
    """
    return _id_of(raw, ARTICLE_PATH_RE)


def extract_images(html_text) -> list:
    """抽出正文 HTML 里的图片地址（去重、保持出现顺序）

    知乎正文的 `<img>` 同时带 `data-original`（原图）与 `src`（可带尺寸后缀的图），
    优先取 `data-original`，没有才退回 `src`。
    """
    if not html_text:
        return []
    urls = []
    for tag in re.findall(r'<img\b[^>]*>', html_text):
        matched = (re.search(r'data-original="([^"]+)"', tag)
                   or re.search(r'\bsrc="([^"]+)"', tag))
        if not matched:
            continue
        url = matched.group(1).strip()
        if url and url not in urls:
            urls.append(url)
    return urls


def web_url(target: dict) -> str:
    """把接口返回的 `target` 转成可点击的网页地址

    热榜里绝大多数是问题（question）；非问题类型尽量按官方域名规则拼，
    拼不出就退回接口自带的 url（形如 https://api.zhihu.com/...）。
    """
    target = target or {}
    target_id = target.get('id')
    target_type = (target.get('type') or '').strip()
    if target_type == 'question' and target_id:
        return question_url(target_id)
    if target_type == 'article' and target_id:
        return f'https://zhuanlan.zhihu.com/p/{target_id}'
    return (target.get('url') or '').strip()
