"""三角洲行动（game_id=394）发单表单声明 —— **已启用（「自定义发布」已真机发单验证通过）**

状态：字段与「代练类型 → 上游 LevelType2」已用两种方式核对（打包 JS + 发单页运行期实例），
      并已用「自定义发布（LevelType2=3）」真机发单 → 在「我的订单」核对 → 撤销成功。
      其余玩法（哈夫币/撞车/烽火战场等）的二级字段尚未真机验证，如需开放请按下面的待办补完。

## 一、代练类型清单（发单页 picker 表 arr48，`id` 即上游 LevelType2）
| 代练类型 | LevelType2 |
|---|---|
| 哈夫币 | 29 |
| 护航(陪) | 30 |
| 赛季3X3 | 26 |
| 撞车 | 32 |
| 烽火/战场 | 31 |
| 道具/称号 | 33 |
| 部门任务 | 34 |
| **自定义发布** | **3** |

> 注意：王者的「自定义发布」是 14，三角洲行动是 **3**，两者不通用。

## 二、二级玩法会改 LevelType2（同一代练类型下再细分）
- 撞车：哈夫币 → 40；道具 → 34
- 烽火/战场：烽火段位 → 35；战场段位 → 36；烽火等级 → 31；其它 → 27
- 任务类型(SJZ_RWType)：活动道具 → 39；其余 → 41

## 三、真机读取到的字段（代练模式，代练类型=哈夫币）
显示的字段 = 代练类型(type) / 区服(zoneserver) / AQTW_BXNum / AQTW_goods_KNCoin / 训练模式(SJZ_traningMode)
→ **没有「订单类别(orderType)」、没有「铭文/角色信息」、没有「代练任务(段位)」**（这些是王者荣耀专属）

相关字段与已读到的选项：
- 训练模式 SJZ_traningMode：跑刀 / 直播猛攻（哈夫币类玩法下）
- 游戏模式 SJZGameMode：绝密 / 机密
- 地图 SJZMaps：不限 / 巴克什 / 航天基地 / 潮汐监狱（「绝密」子项下另有一层）
- 任务类型 SJZ_RWtype：海洋之泪 / 非洲之心 / 天才少年 / 活动道具

## 四、待办
  [x] 自定义发布（LevelType2=3）：真机发单 → 「我的订单」核对 → 撤销，全部通过
  [ ] 其余玩法（哈夫币/护航/赛季3X3/撞车/烽火战场/道具称号/部门任务）：
      逐玩法确认二级字段的必填/默认与选项，再各真机发一笔验证
  [ ] 验证通过后把对应 PlaySpec 的 fields 补全（当前为占位）
"""
from .spec import FieldSpec, GameProfile, PlaySpec

PROFILE = GameProfile(
    game_id='394',
    name='三角洲行动',
    default_zone_server_id='394183617899100',   # 手机QQ
    plays=[
        # 首位 = 默认玩法；必须是已真机验证的那条，避免默认落到未验证玩法
        PlaySpec('自定义发布', '3', [], '自由填写；LevelType2=3（与王者的 14 不同）— 已真机验证'),
        PlaySpec('哈夫币', '29', ['SJZ_traningMode'], '训练模式：跑刀 / 直播猛攻'),
        PlaySpec('护航(陪)', '30', [], '字段待真机确认'),
        PlaySpec('赛季3X3', '26', [], '字段待真机确认'),
        PlaySpec('撞车', '32', ['SJZ_traningMode'], '二级：哈夫币→LevelType2=40、道具→34'),
        PlaySpec('烽火/战场', '31', ['SJZ_traningMode', 'SJZMaps', 'SJZMission'],
                 '二级：烽火段位→35、战场段位→36、烽火等级→31、其它→27'),
        PlaySpec('道具/称号', '33', ['SJZ_RWtype'], '任务类型：活动道具→39、其余→41'),
        PlaySpec('部门任务', '34', [], '字段待真机确认'),
    ],
    fields=[
        FieldSpec('SJZ_traningMode', '训练模式', kind='select',
                  options=[{'value': '跑刀', 'label': '跑刀'},
                           {'value': '直播猛攻', 'label': '直播猛攻'}],
                  desc='哈夫币类玩法下的训练模式；撞车/烽火玩法的选项不同，待补'),
        FieldSpec('AQTW_goods_KNCoin', '哈夫币数量', kind='text',
                  desc='真机字段名（上游沿用 AQTW_ 前缀）；取值范围待确认'),
        FieldSpec('AQTW_BXNum', '保险/箱数', kind='text',
                  desc='真机字段名（上游沿用 AQTW_ 前缀）；含义待确认'),
        FieldSpec('SJZMaps', '地图', kind='select',
                  options=[{'value': '不限', 'label': '不限'},
                           {'value': '巴克什', 'label': '巴克什'},
                           {'value': '航天基地', 'label': '航天基地'},
                           {'value': '潮汐监狱', 'label': '潮汐监狱'}],
                  desc='烽火/战场等玩法使用；「绝密」下还有一层子项'),
        FieldSpec('SJZ_RWtype', '任务类型', kind='select',
                  options=[{'value': '海洋之泪', 'label': '海洋之泪'},
                           {'value': '非洲之心', 'label': '非洲之心'},
                           {'value': '天才少年', 'label': '天才少年'},
                           {'value': '活动道具', 'label': '活动道具'}],
                  desc='道具/称号玩法使用'),
    ],
    enabled=True,
    note='自定义发布（LevelType2=3）已真机验证通过；其余玩法的二级字段待逐个验证后补全',
)
