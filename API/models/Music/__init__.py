"""音乐业务域：Music（元数据）+ MusicSource（播放源，外键强关联）"""
from API.models.Music.music import Music, MusicSource

__all__ = ['Music', 'MusicSource']
