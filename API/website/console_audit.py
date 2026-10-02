"""超管控制台 · 操作日志

`/console/audit/`：查看超管在控制台做过的**写操作**（谁 / 何时 / 哪个功能 / 什么动作 / 结果 / 从哪来）。

数据由 `admin_auth.superadmin_required` 统一采集（口径见 `API/models/Security/audit.py`），
本页只读：**看日志这个动作本身不产生日志**（审计只看写操作）。

模板提交的动作是 `prompt_delete` 这类技术码，直接展示没人看得懂，故这里统一翻成中文
（见 `ACTION_LABELS`）；未知码原样显示，绝不丢信息。关键词搜索同时匹配中文说法。

筛选与分页与其它控制台列表页同一套骨架（复用 `console_users._page_prefix` 与 `_pagination.html`）。
"""
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import render
from django.utils.translation import gettext as _

from API.models import ConsoleAuditLog

from .admin_auth import superadmin_required
from .console_menu import MENU
from .console_users import _page_prefix

PAGE_SIZE = 50

#: 控制台动作码 -> 人话。新增动作时在这里补一行即可（漏了也只是显示原始码，不影响使用）。
ACTION_LABELS = {
    # 通用
    'create': '新建',
    'edit': '编辑',
    'delete': '删除',
    'delete_bulk': '批量删除',
    'save': '保存',
    'toggle': '启用 / 停用',
    'refresh': '刷新',
    'apply_presets': '一键补齐建议策略',
    # 支付设置
    'save_setting': '保存支付设置',
    'save_provider': '保存支付渠道',
    'sync_order': '手动查单',
    'refund_order': '发起退款',
    'settle_refund': '标记已退款',
    'reject_refund': '驳回退款申请',
    # 用户管理
    'reset_password': '重置登录密码',
    'ban': '封禁',
    'unban': '解封',
    # 问题反馈
    'reply': '回复反馈',
    'review_reply': '审核并回复',
    'resubmit': '重新提交',
    'toggle_public': '公开 / 取消公开',
    'close': '关闭反馈',
    'reopen': '重新打开',
    'contact_save': '保存联系方式',
    'type_create': '新建反馈类型',
    'type_edit': '编辑反馈类型',
    'type_toggle': '启用 / 停用反馈类型',
    'type_delete': '删除反馈类型',
    'platform_create': '新增反馈平台',
    'platform_edit': '编辑反馈平台',
    'platform_toggle': '启用 / 停用反馈平台',
    'platform_delete': '删除反馈平台',
    # AI 审核
    'provider_create': '新建 AI 供应商',
    'provider_edit': '编辑 AI 供应商',
    'provider_toggle': '启用 / 停用 AI 供应商',
    'provider_delete': '删除 AI 供应商',
    'provider_test': '测试 AI 供应商',
    'model_create': '新建 AI 模型',
    'model_edit': '编辑 AI 模型',
    'model_toggle': '启用 / 停用 AI 模型',
    'model_default': '设为默认 AI 模型',
    'model_delete': '删除 AI 模型',
    'prompt_create': '新建提示词',
    'prompt_edit': '编辑提示词',
    'prompt_toggle': '启用 / 停用提示词',
    'prompt_global': '设为全局提示词',
    'prompt_delete': '删除提示词',
}

#: 请求方法 -> 人话（控制台写操作只有这几种）
METHOD_LABELS = {'POST': '提交', 'PUT': '更新', 'PATCH': '更新', 'DELETE': '删除'}


def action_label(action: str) -> str:
    """动作码 -> 中文（未知码原样返回，便于日后新增动作时仍能看出是什么）"""
    action = (action or '').strip()
    label = ACTION_LABELS.get(action)
    return _(label) if label else action


def _menu_labels():
    """URL name -> 菜单里的中文功能名

    直接读侧边栏菜单声明：加一个新控制台页面时，这里自动就有名字，不必再维护第二份对照表。
    菜单没登记的名字（如详情页 `console_user_detail`）原样显示。
    """
    return {item['key']: item['name'] for group in MENU for item in group['items']}


@superadmin_required
def audit_view(request):
    """操作日志列表（只读页）"""
    keyword = (request.GET.get('q') or '').strip()
    operator = (request.GET.get('operator') or '').strip()
    view_name = (request.GET.get('view') or '').strip()

    labels = _menu_labels()
    logs = ConsoleAuditLog.objects.all()
    if operator:
        logs = logs.filter(operator=operator)
    if view_name:
        logs = logs.filter(view_name=view_name)
    if keyword:
        # 中文说法也参与搜索：「删除」应能搜到 delete / prompt_delete / type_delete …
        matched = [code for code, label in ACTION_LABELS.items() if keyword in _(label)]
        cond = Q(path__icontains=keyword) | Q(note__icontains=keyword) \
            | Q(action__icontains=keyword) | Q(target__icontains=keyword)
        if matched:
            cond |= Q(action__in=matched)
        logs = logs.filter(cond)

    paginator = Paginator(logs, PAGE_SIZE)
    page = paginator.get_page(request.GET.get('page'))
    # 给每行补上「功能」的中文名与「动作」「结果」的人话（模板里不做查表）
    for log in page.object_list:
        log.view_label = labels.get(log.view_name) or log.view_name or ''
        log.action_label = action_label(log.action)
        log.method_label = _(METHOD_LABELS.get((log.method or '').upper(), log.method or ''))
        log.result_label = _('成功') if (log.status_code or 0) < 400 else _('失败')

    return render(request, 'console/audit.html', {
        'page_obj': page,
        'paginator': paginator,
        'total': paginator.count,
        'keyword': keyword,
        'operator_filter': operator,
        'view_filter': view_name,
        'page_prefix': _page_prefix(request),
        # 下拉只列出现过的取值：日志多了以后仍然好用，也不会给出一堆空结果
        'operator_options': (ConsoleAuditLog.objects.exclude(operator='')
                             .values_list('operator', flat=True).distinct().order_by('operator')),
        'view_options': [{'value': name, 'label': labels.get(name) or name}
                         for name in (ConsoleAuditLog.objects.exclude(view_name='')
                                      .values_list('view_name', flat=True).distinct().order_by('view_name'))],
    })
