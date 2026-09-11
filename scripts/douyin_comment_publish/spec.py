"""抖音发布评论 - 接口逆向规格（沙箱用，不参与系统集成）

本文件只承载**已核实的接口规格**（端点 / 请求头 / 参数 / 实测门槛），不含执行逻辑。
执行尝试见 route_a_browser.py（浏览器自动化）与 route_b_sign/（补环境执行官方 JS）。

证据标注约定（避免把推测当事实）：
    [实测] 2026-09-10 本机真实请求得到的响应
    [抓包] 公开的真实抓包样本（来源见各条）
    [待核实] 尚未取得直接证据，接入前必须用真实抓包/请求复核

================================================================================
一、目标接口
================================================================================
    POST https://www.douyin.com/aweme/v1/web/comment/publish/
    - 请求体：application/x-www-form-urlencoded（表单）
    - 必须携带**登录 Cookie**（未登录无论是否签名都被拦，见第五节）
    - 返回 JSON：{status_code, status_msg, comment: {...}}

================================================================================
二、请求头（[抓包] 来源：CSDN 公开 curl 样本，抖音网页版发布评论）
================================================================================
    Accept:              application/json, text/plain, */*
    Accept-Language:     zh-CN,zh;q=0.9,en;q=0.8
    Content-Type:        application/x-www-form-urlencoded; charset=UTF-8
    Origin:              https://www.douyin.com
    Referer:             视频页 URL（如 https://www.douyin.com/video/<aweme_id>）
    User-Agent:          桌面 Chrome/Edge UA
    Cookie:              登录态（见第四节）
    Uifid:               设备指纹，由页面写入；[待核实] 是否强校验
    X-Secsdk-Csrf-Token: [实测 2026-09-11] 浏览器真实请求带的是 "DOWNGRADE"

    【必需·运行时安全头】[实测 2026-09-11 消融实验] 只有下面两个是必需的：
    x-tt-session-dtrait: 设备特征会话票据（形如 <tag>_<base64A>_<base64B>），
                         **内容严格校验**，改一个字符即被拦；缺失时响应是
                         "HTTP 200 + 0 字节"（静默拦截，不是 403）
    x-secsdk-csrf-token: 固定常量 "DOWNGRADE"

    【非必需】[实测] bd-ticket-guard-* 整套（version / web-version / web-sign-type /
    ree-public-key / client-data）**都可以不带**：即便带上，把 req_sign 换成随机值或置空
    也照样通过，说明服务端并不校验它。记录在此，以免日后误判为必需项。

================================================================================
三、参数
================================================================================
[实测 2026-09-11 决定性结论] 参数必须放 **query**，POST 的 body 留空：
    - query 传参 → status_code=0，发布成功（cid=7684070532334306085，用本机登录态实测）
    - body 传参 → status_code=8（同一会话下立刻复测，未发布）
  请求链路为 POST + 空 body，所有参数（公共参数 + 业务参数）拼在 URL 查询串上。
  页面脚本会自动往 query 追加 msToken / a_bogus / verifyFp / fp（我的代码从未拼过它们）。

业务参数（[抓包] 字段名 + [实测] 生效）：
    aweme_id                 视频 ID
    text                     评论内容
    text_extra               JSON 数组字符串，无 @/话题时为 "[]"
    reply_id                 回复目标评论 ID；发一级评论时为 "0"
    comment_send_celltime    发送行为耗时（毫秒），前端埋点
    comment_video_celltime   视频播放耗时（毫秒），前端埋点
    one_level_comment_rank   一级评论排序位（样本为 5）
    paste_edit_method        输入方式，样本为 "non_paste"

后四个是**前端行为特征**参数（非业务必需但参与风控画像），固定为常量有被判机器
的风险，属 [待核实] 项。

公共参数（[抓包] 来源：公开的 comment/list/reply 已签名 URL，与发布接口同源同套）：
    device_platform=webapp, aid=6383, channel=channel_pc_web, pc_client_type=1,
    version_code, version_name, cookie_enabled=true, screen_width, screen_height,
    browser_language, browser_platform, browser_name, browser_version, browser_online,
    engine_name, engine_version, os_name, os_version, cpu_core_num, device_memory,
    platform=PC, downlink, effective_type, round_trip_time, webid, msToken

================================================================================
四、登录 Cookie 与自动追加项
================================================================================
    [实测] 匿名访问只能取得：__ac_nonce、ttwid
    [实测] 本机登录态 Cookie 共 61 个键，含 sessionid / sessionid_ss / sid_tt / sid_guard /
           passport_csrf_token / odin_tt / ttwid / s_v_web_id / UIFID / d_ticket /
           bd_ticket_guard_client_data（**不含 msToken**）
    → 发布评论必须使用真实登录账号的完整 Cookie，匿名必定失败。
    → verifyFp / fp 的取值等于 Cookie 里的 s_v_web_id（[实测] 两者完全一致）。

================================================================================
五、当前卡点：a_bogus 签名（两条路线要验证的就是它）
================================================================================
[实测] 2026-09-10 本机匿名探测（可复跑 probe.py 复现）：
    不签名              → HTTP 403，空响应
    带本仓库旧版 a_bogus → HTTP 403，空响应
  说明：风控层在业务逻辑之前拦截；403 空响应无法区分「签名无效」与「未登录」，
  所以验收标准是唯一的：**门槛通过时返回的应是业务 JSON（而非 403 空响应）**。

签名现状（[抓包] 公开逆向文章，2025-07 / 2026-05 多篇一致）：
    - 本仓库 SpiderServices/Douyin/Video/abogus.py 是 **1.0.1.5 版**算法
      （_end_string="cus"、s4 字符表），仓库注释亦记录「携带即 403」。
    - 现行版本为 **bdms 1.0.1.19-fix（JSVMP 虚拟机保护）**，纯 Python 复现成本高；
      新版还要求页面**至少触发过一次鼠标事件**才生成有效值。

两条路线的实测结论（2026-09-11）：
    A. 浏览器自动化：**已验证可发布**。在已登录页面上下文里 fetch，参数放 query、body 留空，
       页面脚本自动补 msToken/a_bogus/verifyFp/fp → status_code=0 且返回 comment.cid。
    B. 纯服务端（node 补环境 + requests 发送）：**已验证可发布，无需浏览器**。
       三件套：a_bogus（node 跑 bdms 生成，实测不与 UA/服务端绑定）+ msToken（ms_token.txt）
       + 运行时安全头（node 补环境跑抖音 securitySDK 现场产出 dtrait）。
       [实测] comment/publish 返回 status_code=0：cid=7684097675687428916（借头阶段）、
       cid=7684103483653391114（补环境产出阶段）。

安全头来源与最终方案（[实测] 2026-09-11 已打通，代码见 route_b_sign/）：
    - securitySDK 本体不在独立文件里，而在抖音 webpack 的**异步 chunk**
      （async/20021.3fff349b.js，233KB）；同路径的 UMD 构建在 CDN 上不存在（404）。
    - 解法：自建最小 webpack runtime，把抖音主站 chunk 下到 js/douyin/，
      在 node 沙箱里注册全部模块，再 require 入口模块（179262）——它执行
      window.securitySDK = new BG({containerType:"sdk"})。
      见 route_b_sign/secsdk_env.js（沙箱 + runtime + 按需加载磁盘 chunk）。
    - 初始化顺序（照抄浏览器已初始化实例）：
        setWebId → setContext → setStorageType("next") → setDisableCrossStorage(true)
        → setEnableTrustedTimestamp(true) → setLoginStatus(true)
        → setConfig({scene:"web_protect", certType:"cookie", ...}) → start()
        → startDTrait({consumerPathList:[...]}) → secureProxy.installInterceptors()
    - dtrait 模块是**动态 chunk**（83854.2bf261c4.js，由 SDK 内部 req.e(83854) 拉取）；
      取到实例后 updateDTraitPath / updateDTraitHost / init，
      再 getDTraitHeader({url, method}) → {"x-tt-session-dtrait": ...}
    - 补环境踩到的坑（都已修在 env.js / secsdk_env.js 里）：
        1) ArrayBuffer / TypedArray 必须用宿主 realm 的，否则 node WebCrypto 的
           subtle.importKey 会报「不是 BufferSource」（vm 子 realm 类型不被认）
        2) XMLHttpRequest 不能是空壳：SDK 拉证书、上报都走 XHR，空壳会报 get cert timeout
        3) fetch 记录器必须在 SDK **构造之前**装好（secureProxy 在构造时就把当时的
           window.fetch 记作「原始 fetch」）
        4) 需预置 window.ucSecureToolDetect，跳过反自动化检测 SDK 的动态脚本注入
        5) document.getElementsByTagName('head')[0] 必须存在（SDK 会往 head 插 script）
    - [实测] 产出的 dtrait tag 是 "undefined"（该实例的 central 配置为空），但服务端照收：
      用它发布 comment/publish 返回 status_code=0，cid=7684103483653391114。
    - sec_headers.json（浏览器抓的静态头）保留为**回退**：补环境失败时仍能发布。

删除接口（[实测] 未打通，待核实）：
    POST /aweme/v1/web/comment/delete/ 传 cid（四种参数组合都试过）均返回
    status_code=8 / status_msg="用户未登录"，而同一会话 /aweme/v1/web/user/profile/self/ 是正常登录态，
    说明该端点还有未满足的鉴权/参数要求，具体缺什么尚未验证（不做猜测）。

================================================================================
六、其它约束
================================================================================
- 评论接口风控严格：需低频 + 失败退避，高频会导致账号被限流/封禁。
- 只能评论「存在且公开」的视频，否则业务层返回错误。
- 沙箱脚本默认使用不存在的 aweme_id（7400000000000000000），确保不会真的发出评论。
"""

# 发布评论接口
PUBLISH_API = "https://www.douyin.com/aweme/v1/web/comment/publish/"

# 匿名会话与主站
TTWID_URL = "https://ttwid.bytedance.com/ttwid/union/register/"
HOME_URL = "https://www.douyin.com/"

# 请求超时（秒）
REQUEST_TIMEOUT = 15

# 探测用视频 ID：格式合法但不对应真实视频，确保不会真的发出评论
PROBE_AWEME_ID = "7400000000000000000"

# UA（走「补环境签名」路线时需与 abogus 的 ua_code 特征码一致）
UA_STRING = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/130.0.0.0 Safari/537.36"
)

# 公共参数（[抓包] 见第三节）
BASE_PARAMS = {
    "device_platform": "webapp",
    "aid": "6383",
    "channel": "channel_pc_web",
    "pc_client_type": "1",
    "version_code": "190500",
    "version_name": "19.5.0",
    "cookie_enabled": "true",
    "browser_language": "zh-CN",
    "browser_platform": "Win32",
    "browser_name": "Edge",
    "browser_online": "true",
    "engine_name": "Blink",
    "os_name": "Windows",
    "os_version": "10",
    "platform": "PC",
    "screen_width": "1920",
    "screen_height": "1080",
}

# 业务参数默认值（[抓包] 见第三节）：发一级评论 reply_id=0，无 @/话题时 text_extra="[]"
PUBLISH_DEFAULTS = {
    "text_extra": "[]",
    "reply_id": "0",
    "comment_send_celltime": "0",
    "comment_video_celltime": "0",
    "one_level_comment_rank": "5",
    "paste_edit_method": "non_paste",
}

# 请求头模板（Cookie / Referer / X-Secsdk-Csrf-Token 由调用方按登录态填充）
HEADERS_TEMPLATE = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "Origin": "https://www.douyin.com",
    "User-Agent": UA_STRING,
}


def build_params(aweme_id=PROBE_AWEME_ID, text="probe", reply_id="0", text_extra="[]") -> dict:
    """拼装 comment/publish 表单参数（公共参数 + 业务参数）"""
    params = dict(BASE_PARAMS)
    params.update(PUBLISH_DEFAULTS)
    params.update({
        "aweme_id": str(aweme_id),
        "text": text,
        "reply_id": str(reply_id),
        "text_extra": text_extra,
    })
    return params


def load_cookie(cookie_file="cookie.txt") -> str:
    """读取单账号登录 Cookie（沙箱内用文件存放，不接入系统配置）

    :param cookie_file: 相对本文件的 Cookie 文件名
    :return: Cookie 字符串；文件不存在或为空则返回空串（表示匿名探测）
    """
    from pathlib import Path

    path = Path(__file__).resolve().parent / cookie_file
    if not path.exists():
        return ""
    lines = [ln.strip() for ln in path.read_text(encoding="utf-8").splitlines()]
    return "; ".join(ln for ln in lines if ln and not ln.startswith("#"))
