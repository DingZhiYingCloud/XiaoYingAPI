"""小影音乐爬虫 CLI 日志系统

设计目标（满足用户要求）:
- 所有错误信息统一堆到一个日志文件（JSON lines 格式，每行一个完整 JSON 对象）
- 日志包含足够的结构化字段（时间/级别/步骤/歌手/歌曲/页数/URL/异常类型/消息/traceback），方便交给 AI 检查
- 日志文件位置可通过 --log 指定
- 全局兜底: 捕获一切未预期异常写入日志，保证程序不崩溃
"""
import json
import os
import sys
import threading
import time
import traceback

from cli.config import DEFAULT_LOG


# ==================== 终端颜色（ANSI 转义，Windows 10+/现代终端均支持） ====================

class Color:
    """ANSI 颜色码常量"""
    RESET = '\033[0m'
    RED = '\033[31m'            # 错误
    GREEN = '\033[32m'          # 歌曲进度
    YELLOW = '\033[33m'         # 去重跳过
    BLUE = '\033[34m'           # 列表页信息
    MAGENTA = '\033[35m'        # 歌手开始
    CYAN = '\033[36m'           # 任务开始
    BRIGHT_GREEN = '\033[92m'   # 完成
    BRIGHT_YELLOW = '\033[93m'  # 重试/警告
    BRIGHT_BLUE = '\033[94m'    # 歌曲页抓取
    BRIGHT_CYAN = '\033[96m'    # 缓存命中


# 状态 -> 颜色（每种状态唯一，互不相同）
STATUS_COLORS = {
    'start': Color.CYAN,           # 任务开始
    'page': Color.BLUE,            # 歌手列表页信息
    'songpage': Color.BRIGHT_BLUE, # 歌曲页抓取进度
    'singer': Color.MAGENTA,       # 歌手开始
    'progress': Color.GREEN,       # 歌曲播放源进度（新抓取）
    'cache': Color.BRIGHT_CYAN,    # 播放源命中缓存（未请求网络）
    'skipped': Color.YELLOW,       # 去重跳过
    'warn': Color.BRIGHT_YELLOW,   # 失败重试/警告
    'done': Color.BRIGHT_GREEN,    # 任务/页完成
    'error': Color.RED,            # 错误
}


def colorize(text, color):
    """给文本加 ANSI 颜色；color 为空时不加色"""
    return f'{color}{text}{Color.RESET}' if color else text


class Logger:
    """日志器: 同时写文件(JSON lines)与控制台(带色文本)

    状态与颜色对应关系见 STATUS_COLORS，每种状态颜色唯一。
    文件日志始终为纯 JSON（不含 ANSI 转义，便于 AI 解析）。
    """

    def __init__(self, log_path=None):
        self.log_path = log_path or DEFAULT_LOG
        self._lock = threading.Lock()  # 多线程并发写日志时保护文件与控制台（输出不交错）
        parent = os.path.dirname(os.path.abspath(self.log_path))
        os.makedirs(parent, exist_ok=True)

    def _write(self, level, message, status=None, **fields):
        """写一条日志记录: 文件(JSON) + 控制台(带色)"""
        record = {
            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
            'level': level,
            'message': message,
            **fields,
        }
        with self._lock:
            # 文件: JSON lines，追加写入，所有错误堆在同一文件
            with open(self.log_path, 'a', encoding='utf-8') as f:
                f.write(json.dumps(record, ensure_ascii=False) + '\n')

            # 控制台简化输出（按状态着色，默认无色）
            parts = [f'[{level}] {message}']
            for key, label in (('singer', '歌手'), ('song', '歌曲'), ('page', '第{0}页')):
                if fields.get(key):
                    parts.append(f'{label}: {fields[key]}' if not key == 'page' else f'第{fields[key]}页')
            if fields.get('url'):
                parts.append(f'URL: {fields["url"]}')
            if fields.get('msg'):
                parts.append(f'原因: {fields["msg"]}')
            print(colorize(' | '.join(parts), STATUS_COLORS.get(status)))
        return record

    def info(self, message, status=None, **fields):
        """记录普通信息；status 用于控制台着色（取值见 STATUS_COLORS）"""
        return self._write('INFO', message, status=status, **fields)

    def error(self, message, exc=None, status='error', **fields):
        """记录错误（控制台红色）；exc 为异常对象时自动提取类型与 traceback"""
        if exc is not None:
            fields.setdefault('error_type', type(exc).__name__)
            fields.setdefault('msg', str(exc))
            fields.setdefault('traceback', ''.join(traceback.format_exception(type(exc), exc, exc.__traceback__)))
        else:
            fields.setdefault('error_type', 'UNKNOWN')
        return self._write('ERROR', message, status=status, **fields)


def read_errors(log_path):
    """从日志文件读取全部错误记录（level == ERROR），供「错误清单重试」使用

    :param log_path: 日志文件路径
    :return: list[dict] 错误记录（按写入顺序）
    """
    if not os.path.exists(log_path):
        return []
    errors = []
    with open(log_path, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except (ValueError, TypeError):
                continue
            if rec.get('level') == 'ERROR':
                errors.append(rec)
    return errors


def tail_log(log_path, count=50):
    """读取日志文件末尾 count 行（供「查看日志」使用）"""
    if not os.path.exists(log_path):
        return []
    with open(log_path, encoding='utf-8') as f:
        lines = f.readlines()
    return [l.rstrip('\n') for l in lines[-count:]]


def install_global_guard(logger):
    """全局兜底: 替换 sys.excepthook，任何未捕获异常写日志而非让程序崩溃

    仅在主线程入口调用一次。普通流程中的异常已被各层 try/except 兜底，
    此处是最后一道防线（如线程/库内部漏网异常）。
    """

    def handler(exc_type, exc, tb):
        logger.error(f'程序未捕获异常: {exc}', exc=exc)

    sys.excepthook = handler
