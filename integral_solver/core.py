"""积分求解核心。

对外只暴露少量函数，GUI 和命令行共用同一套计算与校验逻辑。
"""

from __future__ import annotations

import re
import time
import warnings
from dataclasses import dataclass, field
from typing import Iterable, Literal

import sympy as sp
from sympy.calculus.accumulationbounds import AccumBounds
from sympy.parsing.sympy_parser import (
    convert_xor,
    function_exponentiation,
    implicit_application,
    implicit_multiplication,
    parse_expr,
    standard_transformations,
)

__all__ = [
    "IntegralError",
    "InputError",
    "CalculationError",
    "Step",
    "Verification",
    "IntegralResult",
    "solve_integral",
    "format_expr",
    "format_number",
]


class IntegralError(Exception):
    """所有可预期错误的基类，异常文本可直接展示给用户。"""


class InputError(IntegralError):
    """输入不合法。"""


class CalculationError(IntegralError):
    """输入合法，但计算阶段失败。"""


# ---------------------------------------------------------------------------
# 表达式解析
# ---------------------------------------------------------------------------

_FUNCTIONS: dict[str, object] = {
    "sin": sp.sin,
    "cos": sp.cos,
    "tan": sp.tan,
    "cot": sp.cot,
    "sec": sp.sec,
    "csc": sp.csc,
    "asin": sp.asin,
    "acos": sp.acos,
    "atan": sp.atan,
    "acot": sp.acot,
    "arcsin": sp.asin,
    "arccos": sp.acos,
    "arctan": sp.atan,
    "arccot": sp.acot,
    "sinh": sp.sinh,
    "cosh": sp.cosh,
    "tanh": sp.tanh,
    "coth": sp.coth,
    "asinh": sp.asinh,
    "acosh": sp.acosh,
    "atanh": sp.atanh,
    "exp": sp.exp,
    "log": sp.log,
    "ln": sp.log,
    "lg": lambda value: sp.log(value, 10),
    "log10": lambda value: sp.log(value, 10),
    "sqrt": sp.sqrt,
    "cbrt": sp.cbrt,
    "Abs": sp.Abs,
    "abs": sp.Abs,
    "sign": sp.sign,
    "floor": sp.floor,
    "ceiling": sp.ceiling,
    "factorial": sp.factorial,
    "gamma": sp.gamma,
    "loggamma": sp.loggamma,
    "erf": sp.erf,
    "erfc": sp.erfc,
    "erfi": sp.erfi,
    "Ei": sp.Ei,
    "li": sp.li,
    "Si": sp.Si,
    "Ci": sp.Ci,
    "Chi": sp.Chi,
    "Shi": sp.Shi,
    "LambertW": sp.LambertW,
    "besselj": sp.besselj,
    "bessely": sp.bessely,
    "besseli": sp.besseli,
    "besselk": sp.besselk,
    "sinc": sp.sinc,
    "Max": sp.Max,
    "Min": sp.Min,
    "re": sp.re,
    "im": sp.im,
    "conjugate": sp.conjugate,
}

_CONSTANTS: dict[str, object] = {
    "pi": sp.pi,
    "E": sp.E,
    "oo": sp.oo,
    "I": sp.I,
}

_SAFE_GLOBALS = {
    "__builtins__": {},
    "Symbol": sp.Symbol,
    "Integer": sp.Integer,
    "Float": sp.Float,
    "Number": sp.Number,
}

_TRANSFORMATIONS = standard_transformations + (
    convert_xor,
    implicit_multiplication,
    implicit_application,
    function_exponentiation,
)

_RESERVED_NAMES = set(_FUNCTIONS) | set(_CONSTANTS) | {
    "e",
    "nan",
    "zoo",
    "True",
    "False",
    "None",
    "Integral",
}

_SUPERSCRIPT_CHARS = {
    "⁰": "0",
    "¹": "1",
    "²": "2",
    "³": "3",
    "⁴": "4",
    "⁵": "5",
    "⁶": "6",
    "⁷": "7",
    "⁸": "8",
    "⁹": "9",
    "⁺": "+",
    "⁻": "-",
}

_SUBSCRIPT_CHARS = str.maketrans("0123456789+-=()", "₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎")
_SUPERSCRIPT_OUT = str.maketrans("0123456789+-=()", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾")

_CHAR_MAP = str.maketrans(
    {
        "−": "-",
        "–": "-",
        "—": "-",
        "×": "*",
        "·": "*",
        "⋅": "*",
        "÷": "/",
        "＋": "+",
        "－": "-",
        "＊": "*",
        "／": "/",
        "＾": "^",
        "（": "(",
        "）": ")",
        "，": ",",
        "：": ":",
        "　": " ",
        "≤": "<=",
        "≥": ">=",
        "≠": "!=",
        "π": " pi ",
        "∞": " oo ",
        "ⅇ": "e",
        "𝑑": "d",
        "ⅆ": "d",
        "∫": "",
    }
)

_FORBIDDEN_TOKENS = re.compile(
    r"(__|\b(?:import|lambda|exec|eval|compile|open|globals|locals|"
    r"getattr|setattr|delattr|subprocess|socket|shutil|pathlib)\b)",
    re.IGNORECASE,
)

_VARIABLE_RE = re.compile(r"^[A-Za-z_α-ωΑ-Ω][A-Za-z0-9_α-ωΑ-Ω]*$")


def validate_variable(variable: str) -> str:
    """检查积分变量名，返回去除空白后的名称。"""

    variable = (variable or "").strip()
    if not variable:
        raise InputError("请填写积分变量，例如 x。")
    if len(variable) > 20:
        raise InputError("积分变量名太长，请使用较短的名称，例如 x、t 或 u。")
    if not _VARIABLE_RE.fullmatch(variable):
        raise InputError(
            "积分变量只能是字母、数字或下划线组成的名称，且不能以数字开头。"
        )
    if variable in _RESERVED_NAMES:
        raise InputError(f"“{variable}”是内置函数或常量名，不能作为积分变量。")
    return variable


def _replace_superscripts(text: str) -> str:
    def repl(match: re.Match[str]) -> str:
        raw = "".join(_SUPERSCRIPT_CHARS[ch] for ch in match.group(0))
        return f"^({raw})"

    return re.sub(r"[⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻]+", repl, text)


def _replace_roots(text: str) -> str:
    # 兼容 √x、√(x+1) 这类写法；嵌套根式建议直接写 sqrt(...)。
    pattern = re.compile(r"√\s*(\([^()]*\)|[A-Za-z0-9_.]+)")

    def repl(match: re.Match[str]) -> str:
        body = match.group(1)
        return f"sqrt({body})"

    return pattern.sub(repl, text)


def _normalize_input(text: str, variable: str, *, strip_differential: bool = True) -> str:
    if not isinstance(text, str):
        raise InputError("表达式必须是文本。")
    text = text.strip()
    if not text:
        raise InputError("请输入被积函数，例如 x^2、sin(x) 或 exp(-x^2)。")
    if len(text) > 1000:
        raise InputError("表达式过长（超过 1000 个字符），请拆成较小的部分。")
    if _FORBIDDEN_TOKENS.search(text):
        raise InputError("表达式中包含不支持的名称，请只输入数学表达式。")

    text = _replace_roots(text)
    text = _replace_superscripts(text)
    text = text.translate(_CHAR_MAP)
    text = text.replace("√", "sqrt")

    # 去掉整体积分记号前后的空白和末尾的 dx，允许直接粘贴 ∫ x^2 dx。
    text = text.strip()
    if text.startswith("∫"):
        text = text[1:].strip()

    if strip_differential:
        differential = re.compile(
            r"(?:\s*[dD]\s*" + re.escape(variable) + r")\s*$"
        )
        text = differential.sub("", text).strip()

    # 绝对值为便于输入写成 |x| 时，转换成 Abs(x)。
    text = re.sub(r"\|([^|]+)\|", r"Abs(\1)", text)

    # 单独的 e 视为自然常数，避免和变量 e 冲突。
    if variable != "e":
        text = re.sub(r"(?<![A-Za-z0-9_])e(?![A-Za-z0-9_])", "E", text)

    text = text.strip()
    if not text:
        raise InputError("没有找到可计算的部分，请检查表达式。")
    return text


def _parse_expression(
    text: str,
    variable: str,
    symbol: sp.Symbol,
    *,
    label: str = "被积函数",
    strip_differential: bool = True,
) -> sp.Expr:
    normalized = _normalize_input(text, variable, strip_differential=strip_differential)
    local_dict: dict[str, object] = {
        **_FUNCTIONS,
        **_CONSTANTS,
        "e": sp.E,
        "nan": sp.nan,
        "zoo": sp.zoo,
    }
    local_dict[variable] = symbol

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            expr = parse_expr(
                normalized,
                local_dict=local_dict,
                global_dict=dict(_SAFE_GLOBALS),
                transformations=_TRANSFORMATIONS,
                evaluate=True,
            )
    except Exception as exc:  # noqa: BLE001 - 统一转换成友好的输入错误
        raise InputError(
            f"{label}无法解析。请检查括号、运算符或函数名。\n"
            f"输入：{text.strip()}\n"
            f"提示：乘法可写成 2*x 或 2x，乘方可写成 x^2，自然对数写 ln(x)。"
        ) from exc

    if not isinstance(expr, sp.Expr):
        raise InputError(f"{label}不是有效的数学表达式。")
    if expr.has(sp.nan):
        raise InputError(f"{label}的结果是未定义（nan），请检查输入。")
    return expr


# ---------------------------------------------------------------------------
# 结果数据结构
# ---------------------------------------------------------------------------


@dataclass
class Step:
    """一条推导步骤。"""

    title: str
    lines: list[str] = field(default_factory=list)


@dataclass
class Verification:
    """求导验算或数值积分校验的结果。"""

    status: Literal["verified", "sampled", "skipped", "warning", "failed"]
    title: str
    detail: str


@dataclass
class IntegralResult:
    """一次积分计算结果。"""

    kind: Literal["indefinite", "definite"]
    input_expression: str
    variable: str
    integrand: sp.Expr
    lower: sp.Expr | None = None
    upper: sp.Expr | None = None
    antiderivative: sp.Expr | None = None
    value: sp.Expr | None = None
    exact: bool = True
    numeric_text: str | None = None
    divergent: bool = False
    undefined: bool = False
    divergence_reason: str | None = None
    unevaluated: bool = False
    steps: list[Step] = field(default_factory=list)
    verification: Verification | None = None
    warnings: list[str] = field(default_factory=list)
    elapsed: float = 0.0

    @property
    def kind_label(self) -> str:
        return "不定积分" if self.kind == "indefinite" else "定积分"

    @property
    def formula_text(self) -> str:
        f = format_expr(self.integrand)
        var = self.variable
        if self.kind == "indefinite":
            if self.unevaluated:
                return f"∫ {f} d{var}（未找到初等原函数）"
            body = format_expr(self.antiderivative) if self.antiderivative is not None else "—"
            return f"∫ {f} d{var} = {body} + C"
        left = _integral_bounds_text(self.lower, self.upper)
        if self.unevaluated:
            if self.numeric_text:
                return f"{left} {f} d{var} ≈ {self.numeric_text}"
            return f"{left} {f} d{var}（未求出闭式结果）"
        right = format_expr(self.value) if self.value is not None else "—"
        return f"{left} {f} d{var} = {right}"

    @property
    def short_result(self) -> str:
        if self.unevaluated:
            return self.numeric_text or "—"
        if self.kind == "indefinite" and self.antiderivative is not None:
            return format_expr(self.antiderivative)
        if self.value is not None:
            return format_expr(self.value)
        return "—"

    def to_text(self, *, include_steps: bool = True) -> str:
        """返回适合命令行或剪贴板的纯文本报告。"""

        lines: list[str] = []
        lines.append(f"【{self.kind_label}】")
        lines.append(self.formula_text)
        if self.numeric_text:
            lines.append(f"数值近似：≈ {self.numeric_text}")
        if self.divergent:
            lines.append(f"注意：{self.divergence_reason or '该积分不收敛。'}")
        elif self.undefined:
            lines.append(f"注意：{self.divergence_reason or '该积分未定义。'}")
        if not self.exact:
            lines.append("说明：未找到精确原函数，结果可能以积分号或数值形式给出。")
        if self.verification:
            lines.append("")
            lines.append("【校验】")
            lines.append(f"{self.verification.title}")
            if self.verification.detail:
                lines.append(self.verification.detail)
        if include_steps and self.steps:
            lines.append("")
            lines.append("【推导步骤】")
            for index, step in enumerate(self.steps, start=1):
                lines.append(f"{index}. {step.title}")
                for step_line in step.lines:
                    lines.append(f"   {step_line}")
        if self.warnings:
            lines.append("")
            lines.append("【提示】")
            for warning in self.warnings:
                lines.append(f"• {warning}")
        lines.append("")
        lines.append(f"用时：{self.elapsed:.2f} 秒")
        return "\n".join(lines)

    def to_dict(self) -> dict[str, object]:
        """返回可 JSON 序列化的结果。"""

        return {
            "ok": True,
            "kind": self.kind,
            "kind_label": self.kind_label,
            "input_expression": self.input_expression,
            "variable": self.variable,
            "integrand": str(self.integrand),
            "integrand_display": format_expr(self.integrand),
            "lower": None if self.lower is None else str(self.lower),
            "upper": None if self.upper is None else str(self.upper),
            "antiderivative": None
            if self.antiderivative is None
            else str(self.antiderivative),
            "antiderivative_display": None
            if self.antiderivative is None
            else format_expr(self.antiderivative),
            "value": None if self.value is None else str(self.value),
            "value_display": None if self.value is None else format_expr(self.value),
            "formula": self.formula_text,
            "numeric": self.numeric_text,
            "exact": self.exact,
            "divergent": self.divergent,
            "undefined": self.undefined,
            "divergence_reason": self.divergence_reason,
            "unevaluated": self.unevaluated,
            "warnings": list(self.warnings),
            "steps": [
                {"title": step.title, "lines": list(step.lines)}
                for step in self.steps
            ],
            "verification": None
            if self.verification is None
            else {
                "status": self.verification.status,
                "title": self.verification.title,
                "detail": self.verification.detail,
            },
            "elapsed_seconds": round(self.elapsed, 3),
        }


# ---------------------------------------------------------------------------
# 格式化
# ---------------------------------------------------------------------------


def format_number(value: sp.Expr | complex, digits: int = 15) -> str:
    """把数值格式化为简短、可读的十进制表示。"""

    digits = max(6, min(int(digits), 50))
    try:
        number = sp.N(value, digits)
    except Exception:  # noqa: BLE001
        return str(value)
    if number in (sp.oo, -sp.oo):
        return "∞" if number is sp.oo else "-∞"
    if number is sp.zoo or number is sp.nan:
        return "未定义"
    try:
        if number.is_real:
            real = float(number)
            if abs(real) != 0 and (abs(real) < 1e-4 or abs(real) >= 1e14):
                return f"{real:.{max(1, digits - 1)}e}"
            return f"{real:.{digits}g}"
        complex_value = complex(number)
        real_part = f"{complex_value.real:.{digits}g}"
        imag_part = f"{abs(complex_value.imag):.{digits}g}"
        sign = "+" if complex_value.imag >= 0 else "-"
        return f"{real_part} {sign} {imag_part}i"
    except (TypeError, ValueError, OverflowError):
        return _pretty_expression_text(
            sp.sstr(number, order="none", full_prec=False)
        )


def _format_power(match: re.Match[str]) -> str:
    exponent = match.group(1)
    if re.fullmatch(r"-?\d+", exponent):
        translated = exponent.translate(_SUPERSCRIPT_OUT)
        return translated
    return f"^({exponent})"


def _pretty_expression_text(text: str) -> str:
    """把 SymPy 的 ASCII 字符串转换为适合界面阅读的 Unicode 文本。"""

    # 整数次幂使用上标；其他幂保留 ^(...)。
    text = re.sub(r"\*\*\(([^()]*)\)", _format_power, text)
    text = re.sub(r"\*\*(-?\d+)", _format_power, text)
    text = text.replace("**", "^")

    # 去掉 sqrt 的最外层括号，保留内部结构。
    text = re.sub(r"\bsqrt\(([^()]*)\)", r"√(\1)", text)
    text = re.sub(r"\bAbs\(([^()]*)\)", r"|\1|", text)

    replacements = (
        (r"\bpi\b", "π"),
        (r"\boo\b", "∞"),
        (r"\bzoo\b", "未定义"),
        (r"\bnan\b", "未定义"),
        (r"\bE\b", "e"),
        (r"\bI\b", "i"),
        (r"\blog\(", "ln("),
        (r"\basin\(", "arcsin("),
        (r"\bacos\(", "arccos("),
        (r"\batan\(", "arctan("),
        (r"\bacot\(", "arccot("),
        (r"\basinh\(", "arsinh("),
        (r"\bacosh\(", "arcosh("),
        (r"\batanh\(", "artanh("),
        (r"\bconjugate\(", "conj("),
    )
    for pattern, replacement in replacements:
        text = re.sub(pattern, replacement, text)

    text = text.replace("*", "·")
    text = text.replace(" + -", " - ")
    text = text.replace(" - -", " + ")
    return text


def format_expr(expr: sp.Expr | None) -> str:
    """把 SymPy 表达式转换成界面中显示的数学文本。"""

    if expr is None:
        return "—"
    if isinstance(expr, AccumBounds):
        return f"[{format_expr(expr.min)}, {format_expr(expr.max)}]（振荡）"
    if isinstance(expr, sp.Integral) and len(expr.limits) == 1:
        limit = expr.limits[0]
        inner = format_expr(expr.function)
        if len(limit) == 1:
            return f"∫ {inner} d{limit[0]}"
        if len(limit) == 3:
            return (
                f"{_integral_bounds_text(limit[1], limit[2])} "
                f"{inner} d{limit[0]}"
            )
    try:
        raw = sp.sstr(expr, order="none", full_prec=False)
    except Exception:  # noqa: BLE001
        raw = str(expr)
    return _pretty_expression_text(raw)


def _to_subscript(text: str) -> str | None:
    if text and all(ch in "0123456789+-=()" for ch in text):
        return text.translate(_SUBSCRIPT_CHARS)
    return None


def _to_superscript(text: str) -> str | None:
    if text and all(ch in "0123456789+-=()" for ch in text):
        return text.translate(_SUPERSCRIPT_OUT)
    return None


def _bound_operand(text: str) -> str:
    """给无法用上下标表示的上/下限加上必要的括号。"""

    if len(text) <= 1 or text in {"∞", "π"}:
        return text
    return f"({text})"


def _integral_bounds_text(lower: sp.Expr | None, upper: sp.Expr | None) -> str:
    lower_text = format_expr(lower)
    upper_text = format_expr(upper)
    lower_sub = _to_subscript(lower_text)
    upper_sup = _to_superscript(upper_text)
    if lower_sub is not None and upper_sup is not None:
        return f"∫{lower_sub}{upper_sup}"
    lower_part = lower_sub if lower_sub is not None else f"_{_bound_operand(lower_text)}"
    upper_part = upper_sup if upper_sup is not None else f"^{_bound_operand(upper_text)}"
    return f"∫{lower_part}{upper_part}"


# ---------------------------------------------------------------------------
# 计算辅助
# ---------------------------------------------------------------------------


def _simplify(expr: sp.Expr) -> sp.Expr:
    """尽量化简，同时保证化简失败时仍返回原表达式。"""

    for function in (sp.trigsimp, sp.simplify):
        try:
            simplified = function(expr)
        except Exception:  # noqa: BLE001
            continue
        if isinstance(simplified, sp.Expr):
            expr = simplified
    return expr


def _contains_unevaluated_integral(expr: sp.Expr) -> bool:
    return any(isinstance(atom, sp.Integral) for atom in expr.atoms(sp.Integral))


def _classify_special(value: sp.Expr) -> tuple[bool, bool, str | None]:
    """返回 (是否发散, 是否未定义, 原因)。"""

    if isinstance(value, AccumBounds):
        return True, False, "积分不收敛：结果在有限范围内持续振荡。"
    if value is sp.nan or value.has(sp.nan):
        return False, True, "积分未定义；被积函数可能在区间内存在奇点。"
    if value is sp.zoo or value.has(sp.zoo):
        return False, True, "积分不存在（出现无穷大或未定义点）。"
    if value is sp.oo or value is -sp.oo or value.has(sp.oo) or value.has(-sp.oo):
        return True, False, "积分发散（结果趋于无穷大）。"
    return False, False, None


def _is_real_number(expr: sp.Expr) -> bool:
    return not expr.free_symbols and expr.is_real is True and expr.is_finite is not False


def _safe_numeric(expr: sp.Expr, digits: int = 15) -> str | None:
    if expr.free_symbols:
        return None
    try:
        number = sp.N(expr, max(digits, 15))
    except Exception:  # noqa: BLE001
        return None
    if number in (sp.oo, -sp.oo) or number is sp.zoo or number is sp.nan:
        return None
    if number.has(sp.oo, -sp.oo, sp.zoo, sp.nan):
        return None
    if number.is_real is False:
        try:
            value = complex(number)
        except (TypeError, ValueError):
            return None
        if abs(value.imag) < 1e-14 * max(1.0, abs(value.real)):
            return format_number(value.real, digits)
        return format_number(number, digits)
    return format_number(number, digits)


def _close(left: complex, right: complex) -> bool:
    scale = max(1.0, abs(left), abs(right))
    return abs(left - right) <= 1e-7 * scale


def _numeric_sample_verification(
    derivative: sp.Expr,
    integrand: sp.Expr,
    variable: sp.Symbol,
) -> tuple[bool, int, str | None]:
    """当符号化简无法判断时，在若干实数点抽样比较。"""

    if (derivative.free_symbols - {variable}) or (integrand.free_symbols - {variable}):
        # 还有参数时改用符号差判断；这里不做采样。
        return False, 0, "表达式含参数，无法用固定数值点抽样。"

    samples = [-3.7, -2.3, -1.1, -0.37, 0.0, 0.37, 1.1, 2.3, 3.7]
    checked = 0
    errors: list[str] = []
    for point in samples:
        try:
            lhs = complex(sp.N(derivative.subs(variable, point), 30))
            rhs = complex(sp.N(integrand.subs(variable, point), 30))
        except (TypeError, ValueError, ZeroDivisionError, OverflowError):
            continue
        if not (abs(lhs) < 1e300 and abs(rhs) < 1e300):
            continue
        checked += 1
        if not _close(lhs, rhs):
            errors.append(
                f"x={point:g} 时，F'(x)≈{lhs:.10g}，f(x)≈{rhs:.10g}"
            )
    if checked < 3:
        return False, checked, "可用的实数采样点不足，未完成数值抽检。"
    if errors:
        return False, checked, "；".join(errors[:3])
    return True, checked, None


def _differentiate_verification(
    antiderivative: sp.Expr,
    integrand: sp.Expr,
    variable: sp.Symbol,
) -> Verification:
    try:
        derivative = sp.diff(antiderivative, variable)
        difference = derivative - integrand
        simplified_difference = _simplify(difference)
    except Exception as exc:  # noqa: BLE001
        return Verification(
            "skipped",
            "未完成求导校验",
            f"求导或化简时出现异常：{exc}",
        )

    if simplified_difference == 0:
        detail = (
            f"d/d{ variable } [{format_expr(antiderivative)}] = "
            f"{format_expr(_simplify(derivative))}\n"
            "与原被积函数完全一致，原函数正确。"
        )
        return Verification("verified", "✓ 求导校验通过", detail)

    sampled_ok, checked, sample_error = _numeric_sample_verification(
        derivative,
        integrand,
        variable,
    )
    if sampled_ok:
        detail = (
            f"符号化简后的差为 {format_expr(simplified_difference)}，未直接化为 0；\n"
            f"在 {checked} 个实数采样点上，F'(x) 与 f(x) 的数值一致（相对误差 < 1e-7）。"
        )
        return Verification("sampled", "✓ 数值抽检通过", detail)

    detail = (
        f"求导得到：{format_expr(derivative)}\n"
        f"与输入的差：{format_expr(simplified_difference)}"
    )
    if sample_error:
        detail += f"\n{sample_error}"
    return Verification("failed", "✗ 求导校验未通过", detail)


def _numeric_definite_check(
    integrand: sp.Expr,
    variable: sp.Symbol,
    lower: sp.Expr,
    upper: sp.Expr,
    exact_value: sp.Expr,
    digits: int,
) -> Verification:
    """用独立数值积分交叉检查定积分结果。"""

    if exact_value.free_symbols:
        return Verification("skipped", "未做数值校验", "结果含符号参数，跳过固定数值校验。")
    if lower.free_symbols or upper.free_symbols:
        return Verification("skipped", "未做数值校验", "积分限含符号参数，跳过固定数值校验。")
    if lower.is_extended_real is not True or upper.is_extended_real is not True:
        return Verification("skipped", "未做数值校验", "积分限不是实数，跳过数值校验。")

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            numerical = sp.Integral(integrand, (variable, lower, upper)).evalf(
                max(12, min(digits, 30))
            )
    except Exception as exc:  # noqa: BLE001
        return Verification(
            "skipped",
            "数值校验不可用",
            f"数值积分未能完成：{exc}",
        )

    if numerical in (sp.oo, -sp.oo) or numerical is sp.nan or numerical is sp.zoo:
        return Verification(
            "warning",
            "数值校验未完成",
            "数值积分未得到有限值，无法用数值方法确认结果。",
        )

    try:
        lhs = complex(sp.N(exact_value, 30))
        rhs = complex(sp.N(numerical, 30))
    except (TypeError, ValueError, OverflowError):
        return Verification("skipped", "数值校验不可用", "结果无法转换为数值。")

    if not (abs(lhs) < 1e300 and abs(rhs) < 1e300):
        return Verification("warning", "数值校验未完成", "结果数值过大，无法可靠比较。")

    exact_text = format_number(lhs, max(10, digits))
    numeric_text = format_number(rhs, max(10, digits))
    if _close(lhs, rhs):
        detail = (
            f"解析结果 ≈ {exact_text}\n"
            f"独立数值积分 ≈ {numeric_text}\n"
            "两者一致（相对误差 < 1e-7）。"
        )
        return Verification("verified", "✓ 数值积分校验通过", detail)

    # 数值积分对强振荡、端点奇点可能不准确，提示而不直接断言解析结果错误。
    detail = (
        f"解析结果 ≈ {exact_text}\n"
        f"独立数值积分 ≈ {numeric_text}\n"
        "两者差异较大。可能是数值积分在振荡或奇点附近不收敛，"
        "也可能解析结果受分支/主值影响，建议检查积分区间和奇点。"
    )
    return Verification("warning", "⚠ 数值校验有差异", detail)


def _collect_free_parameters(
    expressions: Iterable[sp.Expr],
    variable: sp.Symbol,
) -> list[sp.Symbol]:
    result: set[sp.Symbol] = set()
    for expr in expressions:
        result.update(expr.free_symbols)
    result.discard(variable)
    return sorted(result, key=str)


# ---------------------------------------------------------------------------
# 顶层接口
# ---------------------------------------------------------------------------


def solve_integral(
    expression: str,
    variable: str = "x",
    lower: str | None = None,
    upper: str | None = None,
    *,
    digits: int = 15,
) -> IntegralResult:
    """计算不定积分或定积分。

    参数
    ----
    expression:
        被积函数文本，例如 ``"x^2*sin(x)"``。
    variable:
        积分变量，默认 ``"x"``。
    lower, upper:
        定积分的下限和上限；两者都为空时计算不定积分。
        支持 ``0``、``pi``、``oo`` 等 SymPy 可解析的表达式。
    digits:
        数值近似和校验的有效数字位数。

    返回
    ----
    IntegralResult
        包含公式、步骤、校验和提示的结果对象。
    """

    started = time.perf_counter()
    expression = (expression or "").strip()
    if not expression:
        raise InputError("请输入被积函数，例如 x^2、sin(x) 或 exp(-x^2)。")
    variable = validate_variable(variable)
    digits = max(6, min(int(digits), 50))

    lower = None if lower is None or str(lower).strip() == "" else str(lower).strip()
    upper = None if upper is None or str(upper).strip() == "" else str(upper).strip()
    if (lower is None) != (upper is None):
        raise InputError("定积分需要同时填写下限和上限；只填一个无法计算。")
    definite = lower is not None

    x = sp.Symbol(variable, real=True)
    integrand = _parse_expression(expression, variable, x, label="被积函数")

    lower_expr: sp.Expr | None = None
    upper_expr: sp.Expr | None = None
    if definite:
        assert lower is not None and upper is not None
        lower_expr = _parse_expression(
            lower,
            variable,
            x,
            label="积分下限",
            strip_differential=False,
        )
        upper_expr = _parse_expression(
            upper,
            variable,
            x,
            label="积分上限",
            strip_differential=False,
        )
        for bound, bound_label in ((lower_expr, "下限"), (upper_expr, "上限")):
            if bound.has(x):
                raise InputError(f"积分{bound_label}不能包含积分变量 {variable}。")
            if bound.has(sp.Integral):
                raise InputError(f"积分{bound_label}不能是未计算的积分。")

    warnings_list: list[str] = []
    parameters = _collect_free_parameters(
        [integrand] + ([lower_expr, upper_expr] if definite else []),
        x,
    )
    if parameters:
        names = "、".join(str(parameter) for parameter in parameters)
        warnings_list.append(
            f"表达式中还包含符号参数：{names}。结果会保留这些参数；"
            "若需要数值，请先为参数代入具体值。"
        )

    if not integrand.has(x):
        if parameters:
            warnings_list.append(
                f"被积函数不含 {variable}，因此按“关于 {variable} 的常函数”处理。"
            )
        else:
            warnings_list.append(
                f"被积函数是常数；请确认是否想对 {variable} 积分。"
            )

    if definite:
        result = _solve_definite(
            expression=expression,
            variable=variable,
            x=x,
            integrand=integrand,
            lower_text=lower or "",
            upper_text=upper or "",
            lower=lower_expr,
            upper=upper_expr,
            digits=digits,
            warnings_list=warnings_list,
        )
    else:
        result = _solve_indefinite(
            expression=expression,
            variable=variable,
            x=x,
            integrand=integrand,
            warnings_list=warnings_list,
        )

    result.elapsed = time.perf_counter() - started
    return result


def _solve_indefinite(
    *,
    expression: str,
    variable: str,
    x: sp.Symbol,
    integrand: sp.Expr,
    warnings_list: list[str],
) -> IntegralResult:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            antiderivative = sp.integrate(integrand, x)
    except Exception as exc:  # noqa: BLE001
        raise CalculationError(
            "积分器无法处理这个表达式。\n"
            "可以尝试先展开、化简，或改用数值定积分。\n"
            f"底层信息：{exc}"
        ) from exc

    if not isinstance(antiderivative, sp.Expr):
        raise CalculationError("积分器返回了无法识别的结果。")

    unevaluated = _contains_unevaluated_integral(antiderivative)
    if not unevaluated:
        antiderivative = _simplify(antiderivative)
        if _contains_unevaluated_integral(antiderivative):
            unevaluated = True
    else:
        warnings_list.append(
            "SymPy 未能找到初等原函数，结果保留为积分形式。"
            "这仍然是精确表达式，但可能无法进一步化简。"
        )

    if not unevaluated:
        verification = _differentiate_verification(antiderivative, integrand, x)
    else:
        verification = Verification(
            "skipped",
            "未做求导校验",
            "原函数仍未求出，无法进行求导校验。",
        )

    steps = [
        Step(
            "识别被积函数",
            [f"f({variable}) = {format_expr(integrand)}"],
        ),
    ]
    if unevaluated:
        steps.append(
            Step(
                "求不定积分",
                [
                    "已尝试标准积分规则，但未能找到初等原函数。",
                    f"精确形式：{format_expr(antiderivative)}",
                ],
            )
        )
        steps.append(
            Step(
                "说明",
                [
                    "该积分可能没有初等原函数，程序保留了未计算的积分形式。",
                    "如需数值结果，请改用定积分并填写积分区间。",
                ],
            )
        )
    else:
        steps.append(
            Step(
                "求不定积分",
                [
                    f"∫ {format_expr(integrand)} d{variable} = "
                    f"{format_expr(antiderivative)} + C",
                    "其中 C 为任意常数。",
                ],
            )
        )
        steps.append(
            Step(
                "求导校验",
                [
                    f"d/d{variable} [{format_expr(antiderivative)}] = "
                    f"{format_expr(_simplify(sp.diff(antiderivative, x)))}",
                    "结果应等于原被积函数。",
                ],
            )
        )

    return IntegralResult(
        kind="indefinite",
        input_expression=expression,
        variable=variable,
        integrand=integrand,
        antiderivative=antiderivative,
        value=antiderivative,
        exact=not unevaluated,
        unevaluated=unevaluated,
        steps=steps,
        verification=verification,
        warnings=warnings_list,
    )


def _solve_definite(
    *,
    expression: str,
    variable: str,
    x: sp.Symbol,
    integrand: sp.Expr,
    lower_text: str,
    upper_text: str,
    lower: sp.Expr,
    upper: sp.Expr,
    digits: int,
    warnings_list: list[str],
) -> IntegralResult:
    assert lower is not None and upper is not None
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            value = sp.integrate(integrand, (x, lower, upper))
    except Exception as exc:  # noqa: BLE001
        # 符号积分失败时，如果被积函数和上下限都是数值，仍尝试数值积分。
        numeric_text: str | None = None
        numeric_value: sp.Expr | None = None
        if not (integrand.free_symbols - {x}) and not lower.free_symbols and not upper.free_symbols:
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", DeprecationWarning)
                    numerical = sp.Integral(integrand, (x, lower, upper)).evalf(digits)
                if (
                    numerical not in (sp.oo, -sp.oo, sp.zoo, sp.nan)
                    and not numerical.has(sp.oo, -sp.oo, sp.zoo, sp.nan)
                ):
                    numeric_text = format_number(numerical, digits)
                    numeric_value = sp.N(numerical, digits)
            except Exception:  # noqa: BLE001
                pass
        if numeric_text is None or numeric_value is None:
            raise CalculationError(
                "定积分计算失败。请检查被积函数在区间内是否有奇点，"
                "或尝试换一种等价写法。\n"
                f"底层信息：{exc}"
            ) from exc
        warnings_list.append("符号积分失败，已改用数值积分，结果不是精确值。")
        value = numeric_value
        result = IntegralResult(
            kind="definite",
            input_expression=expression,
            variable=variable,
            integrand=integrand,
            lower=lower,
            upper=upper,
            antiderivative=None,
            value=value,
            exact=False,
            numeric_text=numeric_text,
            divergent=False,
            steps=[
                Step(
                    "识别积分",
                    [
                        f"{_integral_bounds_text(lower, upper)} "
                        f"{format_expr(integrand)} d{variable}"
                    ],
                ),
                Step("数值积分", [f"结果 ≈ {numeric_text}"]),
            ],
            verification=Verification(
                "skipped",
                "仅数值结果",
                "符号积分失败，结果由数值积分给出，未做求导校验。",
            ),
            warnings=warnings_list,
        )
        return result

    if not isinstance(value, sp.Expr):
        raise CalculationError("积分器返回了无法识别的结果。")

    unevaluated = _contains_unevaluated_integral(value)
    is_divergent, is_undefined, reason = _classify_special(value)
    if not is_divergent and not is_undefined and not unevaluated:
        value = _simplify(value)
        is_divergent, is_undefined, reason = _classify_special(value)

    numeric_text = _safe_numeric(value, digits) if not unevaluated else None
    if unevaluated:
        # 定积分有时无法找到闭式原函数，但可以独立做数值积分。
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", DeprecationWarning)
                numerical = sp.Integral(integrand, (x, lower, upper)).evalf(digits)
            if numerical not in (sp.oo, -sp.oo) and numerical is not sp.nan:
                numeric_text = format_number(numerical, digits)
                warnings_list.append(
                    "未能求出精确的闭式结果，已给出数值积分近似值。"
                )
        except Exception:  # noqa: BLE001
            warnings_list.append(
                "未能求出闭式结果，且数值积分也未完成。"
            )

    # 复数分支或主值提示。
    if (
        not is_divergent
        and not is_undefined
        and not value.free_symbols
        and value.is_real is False
    ):
        warnings_list.append(
            "结果含虚部。若被积函数在实数区间内取实值，请检查区间内的奇点或分支。"
        )

    exact = not unevaluated
    if is_undefined:
        warnings_list.append(reason or "积分未定义。")
    elif is_divergent:
        warnings_list.append(reason or "积分发散。")

    verification: Verification
    if is_divergent or is_undefined:
        verification = Verification(
            "skipped",
            "无需数值校验",
            "该积分发散或未定义，不存在有限的数值结果。",
        )
    elif unevaluated and numeric_text is None:
        verification = Verification(
            "skipped",
            "未做数值校验",
            "没有可用于校验的数值结果。",
        )
    elif unevaluated:
        verification = Verification(
            "skipped",
            "仅有数值结果",
            "符号积分未求出闭式原函数；数值结果无法通过独立原函数验证。",
        )
    else:
        verification = _numeric_definite_check(
            integrand, x, lower, upper, value, digits
        )

    upper_minus_lower_text = format_expr(value)
    steps: list[Step] = [
        Step(
            "识别积分",
            [
                f"{_integral_bounds_text(lower, upper)} "
                f"{format_expr(integrand)} d{variable}",
                f"积分区间：[{format_expr(lower)}, {format_expr(upper)}]",
            ],
        )
    ]

    if not unevaluated:
        try:
            antiderivative = sp.integrate(integrand, x)
            if _contains_unevaluated_integral(antiderivative):
                antiderivative = None
            else:
                antiderivative = _simplify(antiderivative)
        except Exception:  # noqa: BLE001
            antiderivative = None
    else:
        antiderivative = None

    if antiderivative is not None:
        steps.append(
            Step(
                "求原函数",
                [
                    f"F({variable}) = ∫ {format_expr(integrand)} d{variable} = "
                    f"{format_expr(antiderivative)}"
                ],
            )
        )
        steps.append(
            Step(
                "牛顿–莱布尼茨公式",
                [
                    f"{_integral_bounds_text(lower, upper)} "
                    f"f({variable}) d{variable} = F({format_expr(upper)}) - "
                    f"F({format_expr(lower)})",
                    f"= {format_expr(antiderivative.subs(x, upper))} - "
                    f"({format_expr(antiderivative.subs(x, lower))})",
                ],
            )
        )
    if unevaluated:
        steps.append(
            Step(
                "闭式结果",
                [
                    "未能求出紧凑的闭式结果。",
                    "数值积分结果已在上方给出。"
                    if numeric_text
                    else "当前也无法给出可靠的数值结果。",
                ],
            )
        )
    else:
        steps.append(
            Step(
                "化简结果",
                [f"= {upper_minus_lower_text}"],
            )
        )
        if numeric_text:
            steps.append(Step("数值近似", [f"≈ {numeric_text}"]))
    if is_divergent or is_undefined:
        steps.append(
            Step(
                "结论",
                [
                    f"该定积分{'发散' if is_divergent else '未定义'}。",
                    reason or "请检查积分区间内是否存在奇点。",
                ],
            )
        )

    return IntegralResult(
        kind="definite",
        input_expression=expression,
        variable=variable,
        integrand=integrand,
        lower=lower,
        upper=upper,
        antiderivative=antiderivative,
        value=value,
        exact=exact,
        numeric_text=numeric_text,
        divergent=is_divergent,
        undefined=is_undefined,
        divergence_reason=reason,
        unevaluated=unevaluated,
        steps=steps,
        verification=verification,
        warnings=warnings_list,
    )
