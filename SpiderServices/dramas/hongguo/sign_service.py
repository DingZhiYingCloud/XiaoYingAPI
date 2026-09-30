"""
红果离线签名服务（unidbg）的进程托管

签名由本项目自带的 unidbg 签名器生成（scripts/hongguo_sign/：JVM 里模拟
libmetasec_ml.so，产出 fqnovel 要求的 metasec 安全头）。它是独立的 Java 进程，
无法在 Django 进程内运行，因此这里负责「按需拉起 + 复用」：

  - 需要签名时先探测端口：已在监听则直接复用（多 worker、开发期热重载都安全）
  - 未监听则拉起该进程，并等待其就绪；日志写入 logs/hongguo_sign.log
  - 只在配置的签名地址是本机（127.0.0.1/localhost）时才自动拉起：指向远端签名服务
    时保持纯客户端行为
  - 仅「第 4 集及以后」走 App 内部接口时才会用到签名，前 3 集不会拉起该进程

运行 Java 的优先级：项目内置的裁剪版 JRE（scripts/hongguo_sign/jre/，无需本机装 Java）
> 配置项 HONGGUO_JAVA_BIN 指定的解释器 > PATH 上的 java。

前置条件：scripts/hongguo_sign/ 下的 unidbg-sign.jar、capture/fq_oversea/、jre/ 均已放好
（见 start_sign_service.bat 顶部说明）。
"""
import os
import shutil
import socket
import subprocess
import threading
import time
from pathlib import Path
from urllib.parse import urlparse

from django.conf import settings

# 本机签名地址的判定范围（非本机则不自动拉起）
_LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}

# 拉起互斥：避免并发请求同时拉起多个进程
_spawn_lock = threading.Lock()
# 已拉起的子进程句柄与日志句柄（持有引用，避免被 GC 回收）
_process = None
_log_handle = None


def _sign_url():
    return str(getattr(settings, "HONGGUO_SIGN_URL", "http://127.0.0.1:9099"))


def _is_local():
    return (urlparse(_sign_url()).hostname or "") in _LOCAL_HOSTS


def _host_port():
    parsed = urlparse(_sign_url())
    return parsed.hostname or "127.0.0.1", parsed.port or 80


def is_running(timeout=0.5):
    """签名服务端口是否已在监听"""
    host, port = _host_port()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _check_artifacts(sign_root):
    """签名服务运行物是否齐全，缺失时给出可操作的报错"""
    jar = sign_root / "sign" / "unidbg-sign.jar"
    libs = sign_root / "capture" / "fq_oversea"
    missing = []
    if not jar.exists():
        missing.append(str(jar))
    for name in ("libmetasec_ml.so", "libc++_shared.so", "ms_16777218.bin"):
        if not (libs / name).exists():
            missing.append(str(libs / name))
    if missing:
        raise RuntimeError(
            "红果离线签名服务的运行物缺失，请按 scripts/hongguo_sign/start_sign_service.bat "
            "顶部说明补齐：\n  " + "\n  ".join(missing))


def _java_bin(sign_root):
    """
    选定运行签名服务用的 java 可执行文件。

    优先项目内置的裁剪版 JRE（免装 Java），其次配置项 HONGGUO_JAVA_BIN，
    最后回退 PATH 上的 java。返回的是可执行文件的路径或命令名。
    """
    configured = getattr(settings, "HONGGUO_JAVA_BIN", "") or ""
    if configured and configured != "java":
        return configured
    bundled = sign_root / "jre" / "bin" / ("java.exe" if os.name == "nt" else "java")
    if bundled.exists():
        return str(bundled)
    return "java"


def _spawn():
    """拉起签名服务进程（调用方需持有 _spawn_lock）"""
    sign_root = Path(getattr(settings, "HONGGUO_SIGN_DIR",
                             str(Path(settings.BASE_DIR) / "scripts" / "hongguo_sign")))
    _check_artifacts(sign_root)

    java_bin = _java_bin(sign_root)
    if not (Path(java_bin).exists() if (os.path.isabs(java_bin) or os.sep in java_bin)
            else shutil.which(java_bin)):
        raise RuntimeError(
            f"找不到可用的 Java（{java_bin}）：请补齐 scripts/hongguo_sign/jre/，"
            f"或安装 JDK 17+ 后设置环境变量 HONGGUO_JAVA_BIN")

    _, port = _host_port()
    log_dir = Path(getattr(settings, "LOG_DIR", str(Path(settings.BASE_DIR) / "logs")))
    log_dir.mkdir(parents=True, exist_ok=True)

    cmd = [java_bin,
           "--add-opens", "java.base/java.lang=ALL-UNNAMED",
           "-cp", "unidbg-sign.jar", "com.hongguo.sign.FqTrace", "serve", str(port)]
    # Windows 下以服务/后台方式运行时避免弹出控制台窗口
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0

    global _process, _log_handle
    if _log_handle:                          # 上一次拉起的日志句柄（进程已退出）先释放
        _log_handle.close()
    # 句柄长期持有：子进程存活期间持续写日志
    _log_handle = open(log_dir / "hongguo_sign.log", "ab", buffering=0)
    _process = subprocess.Popen(cmd, cwd=str(sign_root / "sign"),
                                stdout=_log_handle, stderr=subprocess.STDOUT,
                                stdin=subprocess.DEVNULL, creationflags=creationflags)


def ensure_started():
    """
    确保签名服务可用；返回是否可用（不可用但不该本机拉起时返回 False）。

    本机地址且端口未监听时拉起进程并等待就绪，超时抛 RuntimeError。
    """
    if is_running():
        return True
    if not _is_local():
        return False

    with _spawn_lock:
        if is_running():                     # 等锁期间可能已被其他线程拉起
            return True
        timeout = int(getattr(settings, "HONGGUO_SIGN_START_TIMEOUT", 90))
        _spawn()
        deadline = time.time() + timeout
        while time.time() < deadline:
            if is_running():
                return True
            time.sleep(0.5)
        raise RuntimeError(f"红果签名服务启动超时（{timeout}s），"
                           f"详见 logs/hongguo_sign.log")
