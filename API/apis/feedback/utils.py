"""问题反馈中心 - 业务逻辑

功能：
    create_feedback    - 提交反馈（需签名 + 用户 Token 真实性校验）
    create_reply       - 追加/回复评论（需签名 + 用户 Token 真实性校验，支持无限嵌套）
    list_feedbacks     - 项目内反馈列表（分页 + 状态筛选）
    get_feedback_detail - 反馈详情 + 评论树（一级分页，每条一级内嵌二级评论首页）
    list_replies       - 某条评论的二级评论列表（分页，返回其全部子孙，不分层级）

数据隔离：所有查询以 app（签名确定的接入项目）为租户维度，
子项目只能看到自己项目的反馈，子项目之间互不可见。

身份校验：create / reply 复用用户中心 verify_token 校验用户 Token，
反馈人身份以校验结果中的 user_id 为准，子项目无法伪造用户 ID。
（verify_token 校验 Token 属于当前项目、未过期、用户与项目均启用）

所有函数返回 (success, data_or_msg) 二元组。
"""
from django.db.models import Count

from API.apis.user_center.users.utils import verify_token
from API.models import Feedback, FeedbackReply

# 标题长度上限
TITLE_MAX_LEN = 100

# 列表单页条数上限（防一次拉取过多数据）
PAGE_SIZE_MAX = 100

# 追加列表默认每页条数（单条反馈的追加可能成千上万，必须分页）
REPLY_DEFAULT_PAGE_SIZE = 20

# 详情接口中每条一级评论内嵌的二级首页条数（防止某条一级评论下海量回复撑爆响应）
SUB_REPLY_FIRST_PAGE_SIZE = 5


def _require_user(app, token):
    """校验用户 Token 真实性，返回 (True, user_info) 或 (False, err_msg)

    复用用户中心 verify_token：Token 须属于当前项目（app_id）且有效，
    返回的用户信息即为真实用户身份。
    """
    ok, data = verify_token(app, token)
    if not ok:
        return False, data
    return True, data


def create_feedback(app, token, title, content):
    """提交反馈

    :param app: 接入项目（签名确定，即租户）
    :param token: 用户登录 Token（校验真实性，确定反馈人）
    :return: (True, {feedback_id, status}) 或 (False, err_msg)
    """
    title = (title or '').strip()
    content = (content or '').strip()

    if not title:
        return False, '参数缺失: title(标题)'
    if len(title) > TITLE_MAX_LEN:
        return False, f'参数格式错误: title 长度不能超过 {TITLE_MAX_LEN} 字符'
    if not content:
        return False, '参数缺失: content(内容)'

    ok, user = _require_user(app, token)
    if not ok:
        return False, user

    try:
        fb = Feedback.objects.create(
            app=app, user_id=user['user_id'],
            title=title, content=content, status='pending',
        )
    except Exception as e:
        return False, f'提交反馈失败: {e}'
    return True, {'feedback_id': str(fb.id), 'status': fb.status}


def create_reply(app, token, feedback_id, content, parent_id=''):
    """追加评论 / 回复评论（支持无限嵌套）

    评论结构：parent 为空=一级评论；parent 非空=回复某条评论（可回复任意层级，
    不限制嵌套深度）。同一反馈下所有评论全部人可见（项目内公开）。

    :param parent_id: 可选，被回复的评论 ID（须属于当前反馈）
    :return: (True, {reply_id}) 或 (False, err_msg)
    """
    feedback_id = (feedback_id or '').strip()
    content = (content or '').strip()
    parent_id = (parent_id or '').strip()

    if not feedback_id:
        return False, '参数缺失: feedback_id(反馈ID)'
    if not content:
        return False, '参数缺失: content(追加内容)'

    ok, user = _require_user(app, token)
    if not ok:
        return False, user

    try:
        fb = Feedback.objects.get(pk=feedback_id, app=app)
    except Feedback.DoesNotExist:
        return False, '反馈不存在或不属于当前项目'
    except Exception as e:
        return False, f'查询反馈失败: {e}'

    # 校验父评论（可选）：须存在且属于当前反馈（反馈已按项目隔离，故父评论必属当前项目）
    parent = None
    if parent_id:
        try:
            parent = FeedbackReply.objects.get(pk=parent_id, feedback=fb)
        except FeedbackReply.DoesNotExist:
            return False, '父评论不存在或不属于当前反馈'
        except Exception as e:
            return False, f'查询父评论失败: {e}'

    try:
        reply = FeedbackReply.objects.create(
            feedback=fb, parent=parent, user_id=user['user_id'],
            author_role='user', content=content,
        )
    except Exception as e:
        return False, f'追加失败: {e}'
    return True, {'reply_id': str(reply.id)}


def list_feedbacks(app, status='', page=1, page_size=10):
    """项目内反馈列表（分页 + 状态筛选，按创建时间倒序）

    :param status: 状态筛选（pending/processing/resolved/closed，空=全部）
    :return: (True, {total, page, page_size, total_pages, items}) 或 (False, err_msg)

    性能：用 annotate 一次聚合追加数，避免每条反馈单独 count 的 N+1 查询。
    """
    qs = Feedback.objects.filter(app=app).select_related('user')
    if status in dict(Feedback.STATUS_CHOICES):
        qs = qs.filter(status=status)
    # 追加数聚合（别名 _reply_count，避免与模型 property reply_count 冲突）
    qs = qs.annotate(_reply_count=Count('replies'))

    try:
        page = max(int(page or 1), 1)
        page_size = min(max(int(page_size or 10), 1), PAGE_SIZE_MAX)
    except (ValueError, TypeError):
        page, page_size = 1, 10

    total = qs.count()
    total_pages = (total + page_size - 1) // page_size
    items = list(qs.order_by('-create_time')[(page - 1) * page_size: page * page_size])

    data = {
        'total': total,
        'page': page,
        'page_size': page_size,
        'total_pages': total_pages,
        'items': [
            {
                'feedback_id': str(fb.id),
                'title': fb.title,
                'status': fb.status,
                'username': fb.user.username,
                'reply_count': fb._reply_count,
                'create_time': fb.create_time.strftime('%Y-%m-%d %H:%M:%S'),
            }
            for fb in items
        ],
    }
    return True, data


def _serialize_reply(reply):
    """序列化单条评论（含空 replies 容器，建树时填充）

    - parent_id: 该评论回复的父评论 ID（空=一级评论，即直接评论问题）
    - children_total: 直接子回复数（直接回复本条评论的条数）
    - reply_total: 二级评论总数（本条评论下的全部子孙回复数，含任意嵌套层级）

    评论语义：一级评论=直接评论问题的评论（parent 为空）；二级评论=所有回复在别人
    评论底下的评论，**无论嵌套多深**（B 回复 A、C 回复 B、D 回复 C……全部算二级评论）。
    """
    return {
        'reply_id': str(reply.id),
        'parent_id': str(reply.parent_id) if reply.parent_id else '',
        'author_role': reply.author_role,
        'username': reply.user.username if reply.user else '站长',
        'content': reply.content,
        'create_time': reply.create_time.strftime('%Y-%m-%d %H:%M:%S'),
        'reply_total': 0,      # 二级评论总数（全部子孙回复数，逆序累加得出）
        'children_total': 0,   # 直接子回复数（直接回复本条评论的条数）
        'replies': [],         # 内嵌的二级评论（详情接口为全部子孙首页，翻页见 list_replies）
    }


def _build_tree(all_replies):
    """把一次查询的评论列表组装为评论树

    返回 (roots, nodes)：
        roots - 一级评论节点（parent 为空，按时间正序）
        nodes - {reply_id: 节点}，节点含 reply_total（二级评论总数=全部子孙数）
                与 children_total（直接子回复数）

    实现：内存建树（无逐层 N+1 查询），逆序累加子孙总数（无 Python 递归深度限制）。
    """
    nodes = {r.id: _serialize_reply(r) for r in all_replies}
    roots = []
    for r in all_replies:
        node = nodes[r.id]
        if r.parent_id is None:
            roots.append(node)
        else:
            parent = nodes.get(r.parent_id)
            if parent is not None:
                parent['replies'].append(node)
                parent['children_total'] += 1

    # 逆序累加子孙总数（子节点先处理完，父节点再累加），避免递归
    for r in reversed(all_replies):
        node = nodes[r.id]
        if r.parent_id is not None:
            parent = nodes.get(r.parent_id)
            if parent is not None:
                parent['reply_total'] += 1 + node['reply_total']
    return roots, nodes


def _collect_descendants(all_replies, nodes, target_id):
    """按时间正序收集 target_id（可为任意层级评论）的全部子孙节点（扁平列表）

    语义：二级评论=所有回复在别人评论底下的评论（无论嵌套多深），
    因此"某条评论的二级评论"即其**全部子孙回复**，B、C、D……（无论多深）都算。
    all_replies 已按 create_time 正序，故收集顺序即时间顺序（翻页连续）；
    沿 parent 链上溯归属判断，无递归、无逐层查询。

    :param target_id: 目标评论 ID（UUID 字符串，与序列化字段 reply_id 一致）
    """
    parent_map = {str(r.id): (str(r.parent_id) if r.parent_id else None)
                  for r in all_replies}
    descendants = []
    for r in all_replies:
        if r.parent_id is None:
            continue
        cur = str(r.parent_id)
        while cur is not None and cur != target_id:
            cur = parent_map.get(cur)
        if cur == target_id:
            descendants.append(nodes[r.id])
    return descendants


def _pagination(page, page_size, default_size):
    """分页参数归一化：任一参数非法则整体回退默认值"""
    try:
        page = max(int(page or 1), 1)
        page_size = min(max(int(page_size or default_size), 1), PAGE_SIZE_MAX)
    except (ValueError, TypeError):
        page, page_size = 1, default_size
    return page, page_size


def get_feedback_detail(app, feedback_id, page=1, page_size=REPLY_DEFAULT_PAGE_SIZE):
    """反馈详情 + 评论树（一级分页，每条一级内嵌二级评论首页）

    评论语义：一级评论=直接评论问题的评论（parent 为空）；二级评论=所有回复在别人
    评论底下的评论，**无论嵌套多深**（B 回复 A、C 回复 B、D 回复 C……全部算二级评论）。
    实现上**一次查询**拉取该反馈全部评论，在内存组装评论树（避免逐层查询的 N+1
    与 Python 递归深度限制）。
    分页策略（防海量评论撑爆响应）：
    - **一级评论**按 page/page_size 分页返回（正序，查看最新请翻到最后一页）
    - 每条一级评论内嵌**二级评论首页**（SUB_REPLY_FIRST_PAGE_SIZE 条），取该一级
      评论**全部子孙**中按时间正序的前 N 条（与 list_replies 翻页列表连续一致，
      深层回复如 C、D 也会出现在首页）
    - 每条评论带 parent_id（标明回复了谁）、children_total（直接子回复数）、
      reply_total（二级评论总数=全部子孙数）
    - 内嵌的二级评论不再递归嵌套（replies 为空数组）；更多二级评论通过
      list_replies 接口按 parent_id 翻页获取

    :param page: 一级评论页码（默认 1）
    :param page_size: 每页条数（默认 20，最大 100）
    :return: (True, {feedback_id, title, content, status, username, create_time,
                     total, page, page_size, total_pages, replies}) 或 (False, err_msg)
    """
    feedback_id = (feedback_id or '').strip()
    if not feedback_id:
        return False, '参数缺失: feedback_id(反馈ID)'

    try:
        fb = Feedback.objects.select_related('user').get(pk=feedback_id, app=app)
    except Feedback.DoesNotExist:
        return False, '反馈不存在或不属于当前项目'
    except Exception as e:
        return False, f'查询反馈失败: {e}'

    page, page_size = _pagination(page, page_size, REPLY_DEFAULT_PAGE_SIZE)

    # 一次查询拉取该反馈全部评论（含 user），按创建时间正序，内存建树
    all_replies = list(fb.replies.select_related('user').order_by('create_time'))
    roots, nodes = _build_tree(all_replies)

    # 一级评论分页（roots 已按创建时间正序）
    total = len(roots)
    total_pages = (total + page_size - 1) // page_size
    page_replies = roots[(page - 1) * page_size: page * page_size]

    # 每条一级评论内嵌"二级评论首页"：全部子孙按时间正序前 N 条，且不再递归嵌套
    for root in page_replies:
        root['replies'] = _collect_descendants(all_replies, nodes, root['reply_id'])[:SUB_REPLY_FIRST_PAGE_SIZE]
        for sub in root['replies']:
            sub['replies'] = []

    data = {
        'feedback_id': str(fb.id),
        'title': fb.title,
        'content': fb.content,
        'status': fb.status,
        'username': fb.user.username,
        'create_time': fb.create_time.strftime('%Y-%m-%d %H:%M:%S'),
        'total': total,
        'page': page,
        'page_size': page_size,
        'total_pages': total_pages,
        'replies': page_replies,
    }
    return True, data


def list_replies(app, feedback_id, parent_id, page=1, page_size=REPLY_DEFAULT_PAGE_SIZE):
    """某条评论的二级评论列表（分页）

    语义：二级评论=所有回复在别人评论底下的评论，**无论嵌套多深**。
    因此本接口返回 parent 的**全部子孙回复**（扁平列表，按时间正序分页），
    B、C、D……（无论多深）全部返回，概念上不再区分三级/N级。
    每条回复带 parent_id 标明它回复了谁，便于前端展示"谁回复了谁"。

    :param feedback_id: 反馈 ID（须属于当前项目）
    :param parent_id: 被查看的评论 ID（须属于该反馈，可为任意层级）
    :param page: 页码（默认 1）
    :param page_size: 每页条数（默认 20，最大 100）
    :return: (True, {parent_id, total, page, page_size, total_pages, items}) 或 (False, err_msg)
    """
    feedback_id = (feedback_id or '').strip()
    parent_id = (parent_id or '').strip()
    if not feedback_id:
        return False, '参数缺失: feedback_id(反馈ID)'
    if not parent_id:
        return False, '参数缺失: parent_id(评论ID)'

    try:
        fb = Feedback.objects.get(pk=feedback_id, app=app)
    except Feedback.DoesNotExist:
        return False, '反馈不存在或不属于当前项目'
    except Exception as e:
        return False, f'查询反馈失败: {e}'

    try:
        parent = FeedbackReply.objects.get(pk=parent_id, feedback=fb)
    except FeedbackReply.DoesNotExist:
        return False, '父评论不存在或不属于当前反馈'
    except Exception as e:
        return False, f'查询父评论失败: {e}'

    page, page_size = _pagination(page, page_size, REPLY_DEFAULT_PAGE_SIZE)

    # 一次查询该反馈全部评论，在内存筛出 parent 的全部子孙（按时间正序）
    all_replies = list(fb.replies.select_related('user').order_by('create_time'))
    nodes = {r.id: _serialize_reply(r) for r in all_replies}
    descendants = _collect_descendants(all_replies, nodes, str(parent.id))

    total = len(descendants)
    total_pages = (total + page_size - 1) // page_size
    items = descendants[(page - 1) * page_size: page * page_size]

    data = {
        'parent_id': str(parent.id),
        'total': total,
        'page': page,
        'page_size': page_size,
        'total_pages': total_pages,
        'items': items,
    }
    return True, data
