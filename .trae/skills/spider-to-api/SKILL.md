---
name: "spider-to-api"
description: "基于爬虫文件分析并生成符合项目规范的API服务(三件套结构+统一响应+curl示例)。当用户明确要求基于爬虫生成API时调用。"
---

# 爬虫转 API 服务生成器

## 触发条件

**仅当用户明确要求**基于爬虫文件/目录生成 API 服务时调用本 skill。
典型用户输入格式：

> 请对爬虫文件 `<爬虫文件路径>` 进行全面分析，学习并理解其中所有对外暴露的函数及其功能、参数要求、返回值格式和使用场景。基于这些函数，在 API 服务目录 `<API目录路径>` 下实现完整的 API 服务。具体要求包括：
> 1. 设计并实现与爬虫函数对应的 API 接口，确保接口功能与原函数一致
> 2. 在 `<API目录路径>` 目录下正确配置所有 API 路由，包括路径定义、请求方法和参数映射
> 3. 为每个 API 接口实现完整的请求处理逻辑，包括参数验证、错误处理和响应格式化
> 4. 确保 API 服务符合 RESTful 设计规范，提供清晰的接口文档
> 5. 完成所有 API 接口的 curl 调用示例，包含完整的请求 URL、HTTP 方法、请求头、请求参数和预期响应格式
>
> 最终交付物应包括完整的 API 实现代码、路由配置文件以及所有接口的 curl 调用命令集合。

## 总体原则

- **强制遵循现有项目代码风格**：三件套结构（`request.py` / `utils.py` / `urls.py`）、统一 JSON 响应格式、复用项目现有 `StatusCode` 状态码体系
- **精准修改**：只触碰必须修改的内容，不重构无关代码，不"改进"相邻代码
- **简洁至上**：用最少的代码解决问题，不做无根据的推测，不为一次性代码创建抽象
- **路径通用化**：不硬编码任何具体项目路径，所有路径由用户输入动态决定

## 工作流程

### 第一步：信息收集（并行执行）

**必须先读后写**。一次性并行读取以下文件以理解上下文：

1. **爬虫文件**：完整读取，提取所有对外暴露的方法（公开方法，非 `_` 开头的私有方法）
2. **目标 API 目录**下的 `request.py`、`utils.py`、`urls.py`（若已存在）
3. **项目通用响应规范**：读取 `API/common/status_code.py`（或等价的状态码定义文件）和 `API/common/__init__.py`
4. **上层路由文件**：读取目标 API 目录的父级 `urls.py`，确认路由是否已挂载

### 第二步：爬虫接口分析

对爬虫的每个对外方法，提取并记录以下信息：

| 分析维度 | 说明 |
|---------|------|
| 方法名 | 对外暴露的公开方法名 |
| 功能 | 该方法做什么 |
| 参数 | 每个参数的名称、类型、是否必填、默认值、取值约束 |
| 返回值 | 返回的数据结构（dict 的字段、list 的元素结构）|
| 异常 | 可能抛出的异常类型及触发条件 |
| 依赖 | 是否依赖实例状态（如先调用 A 方法才能调用 B 方法）|
| 使用场景 | 适合什么业务场景调用 |

**关键识别点**：
- 爬虫的会话/身份标识机制（如 `visitor_id`、`session`、`token`）需特别关注——这通常决定了 API 层如何设计"会话凭证"由客户端保管
- 若某方法依赖另一方法建立的实例状态，API 层的 `utils` 封装应内部自动建立上下文，使调用方无感

### 第三步：API 设计

#### 3.1 接口设计原则

- **RESTful 规范**：
  - 只读查询用 `GET`，参数走 query string
  - 创建/修改/触发动作用 `POST`，参数走表单（`application/x-www-form-urlencoded`）或 JSON body
  - 资源路径用名词，层级清晰
- **无状态设计**：会话凭证（如 UUID、token）由客户端保管，服务端不维护会话状态
- **线程安全**：每次请求创建独立爬虫实例，避免 session 共享竞态

#### 3.2 三件套职责划分

**`utils.py`（爬虫调用封装）**：
- 每次调用创建新的爬虫实例（无状态、线程安全）
- 统一捕获爬虫抛出的异常（`requests.RequestException`、`RuntimeError` 等）
- 返回 `(是否成功, 数据或错误信息)` 二元组：`(True, data)` 或 `(False, error_msg)`
- 对外函数与爬虫方法一一对应
- 若爬虫方法间有状态依赖，在封装层内部自动建立上下文（如先调用 init 方法再调用业务方法）
- 异常分类：网络层异常 → 外部服务错误；其他异常 → 系统内部错误

**`request.py`（视图处理）**：
- 每个接口一个视图函数，用 `@require_http_methods([...])` 限定请求方法
- 参数校验顺序：必填校验 → 格式校验 → 值域校验
- 调用 `utils` 层函数，根据返回的二元组构造响应
- 统一响应格式：`{"code": int, "msg": str, "data": Any}`
- 提供私有 `_json_response(code, data=None, msg=None)` 辅助函数

**`urls.py`（路由配置）**：
- 每个视图配置一个 `path`，附带 `name` 参数便于反向解析
- 注释标注完整访问路径前缀

#### 3.3 参数校验规范

- 必填参数缺失 → `StatusCode.PARAM_MISSING`（20001）
- 格式错误（非 UUID、非正整数、非合法 URL 等）→ `StatusCode.PARAM_FORMAT_ERROR`（20002）
- 值非法（不在允许枚举内、URL 域名不匹配等）→ `StatusCode.PARAM_VALUE_INVALID`（20003）
- 爬虫调用失败 → `StatusCode.EXTERNAL_API_FAILED`（40001）
- 成功 → `StatusCode.SUCCESS`（10000）

#### 3.4 安全防护

- 涉及外部 URL 的参数，须校验域名白名单，防止 SSRF
- 涉及用户身份的参数（如 UUID），须校验格式合法性
- 不信任任何客户端输入，所有参数均需校验后再传入爬虫

### 第四步：实现编码

**文件编写顺序**：`utils.py` → `request.py` → `urls.py`

**若上层路由未挂载**：需在父级 `urls.py` 中补充 `include`，并告知用户修改了哪个文件。

**代码注释要求**：
- 模块顶部 docstring 说明职责与对外接口
- 函数 docstring 说明参数、返回值
- 关键逻辑行内注释（如"先建立会话上下文"、"去重避免重复发送"）
- 使用中文注释（与项目风格一致）

### 第五步：验证

1. **Django 检查**：执行 `python manage.py check`，须无 issues
2. **路由解析验证**：用 `django.urls.resolve` 验证每个路由路径能正确解析到对应视图函数
3. **依赖验证**：若爬虫引入了新依赖（如 `lxml`、`pycryptodome`），需确认已安装且导入正常

### 第六步：交付文档

交付说明必须包含以下章节：

#### 1. 爬虫接口分析表
列出爬虫每个对外方法的方法名、参数、返回结构。

#### 2. 实现文件清单
列出新增/修改的文件，附可点击的文件链接。

#### 3. 路由层级树
用树形结构展示完整路由路径，从根域名到各接口。

#### 4. API 接口文档与 curl 示例
每个接口包含：
- 接口路径与 HTTP 方法
- 参数表（参数名 | 位置 | 必填 | 说明）
- curl 调用示例（覆盖典型场景：默认调用、必填参数调用、可选参数调用）
- 预期成功响应 JSON 示例
- 常见错误响应示例（至少覆盖参数缺失、参数格式错误、爬虫调用失败）

#### 5. 典型使用流程
若接口间有调用顺序依赖（如先生成凭证再查询），给出串联调用示例。

#### 6. 设计说明
简述关键设计决策：RESTful 依据、线程安全方案、会话机制、安全防护等。

## 禁止事项

- **禁止**未读文件就写代码
- **禁止**修改爬虫源码（爬虫是数据源，API 是封装层，职责分离）
- **禁止**硬编码具体项目路径
- **禁止**添加未被请求的功能、配置项、灵活性
- **禁止**为不可能出现的场景写错误处理
- **禁止**重复定义（能定义一次的就定义一次，其他地方用变量）
- **禁止**省略验证步骤直接交付
- **禁止**创建未被要求的文档文件（如 README.md）

## 统一响应格式参考

```python
{
    "code": 10000,          # 状态码，参见 StatusCode
    "msg": "成功",          # 描述信息
    "data": {...} or [...]  # 业务数据，失败时为 null
}
```

## 三件套模板参考

### utils.py 模板

```python
"""<服务名>爬虫调用封装

本模块对 <爬虫路径> 中的爬虫类进行薄封装:
- 每次调用创建新的爬虫实例(无状态,线程安全)
- 统一捕获异常,返回 (是否成功, 数据或错误信息) 二元组
"""
from <爬虫模块路径> import <爬虫类名>


def <对外函数名>(<参数>):
    """<功能说明>

    :return: tuple[bool, Any]  (是否成功, 成功时为数据, 失败时为错误信息)
    """
    spider = <爬虫类名>()
    try:
        data = spider.<方法名>(<参数>)
        return True, data
    except <预期异常类型> as e:
        return False, str(e)
    except Exception as e:
        return False, f'<操作描述>失败: {e}'
```

### request.py 模板

```python
"""<服务名> API 请求处理视图

提供 N 个接口,对应爬虫的 N 个对外方法:
    <METHOD> <路径1>  <功能1>
    <METHOD> <路径2>  <功能2>
"""
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from API.common import StatusCode
from . import utils


def _json_response(code, data=None, msg=None):
    """构建统一的 JSON 响应体"""
    return JsonResponse({
        'code': code,
        'msg': msg or StatusCode.get_message(code),
        'data': data,
    })


def _<校验函数名>(value):
    """<校验说明>"""
    try:
        <校验逻辑>
        return True
    except (<异常类型>):
        return False


@require_http_methods(['<METHOD>'])
def <view_name>(request):
    """<接口说明>

    参数:
        <param1> (必填/选填): <说明>
    """
    # 1. 参数获取与校验
    <参数校验逻辑，校验失败返回 _json_response(StatusCode.PARAM_XXX, msg=...)>

    # 2. 调用爬虫
    success, data = utils.<函数名>(<参数>)
    if not success:
        return _json_response(StatusCode.EXTERNAL_API_FAILED, msg=data)
    return _json_response(StatusCode.SUCCESS, data=data)
```

### urls.py 模板

```python
# <服务名> API路由
from django.urls import path

from . import request

# 域名前缀: <完整路径前缀>
urlpatterns = [
    path('<path1>', request.<view1>, name='<unique_name_1>'),
    path('<path2>', request.<view2>, name='<unique_name_2>'),
]
```
