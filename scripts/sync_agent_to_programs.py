"""把 scripts/agent（ai-brain / ai-agent 真实源码）同步到「计算程序」展示副本

前台 `/programs/` 的条目来自 `CalculationProgram/`，其中 `Agent/ai-brain/` 是
**复制**过去的展示 + 下载副本（见 `BugAndRepair/变更记录.md`）。手工复制必然走偏 ——
历史上两份的 VERSION 与多个文件已经不一致，故把同步收敛成这一条命令：改完
`scripts/agent` 后跑一次即可（发布前跑，别把半成品同步出去）。

用法（在项目根目录执行）：
    python scripts/sync_agent_to_programs.py            # 实际同步
    python scripts/sync_agent_to_programs.py --dry-run  # 只列出会变动的文件

规则：
- 只同步源码；`__pycache__`（运行产物）与 `win/win/`（打包脚本在错误目录跑出的嵌套产物）不参与；
- 目标目录里**多出来**的文件会被删除，保证两边文件清单一致；
- 只读写上面这一对目录，不动 `CalculationProgram/` 下的其它内容。
"""
import filecmp
import shutil
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
SOURCE = BASE_DIR / 'scripts' / 'agent'
TARGET = BASE_DIR / 'CalculationProgram' / 'Agent' / 'ai-brain'

# 不同步的目录名（任意层级命中即跳过）：Python 字节码缓存
EXCLUDE_DIRS = {'__pycache__'}
# 不同步的相对路径前缀（打包脚本在错误工作目录下产生的嵌套产物）
EXCLUDE_PREFIXES = (('win', 'win'),)


def _iter_files(root: Path):
    """列出需要同步的相对路径（跳过排除项），按路径排序"""
    result = []
    for path in root.rglob('*'):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        if any(part in EXCLUDE_DIRS for part in rel.parts):
            continue
        if any(rel.parts[:len(prefix)] == prefix for prefix in EXCLUDE_PREFIXES):
            continue
        result.append(rel)
    return sorted(result)


def main() -> int:
    dry_run = '--dry-run' in sys.argv[1:]
    if not SOURCE.is_dir():
        print(f'源目录不存在：{SOURCE}')
        return 1

    src_files = _iter_files(SOURCE)
    tgt_files = _iter_files(TARGET) if TARGET.is_dir() else []

    src_set, tgt_set = set(src_files), set(tgt_files)
    copied, same = [], 0
    for rel in src_files:
        source_file, target_file = SOURCE / rel, TARGET / rel
        if target_file.is_file() and filecmp.cmp(source_file, target_file, shallow=False):
            same += 1
            continue
        copied.append(rel)
        if not dry_run:
            target_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_file, target_file)
    removed = sorted(tgt_set - src_set)
    if not dry_run:
        for rel in removed:
            (TARGET / rel).unlink()

    print(f'源 {len(src_files)} 个文件，其中未变 {same} 个')
    for rel in copied:
        print(f'  {"将同步" if dry_run else "已同步"}: {rel}')
    for rel in removed:
        print(f'  {"将删除（源中已不存在）" if dry_run else "已删除（源中已不存在）"}: {rel}')
    if not copied and not removed:
        print('两边已一致，无需改动。')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
