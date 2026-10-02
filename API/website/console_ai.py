"""超管控制台 · AI 厂商 / 模型 / 系统提示词管理

一页三区（厂商 / 模型 / 系统提示词），是 AI 服务的唯一维护入口：
    /console/ai/models/     厂商、模型、系统提示词的增删改查与启停、默认模型、连通性测试

为什么 Key 在这里维护而不是 .env：见 API/models/AI/provider.py 顶部说明。
页面**永不回显 Key 原文**：列表只显示保存时生成的掩码（如 sk-…4fe2）；
编辑时密钥框留空表示「不修改」，要清空则勾选「清除已配置的 Key」。

系统提示词与采样参数（温度 / 最大长度 / 停止词）都在这里按模型维护，
**调用方不能自定义**（请求里传了会被拒绝），避免对外行为被逐步改得不可控。

鉴权：仅 Django is_superuser（见 admin_auth.superadmin_required）。
"""
import re

from django.contrib import messages
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _

from API.apis.ai.BuiltInModel import utils as ai_utils
from API.models import AiModel, AiProvider, AiSystemPrompt

from .admin_auth import notify_success, superadmin_required

# 厂商标识：英文小写 + 数字，允许 - 与 _
_CODE_RE = re.compile(r'^[a-z0-9][a-z0-9_-]*$')
# 模型标识：允许大小写与 . - _（对齐各家上游的模型名写法，如 qwen-max、glm-4.5）
_MODEL_KEY_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._-]*$')

_MAX_CODE_LEN = 30
_MAX_MODEL_KEY_LEN = 60
_MAX_BASE_URL_LEN = 200
_MAX_IMAGES_LIMIT = 20
"""「最多图片数」的上限（视觉模型单次请求最多可携带的图片张数）"""


@superadmin_required
def ai_models_view(request):
    """AI 厂商 / 模型 / 系统提示词管理：GET 渲染列表；POST 处理各种动作"""
    if request.method == 'POST':
        return _handle_post(request)
    return render(request, 'console/ai_models.html', {
        'providers': AiProvider.objects.all(),
        'models': AiModel.objects.select_related('provider', 'system_prompt').all(),
        'prompts': AiSystemPrompt.objects.all(),
        'prompt_modes': AiModel.PromptMode.choices,
    })


# ==================== 取对象 ====================
def _provider_or_none(raw_id):
    raw = str(raw_id or '').strip()
    return AiProvider.objects.filter(pk=raw).first() if raw.isdigit() else None


def _model_or_none(raw_id):
    raw = str(raw_id or '').strip()
    return AiModel.objects.filter(pk=raw).first() if raw.isdigit() else None


def _prompt_or_none(raw_id):
    raw = str(raw_id or '').strip()
    return AiSystemPrompt.objects.filter(pk=raw).first() if raw.isdigit() else None


def _redirect():
    return redirect('website:console_ai_models')


# ==================== 厂商表单 ====================
def _provider_form_data(request, provider=None):
    """读取并校验厂商表单，返回 (data, error)

    :param provider: 编辑时传入既有对象（用于「Key 留空=不修改」与标识唯一性排除自身）
    """
    code = (request.POST.get('code') or '').strip().lower()
    name = (request.POST.get('name') or '').strip()
    base_url = (request.POST.get('base_url') or '').strip().rstrip('/')
    api_key = (request.POST.get('api_key') or '').strip()
    clear_key = request.POST.get('clear_key') == '1'
    remark = (request.POST.get('remark') or '').strip()

    if not name:
        return None, _('请填写厂商名称')
    if not code:
        return None, _('请填写厂商标识')
    if len(code) > _MAX_CODE_LEN or not _CODE_RE.match(code):
        return None, _('厂商标识只能是小写字母、数字、短横线与下划线，且以字母或数字开头')
    if not base_url:
        return None, _('请填写上游根地址')
    if len(base_url) > _MAX_BASE_URL_LEN or not base_url.startswith(('http://', 'https://')):
        return None, _('上游根地址必须以 http:// 或 https:// 开头，且不超过 200 个字符')

    duplicated = AiProvider.objects.filter(code=code)
    if provider is not None:
        duplicated = duplicated.exclude(pk=provider.pk)
    if duplicated.exists():
        return None, _('该厂商标识已存在，请更换')

    raw_sort = (request.POST.get('sort') or '').strip()
    try:
        sort = int(raw_sort) if raw_sort else 0
    except ValueError:
        return None, _('排序必须为整数')

    return {
        'code': code,
        'name': name,
        'base_url': base_url,
        'api_key': api_key,          # 空字符串 = 不修改（由调用方决定）
        'clear_key': clear_key,
        'enabled': request.POST.get('enabled') == '1',
        'sort': sort,
        'remark': remark,
    }, None


def _apply_provider(data, provider):
    """把校验后的表单值应用到实例（含 Key 的三态处理：留空不改 / 覆盖 / 清除）"""
    provider.code = data['code']
    provider.name = data['name']
    provider.base_url = data['base_url']
    provider.enabled = data['enabled']
    provider.sort = data['sort']
    provider.remark = data['remark']
    if data['clear_key']:
        provider.set_api_key('')
    elif data['api_key']:
        provider.set_api_key(data['api_key'])


def _provider_create(request):
    data, error = _provider_form_data(request)
    if error:
        messages.error(request, error)
        return _redirect()
    provider = AiProvider()
    _apply_provider(data, provider)
    provider.save()
    notify_success(request, _('厂商「%(name)s」已创建') % {'name': provider.name})
    return _redirect()


def _provider_edit(request, provider):
    data, error = _provider_form_data(request, provider)
    if error:
        messages.error(request, error)
        return _redirect()
    _apply_provider(data, provider)
    provider.save()
    notify_success(request, _('厂商「%(name)s」已保存') % {'name': provider.name})
    return _redirect()


def _provider_toggle(request, provider):
    provider.enabled = not provider.enabled
    provider.save(update_fields=['enabled', 'updated_time'])
    notify_success(request, _('厂商「%(name)s」已启用') % {'name': provider.name}
                     if provider.enabled
                     else _('厂商「%(name)s」已停用，其下所有模型立即不可用') % {'name': provider.name})
    return _redirect()


def _provider_delete(request, provider):
    name = provider.name
    provider.delete()          # 其下模型随外键级联删除
    notify_success(request, _('厂商「%(name)s」及其模型已删除') % {'name': name})
    return _redirect()


def _provider_test(request, provider):
    """连通性测试：用该厂商的地址与 Key 发一条极短请求，当场验证配置是否可用"""
    ok, detail = ai_utils.test_provider(provider)
    if ok:
        notify_success(request, _('连通性测试通过：%(detail)s') % {'detail': detail})
    else:
        messages.error(request, _('连通性测试失败：%(detail)s') % {'detail': detail})
    return _redirect()


# ==================== 模型表单 ====================
def _model_form_data(request, model=None):
    """读取并校验模型表单，返回 (data, error)"""
    key = (request.POST.get('key') or '').strip()
    name = (request.POST.get('name') or '').strip()
    upstream_name = (request.POST.get('upstream_name') or '').strip()
    provider = _provider_or_none(request.POST.get('provider'))
    remark = (request.POST.get('remark') or '').strip()

    if not key:
        return None, _('请填写模型标识')
    if len(key) > _MAX_MODEL_KEY_LEN or not _MODEL_KEY_RE.match(key):
        return None, _('模型标识只能是字母、数字、点、短横线与下划线，且以字母或数字开头')
    if not name:
        return None, _('请填写模型名称')
    if provider is None:
        return None, _('请选择所属厂商')

    duplicated = AiModel.objects.filter(key=key)
    if model is not None:
        duplicated = duplicated.exclude(pk=model.pk)
    if duplicated.exists():
        return None, _('该模型标识已存在，请更换')

    raw_sort = (request.POST.get('sort') or '').strip()
    try:
        sort = int(raw_sort) if raw_sort else 0
    except ValueError:
        return None, _('排序必须为整数')

    raw_window = (request.POST.get('context_window') or '').strip()
    context_window = None
    if raw_window:
        if not raw_window.isdigit():
            return None, _('上下文长度必须为数字（留空表示不填）')
        context_window = int(raw_window)

    # 系统提示词：一个下拉覆盖三态（inherit / none / prompt:<pk>）
    prompt_mode, prompt, error = _parse_prompt_choice(request.POST.get('prompt_choice'))
    if error:
        return None, error

    # 采样参数：留空=不下发该参数（由上游默认值决定）；调用方无法覆盖
    raw_temp = (request.POST.get('temperature') or '').strip()
    temperature = None
    if raw_temp:
        try:
            temperature = float(raw_temp)
        except ValueError:
            return None, _('采样温度必须为数字（留空表示不设置）')
        if not 0 <= temperature <= 2:
            return None, _('采样温度取值范围为 0 ~ 2')

    raw_max = (request.POST.get('max_tokens') or '').strip()
    max_tokens = None
    if raw_max:
        if not raw_max.isdigit() or not 1 <= int(raw_max) <= 32768:
            return None, _('最大回复长度取值范围为 1 ~ 32768（留空表示不设置）')
        max_tokens = int(raw_max)

    raw_images = (request.POST.get('max_images') or '').strip()
    if not raw_images.isdigit() or not 1 <= int(raw_images) <= _MAX_IMAGES_LIMIT:
        return None, _('最多图片数取值范围为 1 ~ %(limit)s') % {'limit': _MAX_IMAGES_LIMIT}
    max_images = int(raw_images)

    stop = (request.POST.get('stop') or '').strip()
    if len(stop) > 255:
        return None, _('停止词过长，请控制在 255 个字符以内')

    return {
        'key': key,
        'name': name,
        'provider': provider,
        'upstream_name': upstream_name,
        'supports_vision': request.POST.get('supports_vision') == '1',
        'max_images': max_images,
        'context_window': context_window,
        'prompt_mode': prompt_mode,
        'system_prompt': prompt,
        'temperature': temperature,
        'max_tokens': max_tokens,
        'stop': stop,
        'sort': sort,
        'enabled': request.POST.get('enabled') == '1',
        'is_default': request.POST.get('is_default') == '1',
        'remark': remark,
    }, None


def _parse_prompt_choice(raw):
    """解析模型表单里的系统提示词选择

    一个下拉覆盖三态：`inherit`（跟随全局共享）/ `none`（不使用）/ `prompt:<pk>`（指定某条）。
    取不到的选择一律按「跟随全局」处理，不让被篡改的表单值把模型弄成半配置状态。

    :return: (prompt_mode, prompt_obj|None, error)
    """
    choice = (raw or '').strip()
    if choice == AiModel.PromptMode.NONE:
        return AiModel.PromptMode.NONE, None, None
    if choice.startswith('prompt:'):
        prompt = _prompt_or_none(choice.split(':', 1)[1])
        if prompt is None:
            return None, None, _('选择的系统提示词不存在，请重新选择')
        return AiModel.PromptMode.CUSTOM, prompt, None
    return AiModel.PromptMode.INHERIT, None, None


def _apply_model(data, model):
    """把校验后的表单值应用到实例；勾选「默认模型」时清掉其它模型的默认标记"""
    if data['is_default']:
        AiModel.objects.filter(is_default=True).exclude(pk=model.pk).update(is_default=False)
    model.key = data['key']
    model.name = data['name']
    model.provider = data['provider']
    model.upstream_name = data['upstream_name']
    model.supports_vision = data['supports_vision']
    model.max_images = data['max_images']
    model.context_window = data['context_window']
    model.prompt_mode = data['prompt_mode']
    model.system_prompt = data['system_prompt']
    model.temperature = data['temperature']
    model.max_tokens = data['max_tokens']
    model.stop = data['stop']
    model.sort = data['sort']
    model.enabled = data['enabled']
    model.is_default = data['is_default']
    model.remark = data['remark']


def _model_create(request):
    data, error = _model_form_data(request)
    if error:
        messages.error(request, error)
        return _redirect()
    model = AiModel()
    _apply_model(data, model)
    model.save()
    notify_success(request, _('模型「%(name)s」已创建') % {'name': model.name})
    return _redirect()


def _model_edit(request, model):
    data, error = _model_form_data(request, model)
    if error:
        messages.error(request, error)
        return _redirect()
    _apply_model(data, model)
    model.save()
    notify_success(request, _('模型「%(name)s」已保存') % {'name': model.name})
    return _redirect()


def _model_toggle(request, model):
    model.enabled = not model.enabled
    model.save(update_fields=['enabled', 'updated_time'])
    notify_success(request, _('模型「%(name)s」已上架') % {'name': model.name}
                     if model.enabled
                     else _('模型「%(name)s」已下架') % {'name': model.name})
    return _redirect()


def _model_set_default(request, model):
    if not model.enabled:
        messages.error(request, _('模型「%(name)s」未上架，不能设为默认') % {'name': model.name})
        return _redirect()
    AiModel.objects.filter(is_default=True).exclude(pk=model.pk).update(is_default=False)
    model.is_default = True
    model.save(update_fields=['is_default', 'updated_time'])
    notify_success(request, _('已把「%(name)s」设为默认模型') % {'name': model.name})
    return _redirect()


def _model_delete(request, model):
    name = model.name
    model.delete()
    notify_success(request, _('模型「%(name)s」已删除') % {'name': name})
    return _redirect()


# ==================== 系统提示词 ====================
def _prompt_form_data(request):
    """读取并校验系统提示词表单，返回 (data, error)"""
    name = (request.POST.get('name') or '').strip()
    content = (request.POST.get('content') or '').strip()
    if not name:
        return None, _('请填写提示词名称')
    if not content:
        return None, _('请填写提示词正文')

    raw_sort = (request.POST.get('sort') or '').strip()
    try:
        sort = int(raw_sort) if raw_sort else 0
    except ValueError:
        return None, _('排序必须为整数')

    return {
        'name': name,
        'content': content,
        'is_global': request.POST.get('is_global') == '1',
        'enabled': request.POST.get('enabled') == '1',
        'sort': sort,
        'remark': (request.POST.get('remark') or '').strip(),
    }, None


def _apply_prompt(data, prompt):
    """把校验后的表单值应用到实例；勾选「全局共享」时清掉其它记录的该标记"""
    if data['is_global']:
        AiSystemPrompt.objects.filter(is_global=True).exclude(pk=prompt.pk).update(is_global=False)
    prompt.name = data['name']
    prompt.content = data['content']
    prompt.is_global = data['is_global']
    prompt.enabled = data['enabled']
    prompt.sort = data['sort']
    prompt.remark = data['remark']


def _prompt_create(request):
    data, error = _prompt_form_data(request)
    if error:
        messages.error(request, error)
        return _redirect()
    prompt = AiSystemPrompt()
    _apply_prompt(data, prompt)
    prompt.save()
    notify_success(request, _('系统提示词「%(name)s」已创建') % {'name': prompt.name})
    return _redirect()


def _prompt_edit(request, prompt):
    data, error = _prompt_form_data(request)
    if error:
        messages.error(request, error)
        return _redirect()
    _apply_prompt(data, prompt)
    prompt.save()
    notify_success(request, _('系统提示词「%(name)s」已保存') % {'name': prompt.name})
    return _redirect()


def _prompt_toggle(request, prompt):
    prompt.enabled = not prompt.enabled
    prompt.save(update_fields=['enabled', 'updated_time'])
    notify_success(request, _('系统提示词「%(name)s」已启用') % {'name': prompt.name}
                     if prompt.enabled
                     else _('系统提示词「%(name)s」已停用，停用期间视同不存在') % {'name': prompt.name})
    return _redirect()


def _prompt_set_global(request, prompt):
    """设为全局共享（全库只保留一条：所有「跟随全局」的模型都用它）"""
    AiSystemPrompt.objects.filter(is_global=True).exclude(pk=prompt.pk).update(is_global=False)
    prompt.is_global = True
    prompt.save(update_fields=['is_global', 'updated_time'])
    notify_success(request, _('已把「%(name)s」设为全局共享提示词') % {'name': prompt.name})
    return _redirect()


def _prompt_delete(request, prompt):
    name = prompt.name
    prompt.delete()            # 引用它的模型外键置空 → 自动回落到全局共享那条
    notify_success(request, _('系统提示词「%(name)s」已删除') % {'name': name})
    return _redirect()


# ==================== 动作分发 ====================
# 新建动作：表单里不需要先取对象，直接调用
_CREATE_ACTIONS = {
    'provider_create': _provider_create,
    'model_create': _model_create,
    'prompt_create': _prompt_create,
}
# 需要先取到对象才能执行的动作
_PROVIDER_ACTIONS = {
    'provider_edit': _provider_edit,
    'provider_toggle': _provider_toggle,
    'provider_delete': _provider_delete,
    'provider_test': _provider_test,
}
_MODEL_ACTIONS = {
    'model_edit': _model_edit,
    'model_toggle': _model_toggle,
    'model_default': _model_set_default,
    'model_delete': _model_delete,
}
_PROMPT_ACTIONS = {
    'prompt_edit': _prompt_edit,
    'prompt_toggle': _prompt_toggle,
    'prompt_global': _prompt_set_global,
    'prompt_delete': _prompt_delete,
}
# 页面表单允许提交的全部动作名（模板自检 / 回归脚本引用，避免弹窗里的 value 与分发脱节）
ACTIONS = (frozenset(_CREATE_ACTIONS) | frozenset(_PROVIDER_ACTIONS)
           | frozenset(_MODEL_ACTIONS) | frozenset(_PROMPT_ACTIONS))


def _handle_post(request):
    action = (request.POST.get('action') or '').strip()

    if action in _CREATE_ACTIONS:
        return _CREATE_ACTIONS[action](request)

    if action in _PROVIDER_ACTIONS:
        provider = _provider_or_none(request.POST.get('id'))
        if provider is None:
            messages.error(request, _('厂商不存在'))
            return _redirect()
        return _PROVIDER_ACTIONS[action](request, provider)

    if action in _MODEL_ACTIONS:
        model = _model_or_none(request.POST.get('id'))
        if model is None:
            messages.error(request, _('模型不存在'))
            return _redirect()
        return _MODEL_ACTIONS[action](request, model)

    if action in _PROMPT_ACTIONS:
        prompt = _prompt_or_none(request.POST.get('id'))
        if prompt is None:
            messages.error(request, _('系统提示词不存在'))
            return _redirect()
        return _PROMPT_ACTIONS[action](request, prompt)

    messages.error(request, _('不支持的操作'))
    return _redirect()
