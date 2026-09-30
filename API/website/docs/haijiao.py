"""海角社区服务 - 接口文档与在线调试数据

数据与 API/apis/haijiao/ 实际实现对齐（服务策略 /api/haijiao/ 默认需签名）：
- 内容列表：热帖 / 新闻 / 大事记 / 原创 / 精华 / 最新（源站接口实时爬取 + 文件缓存，无需登录）

接入方拿到授权后可拉取各栏目内容；帖内配图为源站混淆地址，需按本页说明自行解密。
"""
from .schema import ChannelSpec, EndpointSpec, ParamSpec, ServiceSpec

# 站点域名只有一个出处：爬虫层的 utils.BASE_URL（海角域名不固定，换域名只改那里）
from SpiderServices.haijiao.utils import BASE_URL as _SITE_BASE
_SITE_HOST = _SITE_BASE.split('://', 1)[-1]

# 帖内图片解密说明（接口原样返回混淆地址，调用方按此自行解密）
_IMAGE_NOTES = [
    'images 返回的是源站「混淆地址」，形如 https://pic.xxx.top/hjstore/images/…/<hash>_mini.jpg.txt，'
    '直接当图片引用只会拿到一段文本，必须先解密。',
    '解密步骤：① 请求该 .txt 地址，得到文本内容；'
    '② 去掉文本中所有不属于解码字母表的字符（只保留 A-Za-z0-9 与 * #，等号等一律丢弃）；'
    '③ 用字母表 "ABCD*EFGHIJKLMNOPQRSTUVWX#YZabcdefghijklmnopqrstuvwxyz1234567890" '
    '按下标取 6bit 值，每 4 个字符还原为 3 字节（末尾不足 4 个字符时按下标 0 即 A 补足）；'
    '④ 还原出的字节序列按 UTF-8 解码，得到形如 data:image/jpeg;base64,… 的 data URI，即为图片本身。',
    '说明：列表接口下发的是缩略图（文件名带 _mini）；正文原图需「帖子详情」，本期暂未开放。',
]

# 登录凭据参数（account_id 与 user_id + user_token 二选一）：需要登录态的社交 / 钱包类接口共用
_CRED_PARAMS = [
    ParamSpec('account_id', '库内账号 ID',
              desc='选填：传「账号列表」返回的 account_id；与 user_id + user_token 二选一。'),
    ParamSpec('user_id', '源站用户ID', desc='选填：发起操作的账号，与 user_token 成对使用。'),
    ParamSpec('user_token', '登录Token', desc='选填：与 user_id 成对使用。'),
]

# 头像说明（源站头像有两种形态，服务端统一补成完整地址，并给出「是否还需解码」）
_AVATAR_NOTES = [
    '头像字段（author.avatar / results[].avatar）有两种形态，服务端都已按源站规则补成完整地址，'
    '并额外给出 avatar_encrypted 标明该地址能否直接当图片用：',
    '① 用站点默认头像的用户，源站只给 0~80 的编号 → 已补成 '
    f'{_SITE_BASE}/images/common/avatar/<编号>.jpg，avatar_encrypted=false，可直接 <img src>；',
    '② 用户自定义头像，源站给的是**混淆地址**（形如 …/<hash>.txt，与帖内图片同一套）→ '
    'avatar_encrypted=true，把该地址当 url 传给本服务的「图片解码」接口即可拿到真实图片。',
]

# 「解密说明」弹窗正文：完整讲清加密图片地址的解码原理、步骤与参考代码。
# 段落内的换行会原样保留渲染，故代码片段直接写在同一个字符串里。
_IMAGE_DECRYPT_HELP = [
    '一句话原理：图片本身没有加密。源站只是把标准 base64 的字符表换成了自定义字母表'
    '（把 + 换成 *、/ 换成 #），再把整段结果存成 .txt 文件。因此「解密」= 按换过的字母表做一次 base64 解码。',

    '输入长这样（帖子里的图片地址，注意结尾是 .txt）：\n'
    '  https://pic.xxx.top/hjstore/images/20260926/ea7293d561aa00ebf62910ef501dfbe2_mini.jpg.txt\n'
    '把它下载下来，内容是类似这样的一串文本：\n'
    '  #FEyXSnnZVEl#R8oaFUlN1Ifa1T1MCutNVmtLlbDQTEB#ybC#1MGPjElR*I2...\n'
    '解码之后得到的是 data URI（图片本体就在这里）：\n'
    '  data:image/jpeg;base64,/9j/2wCEAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRof...\n'
    '把 data URI 直接赋给 <img src> 即可显示；本接口做的就是这一步（并直接把图片二进制返回）。',

    '自定义字母表（共 64 个字符，顺序即索引 0~63）：\n'
    '  ABCD*EFGHIJKLMNOPQRSTUVWX#YZabcdefghijklmnopqrstuvwxyz1234567890\n'
    '它就是标准 base64 表的变体：A-Z(26) + a-z(26) + 0-9(10) = 62 个，再加上 * 和 # 补足 64 个。',

    '完整解码步骤：\n'
    '  ① 去掉所有不属于字母表的字符（换行、空格、以及作为补位的 = 号全部丢弃）；\n'
    '  ② 从文本开头起每 4 个字符一组，用上表把每个字符换成它的下标（6 bit）；\n'
    '  ③ 4 个下标拼成 24 bit，按 8 bit 切回 3 个字节：\n'
    '     字节1 = (下标1 << 2) | (下标2 >> 4)\n'
    '     字节2 = ((下标2 & 15) << 4) | (下标3 >> 2)      ← 下标3 为「补位」时不要输出\n'
    '     字节3 = ((下标3 & 3) << 6) | 下标4              ← 下标4 为「补位」时不要输出\n'
    '  ④ 得到的字节序列按 UTF-8 解码，就是 data:image/...;base64,... 这段文本。\n'
    '  ⑤ 若末尾不足 4 个字符：按「下标 0」（即字母表首字符 A）补齐。'
    '这一步是为了与源站前端实现完全一致——它用的是 charAt 越界返回空串、indexOf("") 得 0，效果等价于补 A。',

    '为什么不能直接用标准 base64 解？\n'
    '因为字符集被换过：文本里出现的 * 和 # 在标准 base64 里不是合法字符，直接解会报错或得到乱码；'
    '反之标准表里的 + 和 / 也不会出现在这段文本里。必须换成上面那张表。',

    'Python 参考实现：\n'
    '  import re\n'
    '  ALPHABET = "ABCD*EFGHIJKLMNOPQRSTUVWX#YZabcdefghijklmnopqrstuvwxyz1234567890"\n'
    '\n'
    '  def decode_image(text: str) -> str:\n'
    '      s = re.sub(r"[^A-Za-z0-9*#]", "", text)          # ① 清洗\n'
    '      if len(s) % 4:                                   # ⑤ 末尾补齐\n'
    '          s += ALPHABET[0] * (4 - len(s) % 4)\n'
    '      out = bytearray()\n'
    '      for i in range(0, len(s), 4):                    # ②③ 每 4 字符还原 3 字节\n'
    '          a, b, c, d = (ALPHABET.index(ch) for ch in s[i:i + 4])\n'
    '          out.append(((a << 2) | (b >> 4)) & 0xFF)\n'
    '          if c != 64:\n'
    '              out.append((((b & 15) << 4) | (c >> 2)) & 0xFF)\n'
    '          if d != 64:\n'
    '              out.append((((c & 3) << 6) | d) & 0xFF)\n'
    '      return out.decode("utf-8")                       # ④ 得到 data URI 文本\n'
    '\n'
    '  # 用法：解码结果可直接作为 <img src> 使用\n'
    '  text = requests.get("https://…/xxxx_mini.jpg.txt").text\n'
    '  data_uri = decode_image(text)   # -> data:image/jpeg;base64,....',

    'JavaScript 参考实现（与源站前端同一套逻辑）：\n'
    '  function decodeImage(txt) {\n'
    '    const E = "ABCD*EFGHIJKLMNOPQRSTUVWX#YZabcdefghijklmnopqrstuvwxyz1234567890";\n'
    '    const t = txt.replace(/[^A-Za-z0-9*#]/g, "");\n'
    '    const at = (i) => (i < t.length ? E.indexOf(t.charAt(i)) : 0);  // 越界按下标 0\n'
    '    let d = "", l = 0;\n'
    '    while (l < t.length) {\n'
    '      const a = at(l++), b = at(l++), c = at(l++), e = at(l++);\n'
    '      d += String.fromCharCode((a << 2) | (b >> 4));\n'
    '      if (c !== 64) d += String.fromCharCode(((b & 15) << 4) | (c >> 2));\n'
    '      if (e !== 64) d += String.fromCharCode(((c & 3) << 6) | e);\n'
    '    }\n'
    '    return new TextDecoder("utf-8").decode(Uint8Array.from(d, (ch) => ch.charCodeAt(0)));\n'
    '  }',

    '常见坑：\n'
    '  · 字母表区分大小写，且组内顺序是「4 字符 → 3 字节」，别按标准 base64 的 +/ 去替换；\n'
    '  · .txt 内容里的 = 补位会被第 ① 步过滤掉，所以末尾通常不足 4 字符，必须按第 ⑤ 步补齐；\n'
    '  · 文件名带 _mini 的是列表页下发的缩略图，详情页下发的是原图，两者解码方式完全相同；\n'
    '  · 解码结果以 data:image/ 开头才说明解对了（解错会得到乱码或非法 UTF-8）。',

    '本接口的额外约束（防滥用）：只接受 http/https 公网地址（拒绝内网 / 回环 / 保留地址）、'
    '不跟随重定向、单张体积上限 5MB，并且校验解码结果必须是图片（data:image/*），'
    '否则返回 EXTERNAL_API_FAILED——因此它不能被当作通用网页代理使用。',
]


SERVICE = ServiceSpec(
    slug='haijiao',
    name='海角社区',
    prefix='/api/haijiao/',
    summary='海角社区服务：提供社区内容列表（热帖 / 新闻 / 大事记 / 原创 / 精华 / 最新）、帖子搜索、帖子详情与评论'
            '（含二级评论）、发帖（板块 / 标签 / 图片视频）与我的帖子（审核状态）、给帖子送金币打赏（礼物清单可选）、'
            '可直接播放的视频与图片解码，以及账号注册 / 登录、金币签到（含一键全签）与账号库管理；'
            '配图为源站混淆地址，需按文档说明解密。',
    keywords='海角社区API,海角社区热帖接口,海角帖子搜索接口,海角帖子详情接口,海角帖子评论接口,海角二级评论接口,'
             '海角视频播放接口,海角账号注册接口,海角登录接口,海角新闻接口,社区帖子接口,热帖API,'
             '海角金币签到接口,自动签到API,海角发帖接口,海角自动发帖,社区发帖API,海角我的帖子接口,帖子审核状态查询,'
             '海角打赏接口,帖子送金币接口,海角礼物接口',
    intro=[
        '海角社区服务提供社区内容数据：内容列表按栏目返回帖子标题、摘要、作者、所属板块、标签、'
        '浏览/评论/点赞等互动数据与配图（当前 6 个栏目：热帖 hot、新闻 news、大事记 events、'
        '原创 original、精华 essence、最新 latest）；搜索接口按关键词查帖并支持分页；'
        '帖子详情则返回正文、原图、视频附件、相关推荐等，评论接口分页返回楼层评论与配图'
        '（并支持「只看楼主」），二级评论接口再按主评论 ID 分页取子评论；评论正文统一去掉了源站的 HTML 标签，'
        '只返回纯文本（配图地址在 images 字段）。',
        '发帖能力提供完整链路：板块列表（层级）与标签池取选择项 → 上传图片 / 视频拿到附件与正文片段 → '
        '提交发帖（标题 / 正文 / 板块 / 标签 / 媒体），并可用「我的帖子」按审核状态查看发布成功 / 审核中 / '
        '审核失败的帖子（含审核失败原因）。发帖需带源站登录态（库内账号或自定义 id + token）；'
        '源站对所有新帖走人工审核，提交成功即返回成功、审核通过后才对外可见。',
        '另外提供两类「可直接使用」的能力：图片解码（把混淆图片地址转成真实图片）与视频播放列表'
        '（已还原源站真密钥的 m3u8）；以及账号能力——两步式注册（验证码先人工识别）、账号登录、'
        '每日金币签到（单账号签到与一键全部账号签到），注册成功的账号会自动写入本服务的账号库，'
        '账号库提供增删改查接口；打赏能力则按「礼物清单 + 给帖子送金币」两步完成'
        '（礼物是现买现送，按单价扣金币 / 钻石）。',
        '本服务为公开数据实时爬取 + 文件缓存，无需登录；各栏目内容随时间变动，缓存时间较短'
        '以便及时反映更新。本服务需项目签名。',
        '注意：帖内配图为源站混淆地址（形如 …/<hash>_mini.jpg.txt，内容是自定义字母表 base64 编码的'
        ' data URI），需按各接口的说明自行解密后才能展示；帖内视频的播放地址需登录态，'
        '详情接口会用服务端配置的账号解析出 m3u8（匿名调用时为空）。',
    ],
    # 带 account_id 参数的端点会自动渲染「账号选择器」（搜库内账号一键填入）
    account_search_path='/api/haijiao/accounts',
    channels=[
        ChannelSpec(
            slug='haijiao',
            name='海角社区',
            provider=f'海角社区（{_SITE_HOST}）',
            auth_note='auth',
            note='实时爬取源站公开接口并缓存（无需登录）。各栏目内容随时间变动，缓存时间较短。',
            endpoints=[
                EndpointSpec('topics', '内容列表', 'GET',
                             '/api/haijiao/topics',
                             summary='按栏目获取社区内容列表，支持分页。',
                             params=[
                                 ParamSpec('tab', '栏目', kind='select', default='hot',
                                           options=[
                                               {'value': 'hot', 'label': '热帖'},
                                               {'value': 'news', 'label': '新闻'},
                                               {'value': 'events', 'label': '大事记'},
                                               {'value': 'original', 'label': '原创'},
                                               {'value': 'essence', 'label': '精华'},
                                               {'value': 'latest', 'label': '最新'},
                                           ],
                                           desc='可选：栏目，默认 hot（热帖）。'),
                                 ParamSpec('page', '页码', kind='number', default='1',
                                           placeholder='1',
                                           desc='可选：页码，从 1 开始，默认 1（源站每页 20 条）。'),
                             ],
                             notes=[
                                 '返回 data.tab（当前栏目）、data.results（帖子列表）与 data.pagination'
                                 '（分页信息：page / page_size / total / total_page）。',
                                 '每条帖子含 topic_id、title、excerpt、node（板块）、tags（标签）、'
                                 'author（作者）、images（配图）、has_video、money_type、'
                                 'view_count / comment_count / like_count、create_time、last_comment_time。',
                                 'tab 非法返回 PARAM_VALUE_INVALID；page 非整数返回 PARAM_FORMAT_ERROR，'
                                 '小于 1 返回 PARAM_VALUE_INVALID。',
                                 '配图解密（重要）：',
                             ] + _IMAGE_NOTES),
                EndpointSpec('search', '搜索', 'GET',
                             '/api/haijiao/search',
                             summary='按关键词搜索帖子，支持分页与板块筛选。',
                             params=[
                                 ParamSpec('key', '搜索关键词', required=True,
                                           placeholder='学生妹',
                                           desc='必填：搜索关键词。'),
                                 ParamSpec('type', '搜索范围', kind='select', default='1',
                                           options=[
                                               {'value': '1', 'label': '帖子'},
                                           ],
                                           desc='可选：搜索范围，目前仅支持 1（帖子），默认 1。'),
                                 ParamSpec('node_id', '板块 ID', kind='number', default='0',
                                           placeholder='0',
                                           desc='可选：限定板块 ID，0 表示不限板块（板块 ID 见列表结果 results[].node.id），默认 0。'),
                                 ParamSpec('page', '页码', kind='number', default='1',
                                           placeholder='1',
                                           desc='可选：页码，从 1 开始，默认 1（源站每页 20 条）。'),
                             ],
                             notes=[
                                 '返回 data.key / data.node_id / data.results（帖子列表，字段与「内容列表」一致）'
                                 '与 data.pagination（分页信息：page / page_size / total / total_page）。',
                                 'key 缺失返回 PARAM_MISSING；type 非 1 返回 PARAM_VALUE_INVALID；'
                                 'node_id 非整数返回 PARAM_FORMAT_ERROR、小于 0 返回 PARAM_VALUE_INVALID；'
                                 'page 非整数返回 PARAM_FORMAT_ERROR、小于 1 返回 PARAM_VALUE_INVALID。',
                                 '无匹配结果时 data.results 为空数组，不报错。',
                                 '配图解密（重要，图片字段与内容列表同源）：',
                             ] + _IMAGE_NOTES),
                EndpointSpec('topic_detail', '帖子详情', 'GET',
                             '/api/haijiao/topic/detail',
                             summary='获取单个帖子的详情：正文、原图、视频附件、互动数据与相关推荐。',
                             params=[
                                 ParamSpec('topic_id', '帖子 ID', required=True,
                                           placeholder='2271652',
                                           desc='必填：帖子 ID（取自「内容列表」的 results[].topic_id）。'),
                                 ParamSpec('user_id', '登录账号 ID',
                                           placeholder='（选填，自己的海角账号 ID）',
                                           desc='可选：用自己的账号 ID 覆盖默认凭据（需与 user_token 成对），'
                                                '用于获取视频等需登录态的内容。'),
                                 ParamSpec('user_token', '登录 Token',
                                           placeholder='（选填，登录后的 token）',
                                           desc='可选：与 user_id 成对提供。注意 token 走查询串会留在访问日志，请酌情使用。'),
                             ],
                             notes=[
                                 '返回 data 含：topic_id / title / excerpt / node / tags / author / '
                                 'content（正文 HTML）/ images（原图地址）/ videos（视频附件）/ has_video / '
                                 '互动数据 / 时间 / related（相关推荐）。',
                                 'content 为源站正文 HTML（原样返回）：其中 <img> 指向混淆图片地址、'
                                 '<video> 的 src 为空占位。图片请优先用 data.images，正文 HTML 未做改写。',
                                 '视频：videos[].url 是源站原始 m3u8，**不能直接播放**（源站密钥是假的，标准播放器会因'
                                 '分片解密失败报 fragParsingError），且随登录态下发（匿名时为空串）。'
                                 '请改用 videos[].play_url —— 那是本服务的「视频播放列表」接口，已还原真密钥，'
                                 '可直接喂给 hls.js 等播放器。',
                                 '图片同理：images 里的加密地址可交给本服务的「图片解码」接口，'
                                 '直接得到真实图片（见该接口的说明）。',
                                 'topic_id 缺失返回 PARAM_MISSING、非数字返回 PARAM_FORMAT_ERROR；'
                                 'user_id / user_token 只传其一返回 PARAM_MISSING；帖子不存在返回 EXTERNAL_API_FAILED。',
                                 '作者头像（author.avatar / avatar_encrypted）说明：',
                                 '配图解密（重要）：',
                             ] + _AVATAR_NOTES + _IMAGE_NOTES),
                EndpointSpec('topic_comments', '帖子评论列表', 'GET',
                             '/api/haijiao/topic/comments',
                             summary='分页获取帖子的评论（按楼层倒序，最新在前），可按「只看楼主」筛选。',
                             params=[
                                 ParamSpec('topic_id', '帖子 ID', required=True, placeholder='2272780',
                                           desc='必填：帖子 ID（取自「内容列表」的 results[].topic_id）。'),
                                 ParamSpec('page', '页码', kind='number', default='1',
                                           desc='选填：从 1 开始，默认 1（源站每页 20 条）。'),
                                 ParamSpec('search_type', '筛选', kind='select', default='0',
                                           options=[{'value': '0', 'label': '0（全部，默认）'},
                                                    {'value': '1', 'label': '1（只看楼主）'}],
                                           desc='选填：与源站评论区的「看全部 / 看楼主」两个 tab 一致。'),
                             ],
                             notes=[
                                 '返回 data：topic_id / search_type / pagination（page、page_size、total、'
                                 'total_page）/ results（评论数组）。',
                                 '按楼层**倒序**返回（最新评论在前），源站每页 20 条。',
                                 'results[] 字段：comment_id、floor（楼层）、**content（纯文本正文）**、'
                                 'images（配图加密地址）、author（id / nickname / **avatar / avatar_encrypted** / '
                                 'vip / famous / certified）、like_count、liked（我是否点过赞）、'
                                 'reply_count（子评论总数）、'
                                 'replies（源站随本条内联下发的子评论，只作预览）、create_time / pretty_time。',
                                 'content 已由服务端**去掉全部 HTML 标签**（源站下发的是 '
                                 '<html><body><p>…</p></body></html> 形式的富文本）：只留可读文字，'
                                 '块级标签与 <br> 转成换行，HTML 实体已还原。因此正文里的图片位置信息不再保留——'
                                 '配图请用同一条的 images 字段（源站混淆地址，形如 …/<hash>.jpg.txt，'
                                 '与帖内配图同一套），交给本服务的「图片解码」接口即可得到真实图片。',
                                 '需要某条主评论下的**完整子评论列表**（可翻页）时，用「二级评论」接口'
                                 '（comment_id 取本接口结果里的 comment_id）。',
                                 '本接口按调用方登录态返回 liked；匿名调用时恒为 false（默认凭据见服务说明）。',
                                 'topic_id 缺失返回 PARAM_MISSING、非数字返回 PARAM_FORMAT_ERROR；'
                                 'page 非数字 / 小于 1 返回 PARAM_FORMAT_ERROR / PARAM_VALUE_INVALID；'
                                 'search_type 非 0 / 1 返回 PARAM_VALUE_INVALID；帖子不存在返回 EXTERNAL_API_FAILED。',
                                 '作者头像（author.avatar / avatar_encrypted）说明：',
                             ] + _AVATAR_NOTES),
                EndpointSpec('comment_replies', '二级评论列表', 'GET',
                             '/api/haijiao/comment/replies',
                             summary='分页获取某条主评论下的二级评论（子评论）。',
                             params=[
                                 ParamSpec('comment_id', '主评论 ID', kind='number', required=True,
                                           placeholder='51081038',
                                           desc='必填：主评论 ID（取自「帖子评论列表」的 results[].comment_id）。'),
                                 ParamSpec('page', '页码', kind='number', default='1',
                                           desc='选填：从 1 开始，默认 1（源站每页 20 条）。'),
                             ],
                             notes=[
                                 '源站里子评论是**单独接口**（按主评论 ID 查），主评论列表里内联的 replies '
                                 '只适合预览；要看完整 / 翻页子评论用本接口。',
                                 '返回 data：comment_id（主评论 ID）/ pagination（page、page_size、total、'
                                 'total_page）/ results（子评论数组）。',
                                 'results[] 字段：comment_id（本条评论 ID）、root_comment_id（所属主评论 ID）、'
                                 'parent_comment_id（**直接回复的那条评论 ID**，0 表示直接回复主评论，'
                                 '即标准「二级评论」）、author（id / nickname / **avatar / avatar_encrypted** / '
                                 'vip / famous / certified）、**content（纯文本）**、quote（被引用的内容，'
                                 '通常为空）、'
                                 'like_count、liked、reply_count（本条自己的子回复数）、last_replies'
                                 '（源站内联的最新一条子回复预览）、create_time / pretty_time。',
                                 '返回的是**扁平列表**：同一主评论下的各层级混在一起，层级关系靠 '
                                 'root_comment_id / parent_comment_id 两个 ID 自行组装（源站不做树形返回）。',
                                 '源站字段里另有 title（用户头衔对象）等展示信息，与业务无关，未收录。',
                                 'comment_id 缺失返回 PARAM_MISSING、非数字返回 PARAM_FORMAT_ERROR；'
                                 'page 非数字 / 小于 1 返回 PARAM_FORMAT_ERROR / PARAM_VALUE_INVALID；'
                                 '源站异常返回 EXTERNAL_API_FAILED。',
                                 '作者头像（author.avatar / avatar_encrypted）说明：',
                             ] + _AVATAR_NOTES),
                EndpointSpec('topic_nodes', '板块列表', 'GET',
                             '/api/haijiao/topic/nodes',
                             summary='获取发帖可选板块（按层级返回 children，供联动选择）。',
                             params=[],
                             notes=[
                                 '无参数：返回 data.list 为**顶层板块数组**，每个板块含 node_id / name / icon / '
                                 'description / vip_limit / display / children（子板块同结构，可嵌套多层）。',
                                 '发帖时传所选**叶子板块**的 node_id（见「发帖」接口）。',
                                 '板块属站点级公共数据，服务端缓存，变更不频繁。',
                             ]),
                EndpointSpec('topic_tags', '标签池', 'GET',
                             '/api/haijiao/topic/tags',
                             summary='分页获取发帖可选标签（源站标签池，每页 20 条，最新在前）。',
                             params=[
                                 ParamSpec('page', '页码', kind='number', default='1',
                                           desc='选填：从 1 开始，默认 1（源站每页 20 条）。'),
                             ],
                             notes=[
                                 '返回 data.pagination 与 data.results（每项 tag_id / tag_name）。',
                                 '源站该接口**不支持关键词搜索**（前端只在已加载的一页里本地过滤），只能翻页；'
                                 '调用方若需要搜索，可在本页结果里自行过滤，或直接用标签名发帖。',
                                 '发帖的 tags 参数传**标签名**（不是 tag_id）：不在池中的名称会被源站当作新标签，'
                                 '因此自定义标签直接写名称即可。',
                                 'page 非数字 / 小于 1 返回 PARAM_FORMAT_ERROR / PARAM_VALUE_INVALID。',
                             ]),
                EndpointSpec('topic_upload', '上传发帖媒体', 'POST',
                             '/api/haijiao/topic/upload',
                             summary='上传发帖用的图片 / 视频，返回附件 ID 与可直接嵌入正文的 HTML 片段。',
                             params=[
                                 ParamSpec('file', '媒体文件', kind='file', required=True,
                                           accept='image/*,video/mp4',
                                           desc='必填：图片（png/jpg/jpeg/gif/bmp，单张 ≤10MB）或视频（mp4）。'),
                                 ParamSpec('account_id', '库内账号 ID',
                                           desc='选填：传「账号列表」返回的 account_id；与 user_id + user_token 二选一。'),
                                 ParamSpec('user_id', '源站用户ID', desc='选填：与 user_token 成对使用。'),
                                 ParamSpec('user_token', '登录Token', desc='选填：与 user_id 成对使用。'),
                             ],
                             notes=[
                                 '本接口是 **multipart/form-data**，文件字段名为 file（页面在线调试可直接选文件）。',
                                 '源站把图片与视频放在同一个上传接口，靠返回的 category 区分类型（images / video）。',
                                 '返回 data.html **就是可直接拼进发帖 content 的片段**：'
                                 '图片为 <img src="真实地址" data-id="附件ID"/>，'
                                 '视频为 <video src="" data-id="附件ID"></video>（源站正文里视频只留空 src 占位）。',
                                 '图片的 data.url 已去掉源站下发的 _mini 缩略图后缀（正文用的是原图地址）；'
                                 '视频没有独立地址，url 为空串。',
                                 '上传只产生附件、不会自动带进帖子：正文里靠 data-id 关联，未发帖的附件可忽略。',
                                 '格式不支持 / 图片超过 10MB 返回 PARAM_VALUE_INVALID；未选文件 / 凭据缺失返回 '
                                 'PARAM_MISSING；账号不存在返回 NOT_FOUND（20030）。',
                             ]),
                EndpointSpec('topic_create', '发帖', 'POST',
                             '/api/haijiao/topic/create',
                             summary='发布帖子（板块 / 标签 / 标题 / 正文 / 图片视频）。',
                             params=[
                                 ParamSpec('node_id', '板块 ID', kind='number', required=True,
                                           placeholder='179',
                                           desc='必填：板块 ID（取自「板块列表」的叶子节点 node_id）。'),
                                 ParamSpec('title', '标题', required=True,
                                           desc='必填：标题，源站上限 36 字。'),
                                 ParamSpec('content', '正文', kind='textarea', required=True,
                                           placeholder='<p>正文…</p><img src="…" data-id="14166286"/>',
                                           desc='必填：正文 HTML；图片 / 视频片段用「上传发帖媒体」返回的 data.html 拼接。'),
                                 ParamSpec('tags', '标签', required=True,
                                           placeholder='测试,接口联调',
                                           desc='必填：标签名，多个用英文（或中文）逗号分隔；不存在的名称会被源站当作新标签。'),
                                 ParamSpec('type', '帖子类型', kind='select', default='0',
                                           options=[{'value': '0', 'label': '0（普通，默认）'},
                                                    {'value': '1', 'label': '1（出售）'},
                                                    {'value': '2', 'label': '2（悬赏）'}],
                                           desc='选填：默认普通贴。'),
                                 ParamSpec('money_type', '货币类型', kind='select', default='0',
                                           options=[{'value': '0', 'label': '0（金币，默认）'},
                                                    {'value': '1', 'label': '1（钻石）'}],
                                           desc='选填：仅出售 / 悬赏有意义。'),
                                 ParamSpec('amount', '价格 / 悬赏金额', kind='number', default='0',
                                           desc='选填：默认 0；源站前端对金币按 ×100 换算（服务端已同口径处理）。'),
                                 ParamSpec('reward_hours', '悬赏时长', kind='number', default='0',
                                           desc='选填：仅悬赏贴，需 72-240 的整数。'),
                                 ParamSpec('account_id', '库内账号 ID',
                                           desc='选填：传「账号列表」返回的 account_id；与 user_id + user_token 二选一。'),
                                 ParamSpec('user_id', '源站用户ID', desc='选填：与 user_token 成对使用。'),
                                 ParamSpec('user_token', '登录Token', desc='选填：与 user_id 成对使用。'),
                             ],
                             notes=[
                                 '发布必须带登录态：用 account_id（库内账号），或直传 user_id + user_token。',
                                 '**源站对所有新帖走人工审核**：提交成功时返回 data.pending=true 且 data.topic_id 通常为空，'
                                 '此时源站前端提示「发布成功，待审核通过后便可查看」——这不是失败。'
                                 '审核通过后 topic_id 才是可访问的帖子 ID（`/post/details?pid=<topic_id>`）。',
                                 '源站有发帖频率风控：短时间内重复发帖会直接失败并提示'
                                 '「请勿灌水，耐心等待4分钟再操作吧」，请控制频率。',
                                 '发布前服务端会按源站前端的做法先查询一次人机验证：若源站要求验证（滑块拼图），'
                                 '接口会直接返回错误——滑块必须人工完成，本服务无法代过，请换账号或稍后重试。',
                                 '正文里的图片 / 视频必须先用「上传发帖媒体」上传并拿到 data.html 片段再拼进来；'
                                 '只写 <img> 而没有对应 attachment 不会生效。',
                                 'node_id / title / content / tags 缺失返回 PARAM_MISSING；title 超过 36 字、'
                                 'type 不在 0-2、reward_hours 不在 72-240 等返回 PARAM_VALUE_INVALID；'
                                 '账号不存在返回 NOT_FOUND（20030）。',
                             ],
                             tool_path='/haijiao/post/',
                             tool_label='去发帖页发布'),
                EndpointSpec('topic_mine', '我的帖子', 'GET',
                             '/api/haijiao/topic/mine',
                             summary='查看自己账号的帖子：发布成功 / 审核中 / 审核失败（含审核失败原因）。',
                             params=[
                                 ParamSpec('status', '审核状态', kind='select', default='published',
                                           options=[{'value': 'published', 'label': 'published（审核通过，默认）'},
                                                    {'value': 'pending', 'label': 'pending（审核中）'},
                                                    {'value': 'rejected', 'label': 'rejected（审核失败）'}],
                                           desc='选填：与源站「我的帖子」页三个 tab 一致。'),
                                 ParamSpec('page', '页码', kind='number', default='1',
                                           desc='选填：从 1 开始，默认 1（源站每页 10 条）。'),
                                 ParamSpec('account_id', '库内账号 ID',
                                           desc='选填：传「账号列表」返回的 account_id；与 user_id + user_token 二选一。'),
                                 ParamSpec('user_id', '源站用户ID', desc='选填：与 user_token 成对使用。'),
                                 ParamSpec('user_token', '登录Token', desc='选填：与 user_id 成对使用。'),
                             ],
                             notes=[
                                 '必须带登录态：用 account_id（库内账号），或直传 user_id + user_token。',
                                 '返回 data.status（语义化取值）、data.pagination（page / page_size / total / total_page）'
                                 '与 data.results（帖子数组）。',
                                 'results[] 字段与「内容列表」基本一致（topic_id / title / excerpt / node / tags / '
                                 'author / images / 互动数据 / 时间），另加：pending_id（待审 ID）、source_status'
                                 '（源站状态码）、**remarks（审核失败原因）**、has_pic / has_video / has_audio、'
                                 'is_top / is_cream / is_original。',
                                 '三种状态的区别：published 与 pending 的条目有 topic_id，可拼成 '
                                 f'{_SITE_BASE}/post/details?pid=<topic_id>；rejected 的条目 topic_id 为空、'
                                 '只有 pending_id，失败原因见 remarks（源站人工审核给的说明）。',
                                 '源站状态码对应关系：published=3 / pending=2 / rejected=4（服务端已转换，调用方无需关心）。',
                                 'status 非三种取值返回 PARAM_VALUE_INVALID；page 非数字 / 小于 1 返回 '
                                 'PARAM_FORMAT_ERROR / PARAM_VALUE_INVALID；凭据缺失返回 PARAM_MISSING；'
                                 '账号不存在返回 NOT_FOUND（20030）。',
                             ]),
                EndpointSpec('gift_list', '礼物列表', 'GET',
                             '/api/haijiao/gift/list',
                             summary='打赏可选的礼物清单（金币 / 钻石礼物），含各自价格。',
                             params=[
                                 ParamSpec('kind', '礼物类型', kind='select', default='gold',
                                           options=[{'value': 'gold', 'label': 'gold（金币礼物，默认）'},
                                                    {'value': 'diamond', 'label': 'diamond（钻石礼物）'}],
                                           desc='选填：与源站打赏弹窗的两个 tab 一一对应。'),
                                 ParamSpec('page', '页码', kind='number', default='1',
                                           desc='选填：从 1 开始，默认 1。'),
                             ],
                             notes=[
                                 '礼物是站点级公共数据，无需登录；一次取回该类型全部礼物（源站礼物很少）。',
                                 '返回 data：kind / pagination（page、page_size、total、total_page）/ results。',
                                 'results[] 字段：item_id（礼物 ID，打赏时传它）、name、desc、kind、'
                                 'money_type（1=金币 2=钻石）、price（原价）、**sale_price（实际单价）**、'
                                 'img、expire_time、vip_limit。',
                                 '实际花费 = sale_price × 赠送数量（源站前端同样按 sale_price 计费）。',
                                 '当前金币礼物里最便宜的是 item_id=1「棒棒糖」（5 金币）。',
                                 'kind 非两种取值返回 PARAM_VALUE_INVALID；page 非数字 / 小于 1 返回 '
                                 'PARAM_FORMAT_ERROR / PARAM_VALUE_INVALID。',
                             ],
                             gift_picker_path='/api/haijiao/gift/list'),
                EndpointSpec('topic_give', '给帖子送金币（打赏）', 'GET',
                             '/api/haijiao/topic/give',
                             summary='给帖子的作者赠送一份礼物（默认最便宜的那个），即站点的「打赏」。',
                             params=[
                                 ParamSpec('topic_id', '帖子 ID', kind='number', required=True,
                                           placeholder='2274377',
                                           desc='必填：帖子 ID（取自「内容列表」/「帖子详情」的 topic_id）。'),
                                 ParamSpec('item_id', '礼物 ID', kind='number',
                                           desc='选填：取自「礼物列表」的 item_id；不传则自动选该类型里最便宜的礼物。'),
                                 ParamSpec('quantity', '赠送数量', kind='number', default='1',
                                           desc='选填：默认 1、最大 99；实际花费 = 礼物单价 × 数量。'),
                                 ParamSpec('kind', '礼物类型', kind='select', default='gold',
                                           options=[{'value': 'gold', 'label': 'gold（金币礼物，默认，扣金币）'},
                                                    {'value': 'diamond', 'label': 'diamond（钻石礼物，扣钻石）'}],
                                           desc='选填：与源站打赏弹窗的两个 tab 一一对应。'),
                                 ParamSpec('account_id', '库内账号 ID',
                                           desc='选填：传「账号列表」返回的 account_id；与 user_id + user_token 二选一。'),
                                 ParamSpec('user_id', '源站用户ID', desc='选填：与 user_token 成对使用。'),
                                 ParamSpec('user_token', '登录Token', desc='选填：与 user_id 成对使用。'),
                             ],
                             notes=[
                                 '收礼人 = 帖子作者（源站打赏弹窗传的就是作者的用户 ID），服务端自动解析，'
                                 '调用方只需给帖子 ID。',
                                 '礼物是「现买现送」：账号不需要事先拥有该礼物，直接按单价扣金币 / 钻石。',
                                 '**会真实扣费**：每次调用都会花掉 total_cost 个金币 / 钻石，同一帖子可重复打赏，'
                                 '请确认后再调。',
                                 '必须带登录态：用 account_id（库内账号），或直传 user_id + user_token。',
                                 '返回 data：topic_id / item（所赠礼物）/ quantity / total_cost（本次花费）/ '
                                 'receiver（收礼的作者 user_id、nickname）/ money（赠送后余额）。',
                                 'topic_id 缺失返回 PARAM_MISSING、非数字返回 PARAM_FORMAT_ERROR；quantity 非数字 / '
                                 '小于 1 / 大于 99 返回 PARAM_FORMAT_ERROR / PARAM_VALUE_INVALID；帖子不存在、'
                                 '礼物不存在、金币不足等源站拒绝返回 EXTERNAL_API_FAILED（以错误消息区分）。',
                             ],
                             gift_picker_path='/api/haijiao/gift/list'),
                EndpointSpec('user_follow', '关注 / 取消关注用户', 'GET',
                             '/api/haijiao/user/follow',
                             summary='关注某个用户，或取消对 TA 的关注（相当于个人主页的「关注」按钮）。',
                             params=[
                                 ParamSpec('target_user_id', '目标用户ID', kind='number', required=True,
                                           placeholder='13820512',
                                           desc='必填：目标用户 ID，即个人主页地址里的那段数字'
                                                f'（{_SITE_BASE}/homepage/<user_id>）。'),
                                 ParamSpec('action', '动作', kind='select', default='follow',
                                           options=[{'value': 'follow', 'label': 'follow（关注，默认）'},
                                                    {'value': 'unfollow', 'label': 'unfollow（取消关注）'}],
                                           desc='选填：关注按钮的两种状态。'),
                                 ParamSpec('account_id', '库内账号 ID',
                                           desc='选填：传「账号列表」返回的 account_id；与 user_id + user_token 二选一。'),
                                 ParamSpec('user_id', '源站用户ID',
                                           desc='选填：发起关注的账号（注意不是目标用户），与 user_token 成对使用。'),
                                 ParamSpec('user_token', '登录Token', desc='选填：与 user_id 成对使用。'),
                             ],
                             notes=[
                                 '必须带登录态：用 account_id（库内账号），或直传 user_id + user_token。',
                                 '返回 data：target_user_id / action（follow / unfollow）/ followed（操作后的关注状态）。',
                                 '源站成功时只回状态（没有数据体），因此返回里没有对方的昵称等信息。',
                                 '不能关注自己；重复关注会失败（错误消息「你已关注此用户」），'
                                 '取关未关注的用户同样失败（「用户并未关注被取消的用户」），都返回 EXTERNAL_API_FAILED。',
                                 'target_user_id 缺失返回 PARAM_MISSING、非数字 / 小于 1 返回 '
                                 'PARAM_FORMAT_ERROR / PARAM_VALUE_INVALID；action 非两种取值返回 PARAM_VALUE_INVALID；'
                                 '凭据缺失返回 PARAM_MISSING；账号不存在返回 NOT_FOUND（20030）。',
                             ]),
                EndpointSpec('user_follow_batch', '批量关注 / 取消关注', 'POST',
                             '/api/haijiao/user/follow/batch',
                             summary='让账号库里全部账号，都对同一个目标用户执行关注（或取关）。',
                             params=[
                                 ParamSpec('target_user_id', '目标用户ID', kind='number', required=True,
                                           placeholder='13820512',
                                           desc='必填：目标用户 ID，即个人主页地址里的那段数字'
                                                f'（{_SITE_BASE}/homepage/<user_id>）。'),
                                 ParamSpec('action', '动作', kind='select', default='follow',
                                           options=[{'value': 'follow', 'label': 'follow（批量关注，默认）'},
                                                    {'value': 'unfollow', 'label': 'unfollow（批量取关）'}],
                                           desc='选填：对全部账号执行的动作。'),
                             ],
                             notes=[
                                 '不用传凭据：直接用账号库里每个账号自己的登录态执行，遍历范围是**全部库内账号**。',
                                 '没有 token 的账号（无法登录）与「目标就是该账号自己」的账号都计入 skipped 并注明原因，'
                                 '不发起请求。',
                                 '逐个**串行**执行、不并发；单个账号失败不影响其它账号。整批比较慢，'
                                 '请把客户端超时留够：单次关注请求实测 1.7~2.7 秒，10 个以上账号整体约 20~30 秒。',
                                 '已经是目标状态（已关注 / 本来就没关注）计入 already，不记为失败。',
                                 '返回 data：target_user_id / action / total / success_count / already_count / '
                                 'skipped_count / failed_count / items（逐账号的 account_id、user_id、username、'
                                 'state（done / already / skipped / failed）、message）。',
                                 '**风控提醒**：一次让大量账号关注同一目标属于明显异常行为，源站可能限制甚至封号，'
                                 '请自行控制频率；需要更保守可改用「关注 / 取消关注用户」逐个、间隔执行。',
                                 'target_user_id 缺失返回 PARAM_MISSING、非数字 / 小于 1 返回 '
                                 'PARAM_FORMAT_ERROR / PARAM_VALUE_INVALID；action 非两种取值返回 PARAM_VALUE_INVALID。',
                             ]),
                EndpointSpec('ranking', '排行榜', 'GET',
                             '/api/haijiao/ranking',
                             summary='首页排行榜：粉丝榜 / 点赞榜 / 人气榜，每个榜单另有总榜 / 月榜 / 周榜。',
                             params=[
                                 ParamSpec('board', '榜单维度', kind='select', default='fans',
                                           options=[{'value': 'fans', 'label': 'fans（粉丝榜，默认）'},
                                                    {'value': 'liked', 'label': 'liked（点赞榜）'},
                                                    {'value': 'wealth', 'label': 'wealth（人气榜）'}],
                                           desc='选填：与源站首页排行榜的 tab 一一对应。'),
                                 ParamSpec('period', '榜单周期', kind='select', default='all',
                                           options=[{'value': 'all', 'label': 'all（总榜，默认）'},
                                                    {'value': 'month', 'label': 'month（月榜，近 30 天）'},
                                                    {'value': 'week', 'label': 'week（周榜，近 7 天）'}],
                                           desc='选填：榜单统计的时间范围。'),
                             ],
                             notes=[
                                 '公开数据、无需登录；源站**一次返回整张榜单、不翻页**'
                                 '（实测粉丝 / 点赞 / 人气榜约 101 条，冷门维度与周榜可能更少）。',
                                 '返回 data：board / board_label / period / period_label / total / results。',
                                 'results[] 字段：rank（名次）、user_id、nickname、avatar（头像地址）、'
                                 '**avatar_encrypted（该头像是否需要解码）**、vip / famous / certified、'
                                 '**value（该榜单的数值：粉丝数 / 点赞数 / 人气值）**、'
                                 'title（用户头衔：id / name / icon）。',
                                 f'每位用户的主页地址为 {_SITE_BASE}/homepage/<user_id>，'
                                 '需要看 TA 的帖子可用「关注 / 取消关注用户」同款的用户 ID。',
                                 '源站首页排行榜还有**消费榜**（consume），本服务未开放。',
                                 'board、period 传入约定外的取值都返回 PARAM_VALUE_INVALID（20003）。',
                                 '头像说明：',
                             ] + _AVATAR_NOTES),
                EndpointSpec('user_info', '用户主页信息', 'GET',
                             '/api/haijiao/user/info',
                             summary='按用户 ID 查一个人的主页信息：昵称、头像、签名、发帖数、粉丝数、我是否已关注。',
                             params=[
                                 ParamSpec('target_user_id', '目标用户ID', kind='number', required=True,
                                           placeholder='13820512',
                                           desc='必填：目标用户 ID（个人主页 /homepage/<user_id> 里的数字）。'),
                             ] + _CRED_PARAMS,
                             notes=[
                                 '查别人主页**不需要登录**；但 is_followed（我是否已关注 TA）跟着调用方账号走，'
                                 '不带凭据时恒为 false。',
                                 '返回 data：user_id / nickname / avatar / avatar_encrypted / description（个性签名）/ '
                                 'fans_count（粉丝数）/ vip / famous / certified / is_followed / topic_count（发帖数）/ '
                                 'video_count / comment_count / favorite_count / like_count。',
                                 '排行榜、评论、帖子详情里都只有 user_id 和昵称，想了解「这个人是谁」就用本接口。',
                                 '配合「关注 / 取消关注用户」可完成「查人 → 关注」的闭环。',
                                 'target_user_id 缺失返回 PARAM_MISSING、非数字 / 小于 1 返回 '
                                 'PARAM_FORMAT_ERROR / PARAM_VALUE_INVALID；用户不存在返回 EXTERNAL_API_FAILED。',
                                 '头像说明（author.avatar / results[].avatar）：',
                             ] + _AVATAR_NOTES),
                EndpointSpec('user_wealth', '账号余额', 'GET',
                             '/api/haijiao/user/wealth',
                             summary='查当前账号的金币 / 钻石余额（打赏、签到的配套）。',
                             params=[] + _CRED_PARAMS,
                             notes=[
                                 '必须带登录态：用 account_id（库内账号），或直传 user_id + user_token。',
                                 '返回 data：gold（金币）/ diamond（钻石）。',
                                 '打赏（给帖子送金币）前可先用本接口确认余额够不够，避免提交后才被源站拒绝。',
                                 '凭据缺失返回 PARAM_MISSING；账号不存在返回 NOT_FOUND（20030）。',
                             ]),
                EndpointSpec('user_wealth_log', '金币 / 钻石流水', 'GET',
                             '/api/haijiao/user/wealth/log',
                             summary='查当前账号的金币 / 钻石收支流水（分页，最新在前）。',
                             params=[
                                 ParamSpec('kind', '流水类型', kind='select', default='gold',
                                           options=[{'value': 'gold', 'label': 'gold（金币，默认）'},
                                                    {'value': 'diamond', 'label': 'diamond（钻石）'}],
                                           desc='选填：金币与钻石是两套流水。'),
                                 ParamSpec('page', '页码', kind='number', default='1',
                                           desc='选填：从 1 开始，默认 1（源站每页 20 条）。'),
                             ] + _CRED_PARAMS,
                             notes=[
                                 '必须带登录态：用 account_id（库内账号），或直传 user_id + user_token。',
                                 '返回 data：kind / pagination（page、page_size、total、total_page）/ results。',
                                 'results[] 字段：amount（正数=收入、负数=支出）、balance_after（变动后余额）、'
                                 'time、description（如「购买赠送物品[1-棒棒糖]1件赠送给[…]」「任务:每日签到」）。',
                                 '打赏 / 签到是否真的到账，用本接口核对最直接。',
                                 'kind 非两种取值返回 PARAM_VALUE_INVALID；page 非数字 / 小于 1 返回 '
                                 'PARAM_FORMAT_ERROR / PARAM_VALUE_INVALID；凭据缺失返回 PARAM_MISSING。',
                             ]),
                EndpointSpec('user_following', '我关注的人', 'GET',
                             '/api/haijiao/user/following',
                             summary='列出当前账号关注了哪些人（源站一次返回全部、不翻页）。',
                             params=[] + _CRED_PARAMS,
                             notes=[
                                 '必须带登录态：用 account_id（库内账号），或直传 user_id + user_token。',
                                 '返回 data：total / results（用户名片数组）。',
                                 'results[] 字段与「用户主页信息」一致：user_id / nickname / avatar / '
                                 'avatar_encrypted / description / fans_count / vip / famous / certified / is_followed。',
                                 '源站**不分页**，一次全给；关注人数很多时响应会比较大。',
                                 '提醒：列表项里的 is_followed 实测源站恒返回 false（列表里的人本来就是已关注），'
                                 '别用它做判断；「用户主页信息」里的 is_followed 才可信。',
                                 '凭据缺失返回 PARAM_MISSING；账号不存在返回 NOT_FOUND（20030）。',
                             ]),
                EndpointSpec('user_fans', '我的粉丝', 'GET',
                             '/api/haijiao/user/fans',
                             summary='分页列出当前账号的粉丝。',
                             params=[
                                 ParamSpec('page', '页码', kind='number', default='1',
                                           desc='选填：从 1 开始，默认 1（源站每页 20 条）。'),
                             ] + _CRED_PARAMS,
                             notes=[
                                 '必须带登录态：用 account_id（库内账号），或直传 user_id + user_token。',
                                 '返回 data：pagination / results（用户名片数组，字段同「我关注的人」）。',
                                 '粉丝数可在「用户主页信息」的 fans_count 里直接看到，本接口用来翻具体是谁。',
                                 'page 非数字 / 小于 1 返回 PARAM_FORMAT_ERROR / PARAM_VALUE_INVALID；'
                                 '凭据缺失返回 PARAM_MISSING。',
                             ]),
                EndpointSpec('topic_like_state', '查询是否已点赞', 'GET',
                             '/api/haijiao/topic/like/state',
                             summary='查当前账号是否已经给某帖子点过赞（点赞前先查，避免重复提交）。',
                             params=[
                                 ParamSpec('topic_id', '帖子 ID', kind='number', required=True,
                                           placeholder='2274377',
                                           desc='必填：帖子 ID。'),
                             ] + _CRED_PARAMS,
                             notes=[
                                 '必须带登录态：用 account_id（库内账号），或直传 user_id + user_token。',
                                 '返回 data：topic_id / liked（是否已点赞）。',
                                 '「点赞 / 取消点赞」是**按目标状态**提交的，重复点赞不会重复计数，'
                                 '但先查一次可以少发一次无效请求。',
                                 'topic_id 缺失返回 PARAM_MISSING、非数字返回 PARAM_FORMAT_ERROR；'
                                 '凭据缺失返回 PARAM_MISSING。',
                             ]),
                EndpointSpec('topic_like', '点赞 / 取消点赞', 'POST',
                             '/api/haijiao/topic/like',
                             summary='给帖子点赞，或取消点赞（源站按「点赞后的目标状态」提交）。',
                             params=[
                                 ParamSpec('topic_id', '帖子 ID', kind='number', required=True,
                                           placeholder='2274377',
                                           desc='必填：帖子 ID。'),
                                 ParamSpec('action', '动作', kind='select', default='like',
                                           options=[{'value': 'like', 'label': 'like（点赞，默认）'},
                                                    {'value': 'unlike', 'label': 'unlike（取消点赞）'}],
                                           desc='选填：明确的动作，不是「切换」。'),
                             ] + _CRED_PARAMS,
                             notes=[
                                 '必须带登录态：用 account_id（库内账号），或直传 user_id + user_token。',
                                 '源站提交的是「点赞后的目标状态」（status=true/false），所以 action 传的是**明确动作**：'
                                 '传 like 就是确保点赞，传 unlike 就是确保取消，不存在「反着来」的情况。',
                                 '返回 data：topic_id / action / liked（操作后的状态）。',
                                 '点赞数变化可在「帖子详情」的 like_count 看到；点赞过的帖子用「我点赞过的帖子」查。',
                                 'topic_id 缺失返回 PARAM_MISSING、非数字返回 PARAM_FORMAT_ERROR；'
                                 'action 非两种取值返回 PARAM_VALUE_INVALID；帖子不存在返回 EXTERNAL_API_FAILED。',
                             ]),
                EndpointSpec('topic_like_batch', '批量点赞 / 取消点赞', 'POST',
                             '/api/haijiao/topic/like/batch',
                             summary='让账号库里全部账号，都给同一篇帖子点赞（或取消点赞）。',
                             params=[
                                 ParamSpec('topic_id', '帖子 ID', kind='number', required=True,
                                           placeholder='2274377',
                                           desc='必填：帖子 ID。'),
                                 ParamSpec('action', '动作', kind='select', default='like',
                                           options=[{'value': 'like', 'label': 'like（批量点赞，默认）'},
                                                    {'value': 'unlike', 'label': 'unlike（批量取消点赞）'}],
                                           desc='选填：对全部账号执行的动作。'),
                             ],
                             notes=[
                                 '不用传凭据：直接用账号库里每个账号自己的登录态执行，遍历范围是**全部库内账号**。',
                                 '没有 token 的账号（无法登录）计入 skipped 并注明原因，不发起请求。',
                                 '逐个**串行**执行、不并发；单个账号失败不影响其它账号。整批比较慢，'
                                 '请把客户端超时留够（单次点赞请求实测 1.7~2.1 秒）。',
                                 '已经是目标状态的账号（已点过赞 / 本来就没点赞）计入 already，不记为失败，'
                                 '所以重复调用是安全的。',
                                 '返回 data：topic_id / action / total / success_count / already_count / '
                                 'skipped_count / failed_count / items（逐账号的 account_id、user_id、username、'
                                 'state（done / already / skipped / failed）、message）。',
                                 '**风控提醒**：一次让大量账号给同一篇帖子点赞属于明显的刷赞行为，'
                                 '源站可能限制甚至封号，请自行控制频率；需要更保守就用「点赞 / 取消点赞」逐个执行。',
                                 'topic_id 缺失返回 PARAM_MISSING、非数字返回 PARAM_FORMAT_ERROR；'
                                 'action 非两种取值返回 PARAM_VALUE_INVALID。',
                             ]),
                EndpointSpec('topic_liked', '我点赞过的帖子', 'GET',
                             '/api/haijiao/topic/liked',
                             summary='分页列出当前账号点过赞的帖子。',
                             params=[
                                 ParamSpec('page', '页码', kind='number', default='1',
                                           desc='选填：从 1 开始，默认 1（源站每页 20 条）。'),
                             ] + _CRED_PARAMS,
                             notes=[
                                 '必须带登录态：用 account_id（库内账号），或直传 user_id + user_token。',
                                 '返回 data：pagination / results（帖子数组，字段与「内容列表」一致）。',
                                 'page 非数字 / 小于 1 返回 PARAM_FORMAT_ERROR / PARAM_VALUE_INVALID；'
                                 '凭据缺失返回 PARAM_MISSING。',
                                 '配图解密（重要）：',
                             ] + _IMAGE_NOTES),
                EndpointSpec('image', '图片解码', 'GET',
                             '/api/haijiao/image',
                             summary='传入加密图片地址，服务端解码后返回真实图片，可直接用于 <img src>。',
                             params=[
                                 ParamSpec('url', '加密图片地址', required=True,
                                           placeholder='https://pic.xxx.top/hjstore/images/…/xxxx_mini.jpg.txt',
                                           desc='必填：帖内图片的加密地址（取自内容列表 / 详情接口的 images 字段，'
                                                '形如 …/<hash>_mini.jpg.txt）。'),
                             ],
                             notes=[
                                 '响应不是 JSON，而是真实图片二进制（Content-Type 为 image/jpeg 等），'
                                 '可直接用于 <img src>，也可下载保存。',
                                 '该端点已默认设为「开放」（随迁移 0032 落库）：<img> 无法为请求附带签名参数，'
                                 '故不参与签名校验；如需收紧，可在超管控制台「服务策略」里改回「需要签名」。',
                                 '安全约束：只接受 http/https 公网地址（拒绝内网 / 回环 / 保留地址）、不跟随重定向、'
                                 '单张体积上限 5MB，且校验解码结果必须是图片（data:image/*），'
                                 '否则返回 EXTERNAL_API_FAILED——不能被当作通用网页代理使用。',
                                 'url 缺失返回 PARAM_MISSING；地址非法返回 PARAM_VALUE_INVALID。',
                                 '不清楚加密地址怎么解？点上方「解密说明」，里面有完整的原理、步骤与 Python / JS 参考代码。',
                             ],
                             image_help=_IMAGE_DECRYPT_HELP),
                EndpointSpec('video_m3u8', '视频播放列表', 'GET',
                             '/api/haijiao/video/m3u8',
                             summary='获取可直接播放的 m3u8（已在服务端还原源站真密钥），供 HLS 播放器直接加载。',
                             params=[
                                 ParamSpec('topic_id', '帖子 ID', kind='number', required=True,
                                           placeholder='2271635',
                                           desc='必填：帖子 ID（取自内容列表 results[].topic_id）。'),
                                 ParamSpec('attachment_id', '视频附件 ID', kind='number', required=True,
                                           placeholder='14141834',
                                           desc='必填：视频附件 ID（取自详情接口 videos[].id）。'),
                             ],
                             notes=[
                                 '响应不是 JSON，而是 m3u8 播放列表文本'
                                 '（Content-Type: application/vnd.apple.mpegurl），可直接交给 hls.js / DPlayer 播放；'
                                 '视频分片仍来自源站 CDN，本服务不代理分片。',
                                 '源站对视频做了自定义保护：清单里的密钥是假的，真 AES-128 密钥需源站 WASM 还原。'
                                 '本接口已在服务端完成还原并把真密钥内嵌进清单，播放器无需再取密钥、也无需特殊处理。',
                                 '需要服务端配置可用的海角登录凭据（.env 的 HAIJIAO_USER_ID / HAIJIAO_USER_TOKEN），'
                                 '否则取不到视频地址，返回 EXTERNAL_API_FAILED。',
                                 '该端点已默认设为「开放」（随迁移 0031 落库）：它返回播放列表文本，'
                                 '播放器无法为请求附带签名参数，故不参与签名校验；'
                                 '如需收紧，可在超管控制台「服务策略」里改回「需要签名」。',
                                 'topic_id / attachment_id 缺失返回 PARAM_MISSING，非整数返回 PARAM_FORMAT_ERROR。',
                             ]),
                EndpointSpec('register_captcha', '取注册验证码', 'POST',
                             '/api/haijiao/register/captcha',
                             summary='两步式注册的第一步：取注册验证码图片（供人工识别），可选经巨量代理请求。',
                             params=[
                                 ParamSpec('use_proxy', '是否使用代理', kind='select', default='false',
                                           options=[
                                               {'value': 'false', 'label': '直连（默认）'},
                                               {'value': 'true', 'label': '经巨量代理'},
                                           ],
                                           desc='可选：源站对注册有 IP 限制。选 true 时经巨量代理请求，'
                                                '提交注册会自动复用同一次出口 IP。'),
                             ],
                             notes=[
                                 '返回 data.captcha_token（提交注册时回传）、data.captcha_image（验证码图片，'
                                 'data URI，可直接 <img> 展示给人工识别）、data.expires_in（有效期秒）、'
                                 'data.use_proxy 与 data.proxy（走代理时的出口 IP:端口）。',
                                 '为什么分两步：源站注册必须填图形验证码，当前先人工识别；'
                                 '后续接入验证码识别即可自动化（本服务已有 ddddocr 线路，但该站点验证码'
                                 '目前识别率不足，先用人工）。',
                                 '验证码会话有效期 600 秒：期间需完成「提交注册」，超时请重新获取。',
                                 'use_proxy 仅支持 true / false，非法值返回 PARAM_VALUE_INVALID。',
                                 '本页下方提供「批量注册」面板：填数量 → 取多张验证码 → 每张图旁输入框逐个填码 →'
                                 '「一键注册」，用户名 / 密码 / 邮箱由服务端自动生成（用户名统一 xy_ 前缀）。',
                             ],
                             batch_register_path='/api/haijiao/register/batch'),
                EndpointSpec('register', '提交注册', 'POST',
                             '/api/haijiao/register',
                             summary='两步式注册的第二步：用识别出的验证码提交注册（走代理时自动复用同一出口 IP）。',
                             params=[
                                 ParamSpec('captcha_token', '验证码会话 Token', required=True,
                                           desc='必填：上一步「取注册验证码」返回的 captcha_token。'),
                                 ParamSpec('captcha_code', '验证码', required=True,
                                           placeholder='4-6 位',
                                           desc='必填：人工识别的验证码（源站要求 4-6 位）。'),
                                 ParamSpec('username', '用户名', required=True,
                                           desc='必填：用户名（源站上限 12 个字符）。'),
                                 ParamSpec('password', '密码', required=True,
                                           desc='必填：密码，源站要求 ≥ 6 位。'),
                                 ParamSpec('email', '邮箱', required=True,
                                           desc='必填：邮箱，需符合邮箱格式。'),
                             ],
                             notes=[
                                 '本表单上方提供「一键填写」按钮：调用「生成注册账号凭据」接口，'
                                 '自动生成并填入用户名 / 邮箱 / 密码（用户名统一 xy_ 前缀、合计 12 位）。',
                                 '成功返回 data.user_id / username / nickname / email / token'
                                 '（token 为该账号的登录凭证）。',
                                 '参数缺失返回 PARAM_MISSING；密码不足 6 位返回 PARAM_VALUE_INVALID；'
                                 '验证码会话不存在或已过期返回 PARAM_VALUE_INVALID（需重新取验证码）。',
                                 '源站拒绝时 msg 为源站原因：「验证码错误」等业务校验不通过返回 PARAM_VALUE_INVALID，'
                                 '「用户名已存在 / 邮箱已被注册」等返回 RESOURCE_ALREADY_EXISTS（20031）。',
                                 '验证码一次性：无论成功与否，该 captcha_token 都会立即作废。',
                                 '本接口会在对方站点真实创建账号，请合规使用；'
                                 '如需限制调用方，可在超管控制台「服务策略」把本服务设为「仅白名单项目」可调用。',
                             ],
                             auto_fill_path='/api/haijiao/register/credentials'),
                EndpointSpec('register_credentials', '生成注册账号凭据', 'POST',
                             '/api/haijiao/register/credentials',
                             summary='生成一组注册用的用户名 / 密码 / 邮箱（不注册、不入库），'
                                     '供「一键填写」或自行批量注册使用。',
                             notes=[
                                 '返回 data.username / data.password / data.email。',
                                 '生成规则：用户名 = xy_ + 9 位随机（小写字母/数字，合计 12 位，'
                                 '符合源站用户名长度上限）；密码 10 位（必含大写/小写/数字）；'
                                 '邮箱 = <用户名>@<6 位随机小写字母>.com。',
                                 '本接口只生成不注册：需要创建账号请用「提交注册」或「批量注册」。',
                             ]),
                EndpointSpec('register_batch', '批量注册', 'POST',
                             '/api/haijiao/register/batch',
                             summary='批量注册：按验证码逐条注册，用户名 / 密码 / 邮箱由服务端自动生成，'
                                     '用户名统一 xy_ 前缀。',
                             params=[
                                 ParamSpec('items', '注册项列表', kind='textarea', required=True,
                                           placeholder='[{"captcha_token":"xxx","captcha_code":"1234"}]',
                                           desc='必填：JSON 数组字符串，每项含 captcha_token 与 captcha_code；'
                                                '可另带 username / password / email 覆盖自动生成值。单次上限 20 项。'),
                             ],
                             notes=[
                                 '返回 data.total / success_count / failed_count 与 data.items（逐项结果）：'
                                 '成功项含 username / password / email / user_id / token，失败项含 msg（源站原因）。',
                                 '每项的 captcha_token 都来自「取注册验证码」的一次调用，需与该次识别的验证码成对使用；'
                                 '提交时会自动复用取码时的出口 IP（走代理时）。',
                                 '成功注册的账号会自动写入本服务的账号库（见「账号列表」）。',
                                 'items 缺失返回 PARAM_MISSING；不是合法 JSON 数组返回 PARAM_FORMAT_ERROR；'
                                 '超过 20 项返回 PARAM_VALUE_INVALID。',
                             ]),
                EndpointSpec('login', '账号登录', 'POST',
                             '/api/haijiao/login',
                             summary='登录海角社区账号，返回可用 token；支持直传账号或按库内账号 ID 登录。',
                             params=[
                                 ParamSpec('username', '用户名',
                                           desc='选填：与 password 成对使用；与 account_id 二选一。'),
                                 ParamSpec('password', '密码',
                                           desc='选填：与 username 成对使用。'),
                                 ParamSpec('account_id', '库内账号 ID',
                                           desc='选填：传「账号列表」返回的 account_id，'
                                                '服务端从账号表取用户名/密码登录，成功后回写最新 token。'),
                             ],
                             notes=[
                                 '两种用法二选一：username + password 直传，或 account_id（库内账号）。',
                                 '返回 data.token（登录凭证）与 user_id / username / nickname / email。',
                                 '登录成功后会按源站 user_id 同步库内账号（**命中才同步、不新增**）：刷新 token，'
                                 '并用源站返回的用户名 / 邮箱 / 昵称覆盖本地资料；库里没有该账号则只返回登录结果。',
                                 '源站登录签名为 md5(Username + Password + User-Agent)，由服务端自动计算；'
                                 '正常风控下无需图形验证码。',
                                 '参数缺失返回 PARAM_MISSING；账号不存在返回 NOT_FOUND（20030）；'
                                 '密码错误等校验不通过返回 PARAM_VALUE_INVALID（msg 为源站原因）。',
                             ]),
                EndpointSpec('sign_in', '金币签到', 'POST',
                             '/api/haijiao/sign-in',
                             summary='每日金币签到（20 金币/天）；支持按库内账号或直传登录凭据。',
                             params=[
                                 ParamSpec('account_id', '库内账号 ID',
                                           desc='选填：传「账号列表」返回的 account_id，'
                                                '服务端用该账号的 user_id + token 签到；与直传凭据二选一。'),
                                 ParamSpec('user_id', '源站用户ID',
                                           desc='选填：与 user_token 成对使用，直接签到指定账号（不入库）。'),
                                 ParamSpec('user_token', '登录Token',
                                           desc='选填：与 user_id 成对使用。'),
                             ],
                             notes=[
                                 '原理：源站 POST /api/user/user_sign_in（无请求体），靠登录态请求头鉴权，'
                                 '故本服务用账号表里存的 user_id + token 直接签到。',
                                 '双重保险 + 每日本地记录：① 先查库内该账号的「最近签到日期」，'
                                 '等于今天即视为今日已签到，**直接返回、不发任何源站请求**；'
                                 '② 未命中才查源站任务状态，确认可签到后才真正提交；'
                                 '签到成功后把日期记为今天，当天后续调用都走 ①。日期按自然日比较，'
                                 '**跨天自动失效**，无需定时任务重置。',
                                 '返回 data.state：signed=本次签到成功（amount 为到账金币）/ already=今天已签到 '
                                 '（含「本地记录」/「源站确认」两种来源，见 message）/ closed=签到任务未开放。',
                                 '参数缺失返回 PARAM_MISSING；库内账号不存在返回 NOT_FOUND（20030）；'
                                 '账号未存 token 时按参数缺失处理。',
                             ]),
                EndpointSpec('sign_in_batch', '一键签到全部账号', 'POST',
                             '/api/haijiao/sign-in/batch',
                             summary='对账号表里所有已存 token 的账号逐个执行金币签到（一键全签）。',
                             params=[],
                             notes=[
                                 '无参数：一键签到「账号列表」里的全部账号。',
                                 '逐条走与「金币签到」相同的双重保险：今天已签到的账号命中库内记录的'
                                 '「最近签到日期」后**不发任何源站请求**，因此重复调用很快；'
                                 '只有未签到的账号才会查询源站并提交签到（逐个串行，避免触发源站风控）。',
                                 '已签到的账号计入 already_count，不算失败。',
                                 '返回 data.total / success_count（本次新签成功）/ already_count（今天已签）/ '
                                 'failed_count 与 data.items（逐账号结果：account_id / user_id / username / '
                                 'state / amount / msg）。',
                                 '本接口不修改密码 / token 等账号资料，仅回写各账号的「最近签到日期」，'
                                 '可安全重复调用。',
                             ]),
                EndpointSpec('accounts_list', '账号列表', 'GET',
                             '/api/haijiao/accounts',
                             summary='分页查询已入库的海角社区账号（注册成功会自动入库）。',
                             params=[
                                 ParamSpec('keyword', '关键词', placeholder='用户名 / 邮箱 / 昵称 / 用户ID',
                                           desc='选填：模糊匹配 用户名 / 邮箱 / 昵称 / 源站用户ID。'),
                                 ParamSpec('page', '页码', kind='number', default='1', desc='选填：默认 1。'),
                                 ParamSpec('page_size', '每页条数', kind='number', default='10',
                                           desc='选填：1-100，默认 10。'),
                                 ParamSpec('with_password', '返回密码', kind='select',
                                           options=[{'value': 'false', 'label': 'false（默认，不返回密码）'},
                                                    {'value': 'true', 'label': 'true（返回密码明文）'}],
                                           default='false',
                                           desc='选填：是否在列表项中携带密码明文，默认 false。'),
                             ],
                             notes=[
                                 '返回 data.total 与 data.items；列表项包含 account_id（UUID）、user_id、username、'
                                 'email、nickname、remark 与 has_password / has_token 标记。',
                                 '出于安全，列表**不回传**密码与 token 明文；需要密码请传 with_password=true，'
                                 '需要 token 请查「账号详情」，或直接调「账号登录」（会回写最新 token）。',
                             ]),
                EndpointSpec('accounts_create', '新增账号', 'POST',
                             '/api/haijiao/accounts',
                             summary='手动新增一条账号记录（注册成功也会自动入库，此接口用于补录/导入）。',
                             params=[
                                 ParamSpec('user_id', '源站用户ID', required=True,
                                           desc='必填：海角社区用户 ID（全局唯一，重复返回 20031）。'),
                                 ParamSpec('username', '用户名', required=True, desc='必填：用户名。'),
                                 ParamSpec('password', '密码', required=True,
                                           desc='必填：密码（落库 AES 加密）。'),
                                 ParamSpec('email', '邮箱', desc='选填：邮箱。'),
                                 ParamSpec('nickname', '昵称', desc='选填：昵称。'),
                                 ParamSpec('token', '登录Token', desc='选填：登录凭证（落库 AES 加密）。'),
                                 ParamSpec('remark', '备注', desc='选填：备注。'),
                             ],
                             notes=['必填项缺失返回 PARAM_MISSING；源站用户 ID 已存在返回 RESOURCE_ALREADY_EXISTS（20031）。']),
                EndpointSpec('accounts_detail', '账号详情', 'GET',
                             '/api/haijiao/accounts/<uuid>',
                             summary='按账号 ID 查询单条账号（含 token 明文）。',
                             params=[ParamSpec('account_id', '账号 ID', required=True,
                                               placeholder='账号列表返回的 account_id',
                                               desc='路径参数：账号 UUID（文档页代调时填入 account_id 即可）'),
                                     ParamSpec('with_password', '返回密码', kind='select',
                                               options=[{'value': 'false', 'label': 'false（默认，不返回密码）'},
                                                        {'value': 'true', 'label': 'true（返回密码明文）'}],
                                               default='false',
                                               desc='选填：是否在返回中携带密码明文，默认 false。')],
                             notes=['账号不存在返回 NOT_FOUND（20030）。'],
                             path_params={'uuid': 'account_id'}),
                EndpointSpec('accounts_update', '更新账号', 'PATCH',
                             '/api/haijiao/accounts/<uuid>',
                             summary='部分字段更新账号（username / password / email / nickname / token / remark）。',
                             params=[
                                 ParamSpec('account_id', '账号 ID', required=True,
                                           desc='路径参数：账号 UUID（文档页代调时填入 account_id 即可）'),
                                 ParamSpec('username', '用户名', desc='选填：置空会被拒绝。'),
                                 ParamSpec('password', '密码', desc='选填：置空会被拒绝。'),
                                 ParamSpec('email', '邮箱', desc='选填。'),
                                 ParamSpec('nickname', '昵称', desc='选填。'),
                                 ParamSpec('token', '登录Token', desc='选填。'),
                                 ParamSpec('remark', '备注', desc='选填。'),
                             ],
                             notes=['user_id 是源站身份标识，**不可修改**；账号不存在返回 NOT_FOUND（20030）。'],
                             path_params={'uuid': 'account_id'}),
                EndpointSpec('accounts_delete', '删除账号', 'DELETE',
                             '/api/haijiao/accounts/<uuid>',
                             summary='删除账号记录。',
                             params=[ParamSpec('account_id', '账号 ID', required=True,
                                               desc='路径参数：账号 UUID（文档页代调时填入 account_id 即可）')],
                             notes=['仅删除本服务的记录，不会影响源站账号；账号不存在返回 NOT_FOUND（20030）。'],
                             path_params={'uuid': 'account_id'}),
            ],
        ),
    ],
)
