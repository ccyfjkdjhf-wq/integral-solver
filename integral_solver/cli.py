"""命令行界面。"""

from __future__ import annotations

import argparse
import json
import sys

from . import __version__
from .core import IntegralError, solve_integral


def _configure_streams() -> None:
    """避免在不支持某些 Unicode 字符的终端里直接崩溃。"""

    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(errors="replace")
            except (ValueError, OSError):
                pass


def _print(text: str = "") -> None:
    try:
        print(text)
    except UnicodeEncodeError:
        encoding = (getattr(sys.stdout, "encoding", None) or "utf-8")
        print(text.encode(encoding, errors="replace").decode(encoding, errors="replace"))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python main.py --cli",
        description="积分求解器命令行版：计算定积分与不定积分。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例：\n"
            "  python main.py --cli \"x^2*sin(x)\"\n"
            "  python main.py --cli \"exp(-x^2)\" --bounds 0 oo\n"
            "  python main.py --cli \"1/(1+x^2)\" --bounds -oo oo --json\n"
            "  python main.py --cli\n"
        ),
    )
    parser.add_argument(
        "expression",
        nargs="?",
        help="被积函数，例如 x^2、sin(x)、exp(-x^2)；省略则进入交互模式。",
    )
    parser.add_argument(
        "-v",
        "--var",
        default="x",
        help="积分变量（默认：x）。",
    )
    parser.add_argument(
        "-b",
        "--bounds",
        nargs=2,
        metavar=("LOWER", "UPPER"),
        help="定积分的下限和上限，例如 --bounds 0 1 或 --bounds -oo oo。",
    )
    parser.add_argument(
        "--digits",
        type=int,
        default=15,
        help="数值近似和校验的有效数字位数（默认：15）。",
    )
    parser.add_argument(
        "--no-steps",
        action="store_true",
        help="只输出结果和校验，不输出推导步骤。",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="以 JSON 输出，便于其他程序调用。",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"积分求解器 {__version__}",
    )
    return parser


def _emit_json(payload: dict[str, object]) -> None:
    # 纯 ASCII 转义可以避免管道或重定向时受终端代码页影响。
    print(json.dumps(payload, ensure_ascii=True, indent=2))


def _run_once(
    expression: str,
    variable: str,
    lower: str | None,
    upper: str | None,
    digits: int,
    *,
    as_json: bool,
    include_steps: bool,
) -> int:
    try:
        result = solve_integral(
            expression,
            variable,
            lower,
            upper,
            digits=digits,
        )
    except IntegralError as exc:
        if as_json:
            _emit_json({"ok": False, "error": str(exc)})
        else:
            _print(f"错误：{exc}")
        return 2
    except KeyboardInterrupt:
        _print("\n已取消。")
        return 130
    except Exception as exc:  # noqa: BLE001
        if as_json:
            _emit_json({"ok": False, "error": f"未预期的错误：{exc}"})
        else:
            _print(f"未预期的错误：{exc}")
        return 1

    if as_json:
        _emit_json(result.to_dict())
    else:
        _print(result.to_text(include_steps=include_steps))
    return 0


def _print_banner() -> None:
    _print("=" * 62)
    _print("  积分求解器 · 命令行模式")
    _print("  支持不定积分、定积分、符号参数、无穷区间与发散判定")
    _print("=" * 62)
    _print("直接回车退出。示例：x^2*sin(x)、exp(-x^2)、1/(1+x^2)")
    _print("")


def _interactive(digits: int, include_steps: bool) -> int:
    if not sys.stdin.isatty():
        _print("当前没有交互式终端。请直接给出表达式，例如：")
        _print('  python main.py --cli "x^2" --bounds 0 1')
        return 2

    _print_banner()
    while True:
        try:
            expression = input("被积函数（回车退出）：").strip()
            if not expression:
                _print("再见。")
                return 0
            variable = input("积分变量 [x]：").strip() or "x"
            mode = input("类型 [1=不定积分，2=定积分]（默认 1）：").strip()
            lower = upper = None
            if mode in {"2", "定积分", "定"}:
                lower = input("积分下限（例如 0、-oo）：").strip()
                upper = input("积分上限（例如 1、oo）：").strip()
                if not lower or not upper:
                    _print("错误：定积分需要同时填写下限和上限。\n")
                    continue
        except (EOFError, KeyboardInterrupt):
            _print("\n再见。")
            return 0

        try:
            result = solve_integral(
                expression,
                variable,
                lower,
                upper,
                digits=digits,
            )
        except IntegralError as exc:
            _print(f"\n错误：{exc}\n")
            continue
        except Exception as exc:  # noqa: BLE001
            _print(f"\n未预期的错误：{exc}\n")
            continue

        _print("")
        _print(result.to_text(include_steps=include_steps))
        _print("")


def main(argv: list[str] | None = None) -> int:
    """命令行入口，返回进程退出码。"""

    _configure_streams()
    parser = _build_parser()
    args = parser.parse_args(argv)

    if not 6 <= args.digits <= 50:
        parser.error("--digits 必须在 6 到 50 之间。")

    if args.expression is None:
        if args.json:
            parser.error("--json 需要同时提供被积函数。")
        if args.bounds:
            parser.error("--bounds 需要同时提供被积函数。")
        return _interactive(args.digits, not args.no_steps)

    lower: str | None = None
    upper: str | None = None
    if args.bounds:
        lower, upper = args.bounds

    return _run_once(
        args.expression,
        args.var,
        lower,
        upper,
        args.digits,
        as_json=args.json,
        include_steps=not args.no_steps,
    )


if __name__ == "__main__":
    raise SystemExit(main())
