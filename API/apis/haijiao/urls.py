# 域名前缀: /api/haijiao/
from django.urls import path

from . import request

urlpatterns = [
    path('topics', request.topics_view, name='haijiao_topics'),  # 内容列表（热帖/新闻/大事记/原创/精华/最新）
    path('search', request.search_view, name='haijiao_search'),  # 搜索（帖子）
    path('topic/detail', request.topic_detail_view, name='haijiao_topic_detail'),  # 帖子详情
    path('topic/comments', request.topic_comments_view,
         name='haijiao_topic_comments'),  # 帖子评论列表（分页）
    path('comment/replies', request.comment_replies_view,
         name='haijiao_comment_replies'),  # 二级评论列表（某条主评论下的子评论）
    path('topic/nodes', request.topic_nodes_view, name='haijiao_topic_nodes'),  # 板块列表（发帖用）
    path('topic/tags', request.topic_tags_view, name='haijiao_topic_tags'),  # 标签池（发帖用）
    path('topic/upload', request.topic_media_upload_view,
         name='haijiao_topic_upload'),  # 上传发帖媒体（图片 / 视频）
    path('topic/create', request.topic_create_view, name='haijiao_topic_create'),  # 发帖
    path('topic/mine', request.topic_mine_view, name='haijiao_topic_mine'),  # 我的帖子（按审核状态）
    path('gift/list', request.gift_list_view, name='haijiao_gift_list'),  # 礼物列表（打赏挑礼物）
    path('topic/give', request.topic_give_view, name='haijiao_topic_give'),  # 给帖子送金币（打赏）
    path('user/follow', request.user_follow_view, name='haijiao_user_follow'),  # 关注 / 取消关注用户
    path('user/follow/batch', request.follow_batch_view,
         name='haijiao_user_follow_batch'),  # 批量关注 / 取消关注（全部库内账号）
    path('ranking', request.ranking_view, name='haijiao_ranking'),  # 排行榜（粉丝 / 点赞 / 人气）
    path('user/info', request.user_info_view, name='haijiao_user_info'),  # 用户主页信息
    path('user/wealth', request.user_wealth_view, name='haijiao_user_wealth'),  # 余额
    path('user/wealth/log', request.user_wealth_log_view,
         name='haijiao_user_wealth_log'),  # 金币 / 钻石流水
    path('user/following', request.user_following_view, name='haijiao_user_following'),  # 我关注的人
    path('user/fans', request.user_fans_view, name='haijiao_user_fans'),  # 我的粉丝
    path('topic/like/state', request.topic_like_state_view,
         name='haijiao_topic_like_state'),  # 查询是否已点赞
    path('topic/like', request.topic_like_view, name='haijiao_topic_like'),  # 点赞 / 取消点赞
    path('topic/like/batch', request.like_batch_view,
         name='haijiao_topic_like_batch'),  # 批量点赞 / 取关（全部库内账号）
    path('topic/liked', request.topic_liked_view, name='haijiao_topic_liked'),  # 我点赞过的帖子
    path('image', request.image_view, name='haijiao_image'),  # 图片解码（返回真实图片）
    path('register/captcha', request.register_captcha_view, name='haijiao_register_captcha'),  # 取注册验证码
    path('register/credentials', request.register_credentials_view,
         name='haijiao_register_credentials'),  # 生成注册账号凭据（一键填写）
    path('register/batch', request.register_batch_view, name='haijiao_register_batch'),  # 批量注册
    path('register', request.register_view, name='haijiao_register'),  # 提交注册
    path('login', request.login_view, name='haijiao_login'),  # 账号登录
    path('sign-in', request.sign_in_view, name='haijiao_sign_in'),  # 金币签到（单账号）
    path('sign-in/batch', request.sign_in_all_view,
         name='haijiao_sign_in_batch'),  # 一键签到全部账号
    path('accounts', request.accounts_view, name='haijiao_accounts'),  # 账号列表 / 新增
    path('accounts/<uuid:account_id>', request.account_detail_view,
         name='haijiao_account_detail'),  # 账号详情 / 更新 / 删除
    path('video/m3u8', request.video_m3u8_view, name='haijiao_video_m3u8'),  # 视频播放列表（已还原真密钥）
]
