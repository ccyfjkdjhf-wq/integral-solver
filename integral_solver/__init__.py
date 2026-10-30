"""积分求解器：定积分与不定积分。"""

from .core import (
    CalculationError,
    InputError,
    IntegralError,
    IntegralResult,
    Step,
    Verification,
    format_expr,
    format_number,
    solve_integral,
)

__version__ = "1.0.0"

__all__ = [
    "__version__",
    "IntegralError",
    "InputError",
    "CalculationError",
    "IntegralResult",
    "Step",
    "Verification",
    "solve_integral",
    "format_expr",
    "format_number",
]
