"""行为验证样本（影子模式）

    BehaviorSample - 每次表单提交上报的聚合行为特征与风险分

字段说明:
    scene - 场景（login / register / send_code / reset / feedback / other）
    score - 风险分 0-100（规则见 API/apis/captcha_self/behavior.py）
    band  - 档位（low < 30 / mid 30-69 / high >= 70）
    hits  - 命中的规则键列表（如 ["too_fast", "webdriver"]）

**不存原始轨迹、不存输入内容**：前端只上报聚合特征，落库后也只保留分数与命中项。
样本保留 30 天，由写入路径顺带限批清理。
"""
from django.db import models

from API.common.base import BaseModel


class BehaviorSample(BaseModel):
    """一次表单提交的行为风险样本"""

    SCENE_LOGIN = 'login'
    SCENE_REGISTER = 'register'
    SCENE_SEND_CODE = 'send_code'
    SCENE_RESET = 'reset'
    SCENE_FEEDBACK = 'feedback'
    SCENE_OTHER = 'other'
    SCENE_CHOICES = [
        (SCENE_LOGIN, '登录'),
        (SCENE_REGISTER, '注册'),
        (SCENE_SEND_CODE, '发送验证码'),
        (SCENE_RESET, '重置密码'),
        (SCENE_FEEDBACK, '问题反馈'),
        (SCENE_OTHER, '其他'),
    ]

    BAND_LOW = 'low'
    BAND_MID = 'mid'
    BAND_HIGH = 'high'
    BAND_CHOICES = [
        (BAND_LOW, '低风险'),
        (BAND_MID, '中风险'),
        (BAND_HIGH, '高风险'),
    ]

    scene = models.CharField('场景', max_length=16, choices=SCENE_CHOICES,
                             default=SCENE_OTHER, help_text='表单来源')
    score = models.PositiveSmallIntegerField('风险分', default=0, help_text='0-100，越大越可疑')
    band = models.CharField('风险档', max_length=8, choices=BAND_CHOICES,
                            default=BAND_LOW, help_text='low / mid / high')
    hits = models.JSONField('命中规则', default=list,
                            help_text='命中的规则键，如 ["too_fast", "webdriver"]')

    class Meta:
        db_table = 'captcha_behavior_sample'
        verbose_name = '行为验证样本'
        verbose_name_plural = '行为验证样本'
        ordering = ['-create_time']
        # 追加型大表：只按 -create_time 分页 / 聚合，单独建索引（BaseModel 的 create_time 无索引）
        indexes = [
            models.Index(fields=['-create_time'], name='captcha_behavior_time_idx'),
        ]

    def __str__(self):
        return f'{self.get_scene_display()} {self.score}（{self.get_band_display()}）'
