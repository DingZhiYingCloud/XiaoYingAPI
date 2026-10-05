"""代练通发单表单的「声明式」数据结构

各游戏发单表单完全不同（王者=铭文/英雄数量/段位；三角洲=训练模式/地图/任务/时长），
所以用一份声明描述每个游戏的表单，接口层 / 文档层 / 爬虫层都从声明取数，不再散落硬编码。
新增游戏请看包内 __init__.py 的说明。
"""
from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class FieldSpec:
    """游戏表单里的一个字段

    actor_index > 0 表示该字段写入 Actors 的第 N 段（1 起，用 `|*|` 拼接）；
    actor_index == 0 表示它是独立的请求字段（与上游同名）。
    """
    key: str
    label: str
    kind: str = 'text'                       # text / number / select
    options: List[Dict[str, str]] = field(default_factory=list)   # select 用 [{value,label}]
    required: bool = False
    default: str = ''
    desc: str = ''
    actor_index: int = 0


@dataclass
class PlaySpec:
    """一种「代练类型 / 玩法」（用户要先选玩法，再填该玩法需要的字段）"""
    name: str
    level_type2: str                          # 上游 LevelType2（同一游戏各玩法不同）
    fields: List[str] = field(default_factory=list)   # 该玩法需要的字段 key（见 GameProfile.fields）
    desc: str = ''


@dataclass
class GameProfile:
    """一个游戏的发单表单声明"""
    game_id: str
    name: str
    default_zone_server_id: str               # 默认区服（ZoneServerID）
    plays: List[PlaySpec] = field(default_factory=list)     # 该游戏的玩法列表
    fields: List[FieldSpec] = field(default_factory=list)   # 所有字段定义（含通用字段）
    enabled: bool = True                      # False = 未验证完成，不出现在下拉、接口直接拒绝
    note: str = ''
