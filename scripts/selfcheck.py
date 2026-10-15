"""上线前 / 提交前的一键自检：把散落的自检命令收成一条

背景：项目原先的自检项（Django 系统检查、迁移一致性、单元测试、i18n 体检、语法检查）
散落在文档与个人习惯里，上不上线全靠「记得跑」。本脚本把它们收敛为一个入口，
退出码可直接作为部署脚本的前置门禁。

用法（在项目根目录执行）：
    .venv\\Scripts\\python.exe scripts\\selfcheck.py           # 全量（含单元测试）
    .venv\\Scripts\\python.exe scripts\\selfcheck.py --quick   # 跳过单元测试，只做静态检查

检查项：
  1. Django 系统检查（manage.py check）
  2. 迁移一致性（makemigrations --check --dry-run）—— 防止「模型改了却没生成迁移」
  3. 单元测试（manage.py test API）
  4. i18n 体检（scripts/check_i18n.py）—— 词条缺失 / 漏包翻译
  5. 全项目语法检查（py_compile）—— 可负担的静态底线
"""
import py_compile
import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
PY = sys.executable
SKIP_DIRS = {'.venv', 'venv', '__pycache__', '.git'}


def run(title, args):
    """跑一条子命令，打印结果并返回是否成功"""
    print(f'\n=== {title} ===', flush=True)
    ok = subprocess.run([PY, *args], cwd=BASE_DIR).returncode == 0
    print(f'--- {title}: {"通过" if ok else "失败"} ---', flush=True)
    return ok


def compile_all():
    """全项目语法检查（跳过虚拟环境与缓存目录）"""
    print('\n=== 语法检查（py_compile）===', flush=True)
    bad = []
    for path in sorted(BASE_DIR.glob('**/*.py')):
        if SKIP_DIRS & set(path.parts):
            continue
        try:
            py_compile.compile(str(path), doraise=True)
        except py_compile.PyCompileError as exc:
            bad.append(str(exc))
    for item in bad:
        print(item)
    print(f'--- 语法检查: {"通过" if not bad else "失败（%d 个文件）" % len(bad)} ---', flush=True)
    return not bad


def main():
    quick = '--quick' in sys.argv[1:]
    results = [
        ('Django 系统检查', run('Django 系统检查', ['manage.py', 'check'])),
        ('迁移一致性', run('迁移一致性', ['manage.py', 'makemigrations', '--check', '--dry-run'])),
    ]
    if not quick:
        results.append(('单元测试', run('单元测试', ['manage.py', 'test', 'API'])))
    results.append(('i18n 体检', run('i18n 体检', ['scripts/check_i18n.py'])))
    results.append(('语法检查', compile_all()))

    print('\n================ 自检汇总 ================')
    for name, ok in results:
        print(f'{"✅ 通过" if ok else "❌ 失败"}  {name}')
    failed = [name for name, ok in results if not ok]
    if failed:
        print(f'\n共 {len(failed)} 项未通过：{"、".join(failed)}')
        return 1
    print('\n全部通过。')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
