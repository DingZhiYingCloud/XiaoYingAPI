"""代练通「发布订单」各游戏表单的注册表 —— **新增游戏请从这里开始看**

## 为什么要有这套东西
每个游戏的发单表单**完全不一样**：
- 王者荣耀：铭文等级 + 英雄数量 + 段位（能选「自定义发布」）
- 三角洲行动：训练模式 + 地图 + 任务 + 时长（字段前缀 SJZ_，且代练模式没有「自定义发布」）
它们的「代练类型 → 上游 LevelType2」也不同。所以每个游戏用一份**声明**描述自己的表单，
接口层 / 文档层 / 爬虫层统一从声明取数，避免参数散落硬编码、也让新增游戏有明确落点。

## 新增一个游戏（三步）
1. 复制 `wangzhe.py` → `games/<新游戏>.py`，改 `PROFILE`：
   - 基本：`game_id` / `name` / `default_zone_server_id` / `enabled`
   - `plays`：列出该游戏的每种「代练类型/玩法」，各自声明 `level_type2` 和需要的字段
   - `fields`：字段定义（`key` / `label` / `kind` / `options` / `required` / `default`；
     `actor_index > 0` 表示写进 Actors 第 N 段，`0` 表示是独立请求字段）
2. 在下面 `GAMES` 里注册它。
3. 跑 `python manage.py check` 与 `python manage.py test API.tests`，并在文档页自测；
   真机验证通过后再把 `enabled` 置为 `True`。

逆向入口（怎么拿到这些字段）—— 强烈建议先用方法 1：
1) 【最快·真机运行期直接读】手机端发单页控制台里：
   `const vm = getCurrentPages().pop().$vm`
   - `vm.page1CellName` + `vm.page1Cell`（同长布尔数组）→ **当前游戏/玩法显示哪些字段**
   - `vm.SJZTraningMode / vm.SJZMaps / vm.SJZRWtype / vm.pickerJson.JSONxx` → **各下拉的选项**
   - `vm.form.gameid / levelType2 / type / orderType` → 当前玩法与上游取值
   - 切游戏：`vm.selGame({name:{id:'<gameId>'}}, 2)`（切完等 2~3 秒再读）
   这样做**不用点 UI、不改数据**，比翻 JS 快且准（字段的显示与否由运行期数据决定）。
2) 【静态 JS】`pages/index/orderPublish/orderPublish` 的打包 JS：搜 `gameid` 分支、
   `pickerJson`（选项表）、提交函数里 `x = { ZoneServerID, Actors, ... }` 的组装。
- 无论用哪种方法，**发单前必须真机核对一次**：上游会改，且部分取值（如 LevelType2）上游不校验、写错也能提交。

## 约定
- `enabled=False` 的游戏：不出现在文档下拉；接口传该 `game_id` 会**直接报错**（不会退化成默认游戏的参数）。
- 未在 `GAMES` 中声明的 `game_id`：一律回落到 `DEFAULT_GAME_ID`（王者荣耀）。
"""
from typing import Dict, List

from .spec import FieldSpec, GameProfile, PlaySpec
from . import delta, wangzhe

# 已接入的游戏注册表：新增游戏在这里加一行
GAMES: Dict[str, GameProfile] = {
    wangzhe.PROFILE.game_id: wangzhe.PROFILE,
    delta.PROFILE.game_id: delta.PROFILE,
}

# 未指定 / 未声明游戏时的默认游戏
DEFAULT_GAME_ID: str = wangzhe.PROFILE.game_id

__all__ = ['GAMES', 'DEFAULT_GAME_ID', 'FieldSpec', 'GameProfile', 'PlaySpec',
           'enabled_games', 'get_profile', 'is_supported_game']


def enabled_games() -> List[GameProfile]:
    """可供用户发单的游戏（enabled=True）"""
    return [profile for profile in GAMES.values() if profile.enabled]


def get_profile(game_id) -> GameProfile:
    """取某游戏的表单声明；未声明或未启用则回落默认游戏"""
    profile = GAMES.get(str(game_id or ''))
    if profile is None or not profile.enabled:
        return GAMES[DEFAULT_GAME_ID]
    return profile


def is_supported_game(game_id) -> bool:
    """该 game_id 是否为「已启用」的游戏（用于接口前置校验，避免误用默认游戏参数）"""
    profile = GAMES.get(str(game_id or ''))
    return bool(profile and profile.enabled)
