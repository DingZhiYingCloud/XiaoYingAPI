"""用户中心 - 接入项目业务逻辑

功能：
    get_project_info - 查询项目自身信息（供项目方核对配置）
"""
from API.models import UserApp


def get_project_info(app):
    """查询项目自身信息

    :return: (True, {project_id, name, app_id, token_expire_days, status})
    """
    return True, {
        'project_id': str(app.id),
        'name': app.name,
        'app_id': app.app_id,
        'token_expire_days': app.token_expire_days,
        'status': app.status,
    }
