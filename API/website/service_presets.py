"""建议策略清单（后台「一键新建建议策略」与 manage.py seed_service_policies 共用）

为什么要有这份清单：服务策略表是**接口鉴权的唯一来源**，而全局兜底是 fail-closed
（未命中任何策略一律按「需要签名」处理）。那些「由浏览器直连、带不了项目签名」的接口
一旦丢了策略，就会集体返回 20011 —— 验证码出不来、海角社区的图片与 m3u8 播不了、
反馈中心子项目前端调不动。

这些例外原本散落在 0028 / 0031 / 0032 / 0035 / 0043 几条**数据迁移**里，而数据迁移一旦
标记为已执行就不会重跑：策略表若被清空 / 换环境重建，缺的数据也不会自己回来。因此把它们
收敛成这份**代码内的清单**，作为「策略表该有的最小例外集合」的唯一出处，供两处使用：

- 后台 `/console/services/` 的「一键新建建议策略」（预览面板确认后执行）
- ``python manage.py seed_service_policies``（幂等，可反复执行）

两处都只**新建缺失的**，已存在的一律不动（绝不覆盖你在后台的自定义），因此可反复执行。

**增删改就改本文件**：加一条即多一个建议，删一条即不再建议，改字段即改变建议值。
每条的值必须与上面那几条数据迁移写入的**逐字段一致**（含 `level` —— 即便迁移里有几处
层级与服务树的真实归类不符，也照抄不改，原因见下方注释），否则「一键新建」与「跑迁移」
会得到不同的鉴权结果。
"""
from API.models import ApiServicePolicy

# (路径前缀, 名称, 层级, 认证模式, 状态, 为什么需要)
#
# 状态一栏刻意与迁移保持一致：服务级的三条开放节点（验证码 / 统计）与反馈中心写的是
# normal，其余开放例外写的是 inherit。两者在没有上级策略时行为相同（全局兜底也是
# normal），但只要该服务存在服务级策略，inherit 就会跟随上级的 dev / maintenance / offline。
#
# 层级一栏照抄迁移的原始值，**明知有 4 处与模型自身的形状校验对不上**，刻意不动它：
# /api/captcha_auth/aliyun/ 迁移写作 service（服务树里实为 captcha_auth 下的 aliyun 线路），
# /api/haijiao/image、/api/feedback/ticket、/api/feedback/contacts 迁移写作 endpoint
# （实为「服务下没有更深端点的裸路由」，服务树按线路建模）。
# 为何不改：层级不参与前缀匹配（中间件只按 path_prefix 取整条策略），仅用于后台展示；
# 改它等于顺手改动与本次需求无关的存量数据语义，且会让既有回归测试的第 2 轮失配。
# 后果有限：这些行只是列表里的「层级」徽标与真实归类不符，在后台点一次「编辑」保存后
# 会自动按服务树纠正（编辑弹窗用 locate() 反查三级选择）。
SERVICE_POLICY_PRESETS = (
    (
        '/api/captcha_self/', '自研图形验证码', 'service', 'open', 'normal',
        '登录 / 注册 / 重置密码页的验证码图片由浏览器直接请求，带不了项目签名；'
        '被拦会返回 20011，页面直接登不进来。',
    ),
    (
        '/api/captcha_auth/aliyun/', '阿里云图形认证', 'service', 'open', 'normal',
        '同上：阿里云验证码 SDK 在浏览器里直连本服务，无法附带项目签名。',
    ),
    (
        '/api/statistics/', '调用统计', 'service', 'open', 'normal',
        '官网文档与首页公开查询本站调用量，未登录、无签名即可访问，属对外承诺的公开接口。',
    ),
    (
        '/api/haijiao/video/m3u8', '海角社区-视频播放列表', 'endpoint', 'open', 'inherit',
        'm3u8 播放列表由播放器（hls.js / DPlayer / VLC）直接加载，播放器带不了签名参数；'
        '被拦会一律 20011，视频播不了。',
    ),
    (
        '/api/haijiao/image', '海角社区-图片解码', 'endpoint', 'open', 'inherit',
        '<img src> 直连取图，标签无法附带签名参数；不开放则一律 20011，图片显示不出来。'
        '端点自身已限制为公网地址、拒绝内网 / 回环、只接受能解出 data:image/* 的内容。',
    ),
    (
        '/api/dramas/hongguo/stream', '红果短剧-网页直出流', 'endpoint', 'open', 'inherit',
        '<video> 标签直连播放，带不了项目签名；其鉴权改由 play 接口下发的时效令牌承担'
        '（该路径另有代码内免签名单兜底，见 API/common/middleware.py）。',
    ),
    (
        '/api/feedback/', '问题反馈中心', 'service', 'auth', 'normal',
        '反馈中心服务本身仍要求项目签名；显式建一条服务级策略，避免日后新增子端点时'
        '被上层误判为开放。',
    ),
    (
        '/api/feedback/ticket', '问题反馈中心 · 换一次性票据（子项目前端直调）',
        'endpoint', 'open', 'normal',
        '子项目前端用用户 Token 换一次性票据，走的是「零代码接入」，拿不到 AppSecret。',
    ),
    (
        '/api/feedback/contacts', '问题反馈中心 · 查开发者联系方式（子项目直调）',
        'endpoint', 'open', 'normal',
        '同上：子项目前端直接查询开发者联系方式，同样没有 AppSecret 可用。',
    ),
)

# 清单元组的字段顺序（与 SERVICE_POLICY_PRESETS 一一对应）
FIELDS = ('path_prefix', 'name', 'level', 'auth_mode', 'status', 'reason')


def _claimed_prefixes():
    """已被策略占用的全部 URL 前缀

    「占用」以实际生效范围为准：既看主前缀 ``path_prefix``，也看线路多选时写进
    ``extra_prefixes`` 的其余前缀（见 ApiServicePolicy.all_prefixes）。
    不用 JSON 查询是为了避开各数据库对 JSON 包含查询的行为差异。
    """
    claimed = set()
    for prefix, extra in ApiServicePolicy.objects.values_list('path_prefix', 'extra_prefixes'):
        claimed.add(prefix)
        claimed.update(extra or [])
    return claimed


def preset_rows():
    """清单 + 每条是否已存在（供后台预览面板逐条标注「新建 / 已存在」）"""
    claimed = _claimed_prefixes()
    return [{**dict(zip(FIELDS, row)), 'exists': row[0] in claimed}
            for row in SERVICE_POLICY_PRESETS]


def apply_presets():
    """补齐清单里**缺失**的策略，已存在的一律跳过（幂等，可反复执行）

    只新建、不覆盖：在后台手工配过或改过的策略不会被「一键」抹掉。

    :return: (新建成功的前缀列表, 因已存在而跳过的前缀列表)
    """
    created, existed = [], []
    for row in preset_rows():
        if row['exists']:
            existed.append(row['path_prefix'])
            continue
        ApiServicePolicy.objects.create(path_prefix=row['path_prefix'], name=row['name'],
                                        level=row['level'], auth_mode=row['auth_mode'],
                                        status=row['status'])
        created.append(row['path_prefix'])
    return created, existed
