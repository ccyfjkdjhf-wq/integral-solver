"""启动器：按需创建虚拟环境、安装 SymPy，然后启动图形界面或命令行。

批处理文件保持纯 ASCII，中文提示由本脚本输出，避免 cmd 编码问题。
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV = ROOT / ".venv"
VENV_PYTHON = VENV / "Scripts" / "python.exe"
VENV_PYTHONW = VENV / "Scripts" / "pythonw.exe"
REQUIREMENTS = ROOT / "requirements.txt"


def _configure_stdout() -> None:
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if callable(reconfigure):
        try:
            reconfigure(errors="replace")
        except (ValueError, OSError):
            pass


def _say(message: str = "") -> None:
    print(message, flush=True)


def _sympy_works(python: Path) -> bool:
    if not python.exists():
        return False
    try:
        completed = subprocess.run(
            [str(python), "-c", "import sympy"],
            cwd=ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return completed.returncode == 0


def _venv_is_usable() -> bool:
    if not VENV_PYTHON.exists():
        return False
    try:
        completed = subprocess.run(
            [str(VENV_PYTHON), "-c", "import sys"],
            cwd=ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return completed.returncode == 0


def _ensure_dependencies() -> Path:
    if _sympy_works(VENV_PYTHON):
        return VENV_PYTHON

    _say("首次运行，正在准备本地运行环境……")
    if VENV.exists() and not _venv_is_usable():
        _say("检测到旧环境已失效，正在重建……")
        shutil.rmtree(VENV)

    if not VENV_PYTHON.exists():
        base = shutil.which("python") or sys.executable
        _say(f"使用 Python：{base}")
        subprocess.check_call([base, "-m", "venv", str(VENV)], cwd=ROOT)

    if not (VENV / "Scripts" / "pip.exe").exists():
        subprocess.run(
            [str(VENV_PYTHON), "-m", "ensurepip", "--upgrade"],
            cwd=ROOT,
            check=False,
        )

    _say("正在安装 SymPy（首次运行需要联网，请稍候）……")
    subprocess.check_call(
        [
            str(VENV_PYTHON),
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "-r",
            str(REQUIREMENTS),
        ],
        cwd=ROOT,
    )
    if not _sympy_works(VENV_PYTHON):
        raise RuntimeError("SymPy 安装完成后仍无法导入。")
    _say("依赖安装完成。")
    return VENV_PYTHON


def _launch_gui(python: Path) -> int:
    executable = VENV_PYTHONW if VENV_PYTHONW.exists() else python
    creationflags = 0
    if sys.platform == "win32":
        creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)

    subprocess.Popen(
        [str(executable), str(ROOT / "main.py")],
        cwd=ROOT,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=creationflags,
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    _configure_stdout()
    args = list(sys.argv[1:] if argv is None else argv)

    if sys.version_info < (3, 10):
        _say("需要 Python 3.10 或更高版本，请升级后再运行。")
        return 1

    try:
        python = _ensure_dependencies()
    except KeyboardInterrupt:
        _say("\n已取消。")
        return 130
    except Exception as exc:  # noqa: BLE001
        _say("")
        _say(f"[错误] 依赖准备失败：{exc}")
        _say("")
        _say("请检查网络后重试，也可以手动执行：")
        _say("    python -m pip install -r requirements.txt")
        try:
            input("\n按 Enter 键关闭窗口……")
        except (EOFError, KeyboardInterrupt):
            pass
        return 1

    if args and args[0] == "--ensure-only":
        _say("运行环境已就绪。")
        return 0

    if args and args[0] == "--cli":
        return subprocess.call(
            [str(python), "-B", str(ROOT / "main.py"), "--cli", *args[1:]],
            cwd=ROOT,
        )

    return _launch_gui(python)


if __name__ == "__main__":
    raise SystemExit(main())
