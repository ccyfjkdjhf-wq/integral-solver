"""积分求解器入口。

默认启动图形界面；加上 --cli 后使用命令行模式。

    python main.py
    python main.py --cli "x^2" --bounds 0 1
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

HELP_TEXT = """积分求解器 · 定积分与不定积分

用法：
  python main.py
      启动图形界面。

  python main.py --cli "x^2" --bounds 0 1
      命令行计算定积分。

  python main.py --cli "sin(x)"
      命令行计算不定积分。

  python main.py --cli
      进入命令行交互模式。

更多命令行选项：
  python main.py --cli --help
"""


def _show_dependency_error(error: Exception) -> None:
    message = (
        f"程序缺少运行依赖：{error}\n\n"
        "请先运行“启动积分求解器.bat”（会自动安装依赖），"
        "或在项目目录中执行：\n\n"
        "  python -m pip install -r requirements.txt"
    )
    try:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("积分求解器 · 无法启动", message)
        root.destroy()
    except Exception:  # noqa: BLE001
        if sys.stderr is not None:
            print(message, file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)

    if "--version" in args:
        try:
            from integral_solver import __version__

            print(f"积分求解器 {__version__}")
        except Exception:  # noqa: BLE001
            print("积分求解器")
        return 0

    if "--help" in args or "-h" in args:
        if "--cli" not in args:
            print(HELP_TEXT)
            return 0

    if "--cli" in args:
        args.remove("--cli")
        try:
            from integral_solver.cli import main as cli_main
        except ModuleNotFoundError as exc:
            print(
                f"缺少运行依赖：{exc}\n"
                "请执行：python -m pip install -r requirements.txt",
                file=sys.stderr,
            )
            return 1
        return cli_main(args)

    unknown = [arg for arg in args if arg.strip()]
    if unknown:
        print(
            "未知参数：" + " ".join(unknown) + "\n"
            "启动图形界面请直接运行 python main.py；"
            "命令行模式请加 --cli。",
            file=sys.stderr,
        )
        return 2

    try:
        from integral_solver.gui import run

        run()
    except ModuleNotFoundError as exc:
        _show_dependency_error(exc)
        return 1
    except Exception as exc:  # noqa: BLE001
        try:
            import tkinter as tk
            from tkinter import messagebox

            root = tk.Tk()
            root.withdraw()
            messagebox.showerror("积分求解器 · 错误", f"程序启动失败：\n\n{exc}")
            root.destroy()
        except Exception:  # noqa: BLE001
            print(f"程序启动失败：{exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
