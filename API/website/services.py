"""官网首页展示的 API 服务清单

数据与 API/apis/urls.py 及 README「API 服务清单」保持一致。
仅用于前台展示（名称/简介/能力标签），新增服务时同步在此追加一条即可。

多语言说明：本表在模块导入时即构造完成，若在声明处调用 gettext 会把首次导入时的
语言永久固化，故中文为源语言原样保留，展示前统一调用 localize() 按当前语言翻译。
"""
from django.utils.translation import gettext as _

SERVICES = [
    {
        'name': '用户中心',
        'url_prefix': '/api/user_center/',
        'desc': '统一认证中心（UAC）：全局用户池，账号/邮箱/手机号注册登录，Token 签发与验证，多方式可配。',
        'tags': ['注册登录', 'Token验证', '统一认证'],
    },
    {
        'name': '音乐服务',
        'url_prefix': '/api/music/',
        'desc': '聚合爱听音乐网（2t58）与小影音乐，提供搜索、榜单、播放源等能力。',
        'tags': ['音乐搜索', '榜单', '播放源'],
    },
    {
        'name': 'AI 服务',
        'url_prefix': '/api/ai/',
        'desc': '内置模型能力，开箱即用的 AI 文本/内容接口。',
        'tags': ['内置模型', '文本生成'],
    },
    {
        'name': '邮箱服务',
        'url_prefix': '/api/email/',
        'desc': '邮箱发送与虚拟邮箱收发（VMEmail），覆盖验证邮件、收发场景。',
        'tags': ['邮件发送', '虚拟邮箱'],
    },
    {
        'name': '代理 IP',
        'url_prefix': '/api/ProxyIp/',
        'desc': '66免费 / 91HTTP / 青雨动态与住宅长效 / 巨量代理 / 静态代理 / Thordata 动态住宅代理多源聚合，附带可用性验证。',
        'tags': ['HTTP代理', '静态代理', '住宅代理', '可用性检测'],
    },
    {
        'name': '短信验证',
        'url_prefix': '/api/sms_verify/',
        'desc': '阿里云短信验证码认证，服务端回传校验，安全下发。',
        'tags': ['短信验证码', '阿里云'],
    },
    {
        'name': '图形验证',
        'url_prefix': '/api/captcha_auth/',
        'desc': '阿里云图形验证码集成（滑块/点选），防机器流量。',
        'tags': ['滑块验证', '行为验证'],
    },
    {
        'name': '自研图形验证码',
        'url_prefix': '/api/captcha_self/',
        'desc': '自研字符图片 / 算术验证码，本地绘制、无第三方依赖，答案一次性校验。',
        'tags': ['字符验证码', '算术验证码', '本地生成'],
    },
    {
        'name': '验证码识别',
        'url_prefix': '/api/ddddocr/',
        'desc': '基于 ddddocr 的通用图片验证码识别服务。',
        'tags': ['OCR识别', '验证码'],
    },
    {
        'name': '文件上传',
        'url_prefix': '/api/upload/',
        'desc': '通用文件上传，统一接入与安全响应头处理。',
        'tags': ['文件上传', '安全下载'],
    },
    {
        'name': '图床服务',
        'url_prefix': '/api/ImageHosting/',
        'desc': '图片外链托管：上传图片获取 CDN 直链，支持输出格式、加密与存储位置选择；PicUI 线路由服务端 Token 池自动管理容量。',
        'tags': ['图床', '图片外链', 'CDN'],
    },
    {
        'name': '代练通',
        'url_prefix': '/api/dlt/',
        'desc': '代练订单信息查询与操作（认证/用户/订单/头像）。',
        'tags': ['订单查询', '游戏代练'],
    },
    {
        'name': '代练丸子',
        'url_prefix': '/api/dlwz/',
        'desc': '代练丸子数据接口封装。',
        'tags': ['数据查询'],
    },
    {
        'name': 'SEO 服务',
        'url_prefix': '/api/seo/',
        'desc': '友情链接等 SEO 周边能力，利于站点外链建设。',
        'tags': ['友情链接'],
    },
    {
        'name': '爬虫验证',
        'url_prefix': '/api/spider_verification/',
        'desc': '爬虫环境验证（SV4759），识别自动化环境。',
        'tags': ['环境检测'],
    },
    {
        'name': '问题反馈',
        'url_prefix': '/api/feedback/',
        'desc': '统一问题反馈中心：任何接入项目放一个链接或 iframe 即可接入（子项目零代码），'
                '用户提交建议 / 升级 / 问题 / BUG 并可携带图片与视频，AI 先审内容、管理员后台回复，'
                '每个项目还能展示各自的开发者联系方式。',
        'tags': ['反馈', '工单', '零代码接入', 'AI审核'],
    },
    {
        'name': '调用统计',
        'url_prefix': '/api/statistics/',
        'desc': '公开查询 API 调用量：某个接口被调用了多少次、各服务调用量排行。',
        'tags': ['调用量', '公开统计'],
    },
    {
        'name': '抖音',
        'url_prefix': '/api/douyin/',
        'desc': '抖音平台能力聚合：视频/图文解析（无水印提取）与评论自动发布。',
        'tags': ['抖音', '视频解析', '评论发布'],
    },
    {
        'name': '电影',
        'url_prefix': '/api/movies/',
        'desc': '影视聚合：分类、列表、详情、选集与播放地址（m3u8）及搜索，按「列表 → 详情 → 播放」即可搭建完整影视站。',
        'tags': ['电影', '电视剧', '动漫综艺', '播放地址', '搜索'],
    },
    {
        'name': '短剧',
        'url_prefix': '/api/dramas/',
        'desc': '短剧聚合：热播榜单、分类、搜索、剧集详情（含全量集列表）与播放地址，全量集数均可播放'
                '（前 3 集为源站明链，第 4 集及以后由服务端取流并解密），按「榜单/分类 → 详情 → 播放」即可搭建短剧站。',
        'tags': ['短剧', '红果短剧', '榜单', '播放地址', '搜索'],
    },
    {
        'name': '海角社区',
        'url_prefix': '/api/haijiao/',
        'desc': '海角社区内容：热帖 / 新闻 / 大事记 / 原创 / 精华 / 最新列表、帖子搜索、帖子详情与评论、'
                '可直接播放的视频（已还原源站真密钥）与发帖（板块 / 标签 / 图片视频）；'
                '配图为源站混淆地址，需按文档说明自行解密。',
        'tags': ['热帖', '新闻', '大事记', '原创', '精华', '最新', '评论', '发帖'],
    },
]


def localize(items):
    """返回按当前语言翻译后的服务清单副本（不改动模块级 SERVICES 原文）"""
    return [
        {
            **svc,
            'name': _(svc['name']),
            'desc': _(svc['desc']),
            'tags': [_(tag) for tag in svc['tags']],
        }
        for svc in items
    ]
