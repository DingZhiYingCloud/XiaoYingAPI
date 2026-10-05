"""代练丸子「发布订单」游戏预设（声明式）

新增游戏只在这里加一条；发布接口按 game_id 取预设默认值，调用方只需覆盖差异项。

注意：预设里的价格 / 保证金 / 游戏账号等是**测试默认值**（便于只传 game_id 即可发单），
正式对接请按需覆盖。`tasks` 的字段名与含义见「发单选项」接口返回的 `fields[].name`：
- 段位类（type=6）：{'name': '起止段位', 'start': '青铜3段0星', 'end': '王者50星'}
- 下拉类（type=1）：{'name': '保险箱', 'value': '2格'}
- 数字类（type=5）：{'name': '哈夫币(万)', 'value': 100}
"""
from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class GamePreset:
    game_id: str
    name: str                    # 便于阅读的游戏名（发布时以前端实时拉取的上游名为准）
    region_name: str             # 默认大区中文名（对应发单页「游戏区服」）
    leveling_type_name: str      # 默认代练类型中文名（对应发单页「代练类型」）
    tasks: List[dict] = field(default_factory=list)   # 该游戏默认的任务字段取值
    title_suffix: str = '私单勿接，指定单，接了扣除双金'   # 自动生成标题时追加（测试账号防私接）
    price_index: int = 0         # 默认报价档位下标（slicePriceCal 返回的 categoryPriceList）
    amount: float = 2            # 订单价格（元）
    hour: float = 3              # 代练时长（小时）
    security_deposit: float = 2  # 安全保证金（元）
    efficiency_deposit: float = 2  # 效率保证金（元）
    login_method: int = 2        # 1=扫码上号 / 2=账密上号
    game_account: str = ''
    game_password: str = ''
    game_role: str = ''
    player_phone: str = ''       # 号主手机
    contact_phone: str = ''      # 发单方联系方式
    contact_qq: str = ''         # 其它联系方式
    note: str = ''


# 测试用账号默认值（仅在调用方未覆盖时生效）
_TEST_ACCOUNT = {
    'game_account': '13712992620',
    'game_password': 'qwe12345',
    'game_role': '小影',
    'player_phone': '13712992781',
    'contact_phone': '13712992611',
    'contact_qq': '13712991205',
}

GAMES: Dict[str, GamePreset] = {
    '1': GamePreset(
        game_id='1', name='王者荣耀', region_name='安卓QQ', leveling_type_name='排位',
        tasks=[
            {'name': '起止段位', 'start': '青铜3段0星', 'end': '王者50星'},
            {'name': '铭文等级', 'value': 150},
            {'name': '英雄数量', 'value': 170},
        ],
        price_index=1,
        note='王者荣耀（gameId=1）：默认排位 / 安卓QQ / 青铜3段0星 → 王者50星 / 铭文150 / 英雄170',
        **_TEST_ACCOUNT,
    ),
    '134': GamePreset(
        game_id='134', name='三角洲行动', region_name='手机QQ', leveling_type_name='哈夫币代刷',
        tasks=[
            {'name': '哈夫币(万)', 'value': 100},
            {'name': '哈夫币获取方式', 'value': '代肝'},
            {'name': '保险箱', 'value': '2格'},
        ],
        price_index=2,
        note='三角洲行动（gameId=134）：默认哈夫币代刷 / 手机QQ / 哈夫币100万 / 代肝 / 保险箱2格',
        **_TEST_ACCOUNT,
    ),
}

# 未指定 / 未声明游戏时的默认游戏
DEFAULT_GAME_ID = '1'


def get_preset(game_id=None) -> GamePreset:
    """取某游戏的发单预设；未声明则回落默认游戏"""
    return GAMES.get(str(game_id or ''), GAMES[DEFAULT_GAME_ID])


def supported_game_options() -> List[dict]:
    """已接入发单的游戏下拉：[{value: game_id, label: 游戏名}]（供文档渲染）"""
    return [{'value': preset.game_id, 'label': preset.name} for preset in GAMES.values()]
