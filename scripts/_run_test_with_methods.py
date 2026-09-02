"""临时启用邮箱/手机号验证方式后运行指定测试脚本，结束后恢复 AuthMethod 原状态

用途：邮箱/手机号相关测试需在「验证方式已启用」前提下运行（round 内部会自行切换开关并恢复），
本脚本负责在进入测试前临时启用、退出后恢复后台原配置，避免污染生产配置。

用法：
    .venv\\Scripts\\python.exe scripts\\_run_test_with_methods.py [模块名]
    默认模块名为 test_auth_methods；也可传入 test_email_register 等依赖验证方式的测试模块
"""
import importlib
import os
import sys

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'XiaoYingAPI.settings')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import django

django.setup()

from API.models import AuthMethod


def main():
    module_name = sys.argv[1] if len(sys.argv) > 1 else 'test_auth_methods'
    orig = {m.type: m.enabled for m in AuthMethod.objects.all()}
    print(f'AuthMethod 原状态: {orig}')
    AuthMethod.objects.all().update(enabled=True)
    print(f'已临时启用全部验证方式，开始运行 {module_name}.py')
    try:
        test_mod = importlib.import_module(module_name)
        test_mod.main()
    finally:
        for mtype, enabled in orig.items():
            AuthMethod.objects.filter(type=mtype).update(enabled=enabled)
        print(f'已恢复 AuthMethod 原状态: {orig}')


if __name__ == '__main__':
    main()
