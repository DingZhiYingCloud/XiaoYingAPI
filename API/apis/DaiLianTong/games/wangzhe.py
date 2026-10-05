"""王者荣耀（game_id=107）发单表单声明

逆向来源：手机端发单页 pages/index/orderPublish/orderPublish 的静态 JS。
已实测：代练类型「自定义发布」可成功下单（LevelType2=14）。

新增/修改玩法时，请同时在真机发单页核对一次，避免上游改动后我们落后。
"""
from .spec import FieldSpec, GameProfile, PlaySpec

PROFILE = GameProfile(
    game_id='107',
    name='王者荣耀',
    default_zone_server_id='107103017095500',   # 安卓QQ·默认服
    plays=[
        PlaySpec('自定义发布', '14', ['game_extra'],
                 '自由填写代练任务；Actors 第 4 段放「铭文等级」等角色信息'),
        PlaySpec('5V5排位赛', '10', ['game_extra'], '段位代练（当前未接入表单字段）'),
        PlaySpec('巅峰赛', '13', ['game_extra'], '巅峰赛代练（当前未接入表单字段）'),
        PlaySpec('荣耀战力', '15', ['game_extra'], '荣耀战力单（当前未接入表单字段）'),
    ],
    fields=[
        FieldSpec('game_extra', '铭文', kind='text', default='150',
                  actor_index=4,
                  desc='写入 Actors 第 4 段；默认 150（铭文等级）'),
    ],
    note='当前只接入「自定义发布」；其余玩法待逐个补表单字段',
)
