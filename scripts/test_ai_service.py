"""AI 服务回归脚本（模型注册表 / 统一对话 / 后台管理页）

覆盖范围：
    A. 业务层 utils：模型清单、目标解析、images 校验与多模态消息、能力拦截
    B. 视图层：参数校验与状态码约定（直接调视图，绕过中间件）
    C. 后台页 /console/ai/models/：厂商与模型的增删改查、Key 加密与掩码、缓存即时失效
    D. 真实上游调用：仅当库里的平台 Key 被上游接受时才执行（Key 由后台维护，不再读 .env）

用法：
    .venv\\Scripts\\python.exe scripts\\test_ai_service.py

说明：脚本会自动创建临时厂商 / 模型并在结束时清理；若本机没有超管账号，
会临时建一个并在结束时删除。D 段依赖有效密钥，无有效密钥时自动跳过（记为 SKIP）。
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'XiaoYingAPI.settings')

import django  # noqa: E402

django.setup()

import requests                                          # noqa: E402
from django.contrib.auth import get_user_model           # noqa: E402
from django.db import connection                         # noqa: E402
from django.test import Client, RequestFactory           # noqa: E402

from API.apis.ai.BuiltInModel import request as ai_request, utils  # noqa: E402
from API.models import AiModel, AiProvider, AiSystemPrompt       # noqa: E402
from API.website import console_ai                       # noqa: E402

PASS = FAIL = SKIP = 0
TEST_VENDOR = 'ai_regress_vendor'
TEST_MODEL = 'ai-regress-model'
PROMPT_VENDOR = 'ai_regress_prompt_vendor'
PROMPT_MODEL = 'ai-regress-prompt-model'
# 本脚本创建的临时系统提示词一律用这个前缀命名，便于异常中断后自愈清理
PROMPT_PREFIX = '回归'
IMG = 'https://www.baidu.com/img/PCtm_d9c8750bed0b3c7d089fa7d55720d6cf.png'


def check(name, ok, extra=''):
    global PASS, FAIL
    if ok:
        PASS += 1
        print('PASS', name)
    else:
        FAIL += 1
        print('FAIL', name, extra)


def skip(name, why):
    global SKIP
    SKIP += 1
    print('SKIP', name, '—', why)


def body(resp):
    return json.loads(resp.content.decode('utf-8'))


def post_chat(data):
    return body(ai_request.chat_view(RequestFactory().post('/api/ai/BuiltInModel/chat', data)))


# ==================== 清理 & 前置 ====================
def cleanup():
    """清掉本脚本可能留下的临时数据，并把默认模型复位到 deepseek-v4-flash

    开头与结尾各调用一次：开头那次是为了让上一次异常中断的残留不会让本次跑挂。
    """
    AiProvider.objects.filter(code__in=[TEST_VENDOR, PROMPT_VENDOR]).delete()
    AiModel.objects.filter(key__in=[TEST_MODEL, PROMPT_MODEL]).delete()
    AiSystemPrompt.objects.filter(name__startswith=PROMPT_PREFIX).delete()
    if not AiModel.objects.filter(is_default=True).exists():
        first = AiModel.objects.filter(key='deepseek-v4-flash').first()
        if first:
            first.is_default = True
            first.save(update_fields=['is_default', 'updated_time'])


cleanup()

# ==================== A. 业务层 ====================
models = utils.public_models()
check('模型清单来自数据库', len(models) >= 2, len(models))
check('清单字段为白名单（不含 url/vendor/api_key/provider_id）',
      all(set(m) == {'model', 'name', 'supports_vision', 'context_window', 'is_default'}
          for m in models))
check('默认模型为 deepseek-v4-flash',
      next((m['model'] for m in models if m['is_default']), None) == 'deepseek-v4-flash')

target, err = utils.resolve_target()
check('不传 model 取默认模型', err is None and target['key'] == 'deepseek-v4-flash', err)
check('目标带上游地址与解密后的 Key',
      bool(target['url'].endswith('/chat/completions')) and len(target['api_key']) > 10)
target2, err2 = utils.resolve_target(model_key='deepseek-v4-pro')
check('指定 model 生效', err2 is None and target2['key'] == 'deepseek-v4-pro')
_, err4 = utils.resolve_target(model_key='not-exist-model')
check('未知 model 报参数值非法(20003)', err4 is not None and err4[0] == 20003, err4)
target5, err5 = utils.resolve_target(user_key='user-supplied-key')
check('调用方自带 api_key 覆盖平台 Key', err5 is None and target5['api_key'] == 'user-supplied-key')

urls, e = utils.parse_images(json.dumps([IMG, IMG]))
check('images JSON 数组解析', e is None and len(urls) == 2, e)
urls, e = utils.parse_images(f'{IMG}\n{IMG}')
check('images 纯文本按换行拆分', e is None and len(urls) == 2, e)
_, e = utils.parse_images('["http://127.0.0.1/a.jpg"]')
check('images 拒绝回环地址', e is not None and '图片地址不可用' in e, e)
_, e = utils.parse_images('["http://10.0.0.5/a.jpg"]')
check('images 拒绝内网地址', e is not None, e)
_, e = utils.parse_images('["file:///etc/passwd"]')
check('images 拒绝非 http(s) 协议', e is not None, e)

msgs = utils.build_messages('看看这张图', images=[IMG], platform_prompt='平台提示词')
check('后台配置的系统提示词自动插入为 system 消息',
      msgs[0] == {'role': 'system', 'content': '平台提示词'}, msgs[0])
check('后台未配置提示词时不插 system 消息',
      utils.build_messages('hi')[0]['role'] == 'user')
check('调用方自带 system_prompt 时优先用调用方的',
      utils.build_messages('hi', system_prompt='[{"role": "system", "content": "调用方"}]',
                           platform_prompt='平台提示词')[0]['content'] == '调用方')
last = msgs[-1]
check('图片挂到最后一条 user 消息（OpenAI 多模态格式）',
      last['role'] == 'user' and isinstance(last['content'], list)
      and last['content'][0] == {'type': 'text', 'text': '看看这张图'}
      and last['content'][1]['type'] == 'image_url', last)
check('system_prompt 传空字符串则不插入系统消息',
      utils.build_messages('hi', system_prompt='', platform_prompt='平台提示词')[0]['role'] == 'user')
try:
    utils.build_messages('', '[{"role": "assistant", "content": "x"}]', images=[IMG])
    check('messages 无 user 消息时抛 ValueError', False, '未抛错')
except ValueError:
    check('messages 无 user 消息时抛 ValueError', True)

# ==================== B. 视图层参数校验 ====================
r = post_chat({'content': 'hi', 'prefix': 'true'})
check('prefix=true 明确报「已下线」(20003)', r['code'] == 20003 and '已下线' in r['msg'], r)
r = post_chat({'content': 'hi', 'stream': 'maybe'})
check('stream 非法值报 20002', r['code'] == 20002, r)
for name, value in (('temperature', '0.5'), ('max_tokens', '128'), ('stop', 'END')):
    r = post_chat({'content': 'hi', name: value})
    check(f'{name} 已收回、传入报 20003',
          r['code'] == 20003 and name in r['msg'], r)
r = post_chat({'content': 'hi', 'model': 'ghost'})
check('未知模型报 20003', r['code'] == 20003, r)
r = post_chat({'model': 'deepseek-v4-flash'})
check('缺 content/messages 报参数值非法', r['code'] == 20003, r)
r = post_chat({'content': 'hi', 'messages': '{oops'})
check('messages 非法 JSON 报 20002', r['code'] == 20002, r)
r = post_chat({'content': 'hi', 'images': json.dumps([IMG])})
check('不支持视觉的模型传 images 报 20003', r['code'] == 20003 and '不支持视觉' in r['msg'], r)
r = post_chat({'content': 'hi', 'images': '["http://127.0.0.1/a.jpg"]'})
check('images 内网地址报 20003', r['code'] == 20003, r)

r = body(ai_request.models_view(RequestFactory().get('/api/ai/BuiltInModel/models')))
check('GET /models 返回模型清单', r['code'] == 10000 and len(r['data']['models']) >= 2, r)

# ==================== C. 后台管理页 ====================
AuthUser = get_user_model()
su = AuthUser.objects.filter(is_superuser=True).first()
tmp_user = None
if su is None:
    su = tmp_user = AuthUser.objects.create_superuser('_tmp_ai_su', 'tmp-ai@example.com', 'x')
client = Client()
client.force_login(su)
CONSOLE = '/console/ai/models/'
NEW_KEY = 'sk-regress-abcdefghijklmnop'

html = client.get(CONSOLE).content.decode('utf-8')
check('后台页 200 且列出厂商与模型',
      'deepseek' in html and 'deepseek-v4-flash' in html)
check('后台页只显示 Key 掩码，绝不回显明文',
      AiProvider.objects.get(code='deepseek').key_hint in html
      and AiProvider.objects.get(code='deepseek').api_key not in html)

# 表单自检：页面上所有 action 隐藏域的取值都必须是后端认识的动作名。
# 弹窗里的 action 与 console_ai._handle_post 的分发脱节过一次（提交后只提示「不支持的操作」），
# 服务端直调视图的用例抓不到，故在此对渲染结果做一次闭环比对。
page_actions = set(re.findall(r'name="action"\s+value="([^"]*)"', html))
check('后台页 action 取值全部被后端接受',
      page_actions and page_actions <= console_ai.ACTIONS,
      f'页面: {sorted(page_actions)} 后端: {sorted(console_ai.ACTIONS)}')
check('模型弹窗含「最多图片数」输入框、行内 data-maximg 与回填脚本齐全',
      'name="max_images"' in html and 'data-maximg=' in html
      and "'max_images', d.maximg" in html)

client.post(CONSOLE, {'action': 'provider_create', 'code': TEST_VENDOR,
                      'name': '回归测试厂商', 'base_url': 'https://api.deepseek.com/',
                      'api_key': NEW_KEY, 'sort': '9', 'remark': 'regress', 'enabled': '1'})
vendor = AiProvider.objects.filter(code=TEST_VENDOR).first()
check('后台新建厂商（地址去尾斜杠）',
      vendor is not None and vendor.base_url == 'https://api.deepseek.com', vendor)
check('去尾斜杠后拼出的对话地址正确',
      bool(vendor) and vendor.chat_url == 'https://api.deepseek.com/chat/completions')
check('掩码按规则生成', bool(vendor) and vendor.key_hint == 'sk-…mnop', getattr(vendor, 'key_hint', ''))
with connection.cursor() as cur:
    # Django 的原始 SQL 用 %s 占位（sqlite 后端会在驱动层转成 ?）
    cur.execute('SELECT api_key FROM ai_provider WHERE code = %s', [TEST_VENDOR])
    stored = cur.fetchone()[0]
check('Key 落库为 enc:v1: 密文（非明文）',
      str(stored).startswith('enc:v1:') and NEW_KEY not in str(stored))

client.post(CONSOLE, {'action': 'provider_create', 'code': TEST_VENDOR,
                      'name': '重复', 'base_url': 'https://x.com', 'enabled': '1'})
check('厂商标识重复被拒（不覆盖原记录）',
      AiProvider.objects.filter(code=TEST_VENDOR).count() == 1)

client.post(CONSOLE, {'action': 'provider_create', 'code': 'Bad Code!',
                      'name': '非法', 'base_url': 'ftp://x', 'enabled': '1'})
check('非法厂商标识被拒', not AiProvider.objects.filter(name='非法').exists())

client.post(CONSOLE, {'action': 'model_create', 'key': TEST_MODEL, 'name': '回归测试模型',
                      'provider': str(vendor.pk), 'max_images': '2', 'sort': '9', 'enabled': '1'})
model = AiModel.objects.filter(key=TEST_MODEL).first()
check('后台新建模型', model is not None and model.provider_id == vendor.pk, model)
check('新模型即时出现在对外清单（缓存已失效）',
      any(m['model'] == TEST_MODEL for m in utils.public_models()))

client.post(CONSOLE, {'action': 'model_create', 'key': 'bad key!', 'name': '非法',
                      'provider': str(vendor.pk), 'enabled': '1'})
check('非法模型标识被拒', not AiModel.objects.filter(name='非法').exists())

r = post_chat({'content': 'hi', 'model': TEST_MODEL, 'images': json.dumps([IMG])})
check('能力拦截按模型生效（新模型未勾视觉 → 20003）', r['code'] == 20003, r)

client.post(CONSOLE, {'action': 'model_edit', 'id': str(model.pk), 'key': TEST_MODEL,
                      'name': '回归测试模型', 'provider': str(vendor.pk),
                      'supports_vision': '1', 'max_images': '2', 'sort': '9', 'enabled': '1'})
model.refresh_from_db()
check('后台勾选「支持视觉」后落库', model.supports_vision is True)
r = post_chat({'content': 'hi', 'model': TEST_MODEL, 'images': json.dumps([IMG])})
check('勾选视觉后能力拦截不再触发', r['code'] != 20003, r)

# 图片张数上限由后台按模型配置（默认 2）：超限在调用上游之前就被拦下
r = post_chat({'content': 'hi', 'model': TEST_MODEL, 'images': json.dumps([IMG] * 3)})
check('超过模型配置的图片张数上限报 20003',
      r['code'] == 20003 and '最多' in r['msg'], r)
client.post(CONSOLE, {'action': 'model_edit', 'id': str(model.pk), 'key': TEST_MODEL,
                      'name': '回归测试模型', 'provider': str(vendor.pk),
                      'supports_vision': '1', 'max_images': '5', 'sort': '9', 'enabled': '1'})
model.refresh_from_db()
check('后台可改图片张数上限并即时生效',
      model.max_images == 5 and utils.resolve_target(model_key=TEST_MODEL)[0]['max_images'] == 5,
      model.max_images)
client.post(CONSOLE, {'action': 'model_edit', 'id': str(model.pk), 'key': TEST_MODEL,
                      'name': '回归测试模型', 'provider': str(vendor.pk),
                      'supports_vision': '1', 'max_images': '0', 'sort': '9', 'enabled': '1'})
model.refresh_from_db()
check('后台拒绝越界的图片张数上限（原值不被覆盖）', model.max_images == 5, model.max_images)

client.post(CONSOLE, {'action': 'model_default', 'id': str(model.pk)})
model.refresh_from_db()
check('设为默认：本模型置位、其它模型取消',
      model.is_default and AiModel.objects.filter(is_default=True).count() == 1)
t, e = utils.resolve_target()
check('不传 model 时切到新的默认模型', e is None and t['key'] == TEST_MODEL, e)

client.post(CONSOLE, {'action': 'model_toggle', 'id': str(model.pk)})
model.refresh_from_db()
check('下架后从对外清单消失',
      not model.enabled and not any(m['model'] == TEST_MODEL for m in utils.public_models()))
_, e = utils.resolve_target(model_key=TEST_MODEL)
check('下架模型不可调用（20003）', e is not None and e[0] == 20003, e)

client.post(CONSOLE, {'action': 'provider_toggle', 'id': str(vendor.pk)})
vendor.refresh_from_db()
check('停用厂商后其模型全部退出清单',
      not vendor.enabled and not any(m['model'] == TEST_MODEL for m in utils.public_models()))
client.post(CONSOLE, {'action': 'provider_toggle', 'id': str(vendor.pk)})

client.post(CONSOLE, {'action': 'provider_test', 'id': str(vendor.pk)})
check('「测试连通性」动作不报错（无效 Key 也应给出明确失败结论）',
      AiProvider.objects.filter(pk=vendor.pk).exists())

client.post(CONSOLE, {'action': 'provider_delete', 'id': str(vendor.pk)})
check('删除厂商级联删除其模型',
      not AiProvider.objects.filter(code=TEST_VENDOR).exists()
      and not AiModel.objects.filter(key=TEST_MODEL).exists())

# 删掉「持有默认标记」的模型后：不传 model 应明确报「未设置默认」，而不是静默挑一个
r = post_chat({'content': 'hi'})
check('默认模型被删后不传 model 明确报错(50002)',
      r['code'] == 50002 and '默认' in r['msg'], r)
client.post(CONSOLE, {'action': 'model_default',
                      'id': str(AiModel.objects.get(key='deepseek-v4-flash').pk)})
check('后台可把默认模型补回',
      AiModel.objects.filter(is_default=True, enabled=True).exists())

# ==================== C2. 系统提示词与采样参数（后台配置，调用方不能改） ====================
# 用 ORM 造临时数据（走后台表单的路径已在 C 段覆盖，这里只验证「解析 + 下发 + 三态」）
PV, PM = PROMPT_VENDOR, PROMPT_MODEL
pv = AiProvider(code=PV, name='回归提示词厂商', base_url='https://example.com', sort=99)
pv.set_api_key('sk-regress-prompt-key')
pv.save()
p_custom = AiSystemPrompt.objects.create(name='回归专用提示词', content='专用提示词正文')
pm = AiModel.objects.create(key=PM, name='回归提示词模型', provider=pv, sort=99)

check('未配置提示词时平台提示词为空',
      utils.resolve_target(PM)[0]['platform_prompt'] == '')
p_global = AiSystemPrompt.objects.create(name='回归全局提示词', content='全局提示词正文', is_global=True)
check('「跟随全局」的模型取到全局共享提示词',
      utils.resolve_target(PM)[0]['platform_prompt'] == '全局提示词正文')

client.post(CONSOLE, {'action': 'model_edit', 'id': str(pm.pk), 'key': PM, 'name': '回归提示词模型',
                      'provider': str(pv.pk), 'prompt_choice': f'prompt:{p_custom.pk}',
                      'temperature': '0.3', 'max_tokens': '128', 'stop': 'END,STOP',
                      'max_images': '2', 'sort': '99', 'enabled': '1'})
pm.refresh_from_db()
check('后台可把模型指定到某一条提示词',
      pm.prompt_mode == 'custom' and pm.system_prompt_id == p_custom.pk)
t, _ = utils.resolve_target(PM)
check('指定的提示词生效', t['platform_prompt'] == '专用提示词正文')
check('采样参数随模型下发（温度 / 上限 / 停止词）',
      abs(t['temperature'] - 0.3) < 1e-9 and t['max_tokens'] == 128
      and t['stop_list'] == ['END', 'STOP'], t)

# 越界温度必须被后台拒掉（表单整体提交，被拒时原值不应被覆盖）
client.post(CONSOLE, {'action': 'model_edit', 'id': str(pm.pk), 'key': PM, 'name': '回归提示词模型',
                      'provider': str(pv.pk), 'temperature': '9',
                      'max_images': '2', 'sort': '99', 'enabled': '1'})
pm.refresh_from_db()
check('后台拒绝越界采样温度（原值不被覆盖）', abs(pm.temperature - 0.3) < 1e-9, pm.temperature)

p_custom.enabled = False
p_custom.save(update_fields=['enabled', 'updated_time'])
check('指定的提示词被停用 → 自动回落到全局共享',
      utils.resolve_target(PM)[0]['platform_prompt'] == '全局提示词正文')
p_custom.enabled = True
p_custom.save(update_fields=['enabled', 'updated_time'])

client.post(CONSOLE, {'action': 'model_edit', 'id': str(pm.pk), 'key': PM, 'name': '回归提示词模型',
                      'provider': str(pv.pk), 'prompt_choice': 'none',
                      'max_images': '2', 'sort': '99', 'enabled': '1'})
check('选「不使用系统提示词」→ 平台提示词为空',
      utils.resolve_target(PM)[0]['platform_prompt'] == '')
client.post(CONSOLE, {'action': 'model_edit', 'id': str(pm.pk), 'key': PM, 'name': '回归提示词模型',
                      'provider': str(pv.pk), 'prompt_choice': 'inherit',
                      'max_images': '2', 'sort': '99', 'enabled': '1'})
pm.refresh_from_db()
check('选「跟随全局共享」→ 回到 inherit 且解除指定',
      pm.prompt_mode == 'inherit' and pm.system_prompt is None)

client.post(CONSOLE, {'action': 'prompt_create', 'name': '回归新建提示词',
                      'content': '临时正文', 'enabled': '1'})
created = AiSystemPrompt.objects.filter(name='回归新建提示词').first()
check('后台可新建系统提示词', created is not None)
client.post(CONSOLE, {'action': 'prompt_global', 'id': str(created.pk)})
check('设为全局共享后全库只剩这一条',
      AiSystemPrompt.objects.filter(is_global=True).count() == 1
      and AiSystemPrompt.objects.get(pk=created.pk).is_global)
client.post(CONSOLE, {'action': 'prompt_toggle', 'id': str(created.pk)})
check('后台可停用系统提示词', AiSystemPrompt.objects.get(pk=created.pk).enabled is False)
client.post(CONSOLE, {'action': 'prompt_delete', 'id': str(created.pk)})
check('后台可删除系统提示词', not AiSystemPrompt.objects.filter(pk=created.pk).exists())

pv.delete()                                   # 级联删掉 pm
AiSystemPrompt.objects.filter(pk__in=[p_global.pk, p_custom.pk]).delete()
check('提示词与采样参数临时数据已清理',
      not AiProvider.objects.filter(code=PV).exists()
      and not AiModel.objects.filter(key=PM).exists()
      and not AiSystemPrompt.objects.filter(pk=p_global.pk).exists())

# ==================== D. 真实上游调用 ====================
provider = AiProvider.objects.filter(code='deepseek').first()
key_ok = provider is not None and provider.has_key
if key_ok:
    # 平台 Key 存在只代表「配了」，能不能用还得看上游；直连探一次决定是否执行本组
    try:
        probe = requests.post(provider.chat_url,
                              json={'model': 'deepseek-v4-flash',
                                    'messages': [{'role': 'user', 'content': 'ping'}],
                                    'stream': False, 'max_tokens': 1},
                              headers={'Authorization': f'Bearer {provider.api_key}'}, timeout=20)
    except requests.RequestException as exc:
        key_ok, probe = False, None
        print('   直连上游异常：', exc)
    else:
        key_ok = probe.status_code == 200
        if not key_ok:
            print(f'   直连上游 HTTP {probe.status_code}：{probe.text[:120]}')

if not key_ok:
    skip('上游真实调用（含流式）', '平台 Key 被上游判为无效（与本脚本无关，换有效 Key 后自动覆盖）')
else:
    live_target, _ = utils.resolve_target()
    # 注意：deepseek-v4-flash 是推理模型，先流 reasoning_content（思考）再流 content（答案）。
    # max_tokens 给太小（如 16/24）时 token 会在思考阶段就用尽、content 一帧都没有，
    # 会把「上游可用」误判成不可用——故这里给足额度，并断言确实拿到了正文。
    ok, result = utils.chat_completion(
        live_target, utils.build_messages('只回复两个字：你好', system_prompt=''),
        temperature=0, max_tokens=256)
    check('真实调用上游成功（非流式）', ok and (result.get('reply') or '').strip(), result)
    if ok:
        check('返回结构含 reply/model/usage/finish_reason',
              {'reply', 'model', 'usage', 'finish_reason'} <= set(result), result.keys())
    chunks, done = [], False
    for line in utils.stream_chat_completion(
            live_target, utils.build_messages('数到三', system_prompt=''), max_tokens=256):
        if line.strip() == 'data: [DONE]':
            done = True
        elif line.startswith('data: '):
            chunks.append(json.loads(line[6:]).get('content', ''))
    check('真实调用上游成功（流式 SSE）', done and len(chunks) > 0, f'chunks={len(chunks)}')
    ok_test, msg = utils.test_provider(provider)
    check('后台「测试连通性」在有效 Key 下返回成功', ok_test, msg)

# ==================== 清理 ====================
cleanup()
if tmp_user is not None:
    tmp_user.delete()

print(f'\n=== PASS {PASS} / FAIL {FAIL} / SKIP {SKIP} ===')
sys.exit(1 if FAIL else 0)
