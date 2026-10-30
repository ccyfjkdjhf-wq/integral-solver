from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import sympy as sp

from integral_solver import InputError, format_expr, solve_integral

X = sp.Symbol("x", real=True)


class IndefiniteIntegralTests(unittest.TestCase):
    def assert_equivalent(self, actual: sp.Expr, expected: sp.Expr) -> None:
        self.assertEqual(sp.simplify(actual - expected), 0)

    def test_polynomial(self) -> None:
        result = solve_integral("x^2")
        self.assertEqual(result.kind, "indefinite")
        self.assert_equivalent(result.antiderivative, X**3 / 3)
        self.assertEqual(result.verification.status, "verified")
        self.assertIn("+ C", result.formula_text)

    def test_trigonometric_and_differentiation_check(self) -> None:
        result = solve_integral("x^2*sin(x)")
        self.assert_equivalent(
            result.antiderivative,
            (2 - X**2) * sp.cos(X) + 2 * X * sp.sin(X),
        )
        self.assertEqual(result.verification.status, "verified")

    def test_unicode_superscript_and_root(self) -> None:
        result = solve_integral("x² + √x", "x")
        self.assert_equivalent(
            result.antiderivative,
            X**3 / 3 + sp.Rational(2, 3) * X ** sp.Rational(3, 2),
        )

    def test_pi_implicit_multiplication(self) -> None:
        result = solve_integral("πx", "x", "0", "2")
        self.assert_equivalent(result.value, 2 * sp.pi)

    def test_absolute_value(self) -> None:
        result = solve_integral("|x|", "x", "-1", "1")
        self.assert_equivalent(result.value, 1)

    def test_natural_constant_and_log(self) -> None:
        exponential = solve_integral("e^x")
        self.assert_equivalent(exponential.antiderivative, sp.exp(X))
        logarithm = solve_integral("ln(x)")
        self.assert_equivalent(
            logarithm.antiderivative,
            X * sp.log(X) - X,
        )

    def test_symbolic_parameter(self) -> None:
        result = solve_integral("a*x")
        self.assert_equivalent(result.antiderivative, sp.Symbol("a") * X**2 / 2)
        self.assertTrue(any("符号参数" in warning for warning in result.warnings))

    def test_unevaluated_integral_is_reported(self) -> None:
        result = solve_integral("x!")
        self.assertTrue(result.unevaluated)
        self.assertFalse(result.exact)
        self.assertIn("未找到初等原函数", result.formula_text)
        self.assertEqual(result.verification.status, "skipped")


class DefiniteIntegralTests(unittest.TestCase):
    def assert_equivalent(self, actual: sp.Expr, expected: sp.Expr) -> None:
        self.assertEqual(sp.simplify(actual - expected), 0)

    def test_rational_result(self) -> None:
        result = solve_integral("x^2", "x", "0", "1")
        self.assertEqual(result.kind, "definite")
        self.assert_equivalent(result.value, sp.Rational(1, 3))
        self.assertEqual(result.verification.status, "verified")
        self.assertIn("∫₀¹", result.formula_text)

    def test_trigonometric_result(self) -> None:
        result = solve_integral("sin(x)", "x", "0", "pi")
        self.assert_equivalent(result.value, 2)
        self.assertEqual(result.verification.status, "verified")

    def test_gaussian_improper_integral(self) -> None:
        result = solve_integral("exp(-x^2)", "x", "0", "oo")
        self.assert_equivalent(result.value, sp.sqrt(sp.pi) / 2)
        self.assertEqual(result.verification.status, "verified")
        self.assertAlmostEqual(float(result.value), 0.886226925452758, places=12)

    def test_arctangent_infinite_interval(self) -> None:
        result = solve_integral("1/(1+x^2)", "x", "-oo", "oo")
        self.assert_equivalent(result.value, sp.pi)
        self.assertEqual(result.verification.status, "verified")
        self.assertIn("∫_(-∞)^∞", result.formula_text)

    def test_divergent_integral(self) -> None:
        result = solve_integral("1/x", "x", "0", "1")
        self.assertTrue(result.divergent)
        self.assertIsNone(result.numeric_text)
        self.assertIn("发散", result.divergence_reason or "")

    def test_undefined_symmetric_improper_integral(self) -> None:
        result = solve_integral("1/x", "x", "-1", "1")
        self.assertTrue(result.undefined)
        self.assertFalse(result.divergent)

    def test_undefined_trigonometric_improper_integral(self) -> None:
        result = solve_integral("tan(x)", "x", "0", "pi")
        self.assertTrue(result.undefined)

    def test_reversed_bounds(self) -> None:
        result = solve_integral("x^2", "x", "1", "0")
        self.assert_equivalent(result.value, -sp.Rational(1, 3))

    def test_equal_bounds(self) -> None:
        result = solve_integral("sin(x)", "x", "2", "2")
        self.assertEqual(result.value, 0)

    def test_parameter_bounds(self) -> None:
        result = solve_integral("a*x", "x", "0", "b")
        a, b = sp.symbols("a b")
        self.assert_equivalent(result.value, a * b**2 / 2)
        self.assertIsNone(result.numeric_text)

    def test_constant_integrand(self) -> None:
        result = solve_integral("3", "x", "0", "2")
        self.assertEqual(result.value, 6)
        self.assertTrue(any("常数" in warning for warning in result.warnings))

    def test_numeric_only_when_no_closed_form(self) -> None:
        result = solve_integral("x!", "x", "0", "1")
        self.assertTrue(result.unevaluated)
        self.assertFalse(result.exact)
        self.assertIsNotNone(result.numeric_text)
        self.assertIn("≈", result.formula_text)


class ValidationTests(unittest.TestCase):
    def test_empty_expression(self) -> None:
        with self.assertRaises(InputError):
            solve_integral("   ")

    def test_bad_syntax(self) -> None:
        with self.assertRaises(InputError):
            solve_integral("x**")

    def test_dangerous_input_is_rejected(self) -> None:
        with self.assertRaises(InputError):
            solve_integral("__import__('os')")

    def test_reserved_variable(self) -> None:
        with self.assertRaises(InputError):
            solve_integral("x^2", "sin")

    def test_only_one_bound(self) -> None:
        with self.assertRaises(InputError):
            solve_integral("x^2", "x", "0", None)

    def test_variable_in_bound(self) -> None:
        with self.assertRaises(InputError):
            solve_integral("x^2", "x", "0", "x")

    def test_integral_notation_paste(self) -> None:
        result = solve_integral("∫ x^2 dx")
        self.assertEqual(result.kind, "indefinite")
        self.assertEqual(result.verification.status, "verified")


class FormattingTests(unittest.TestCase):
    def test_superscripts_and_constants(self) -> None:
        self.assertEqual(format_expr(X**2), "x²")
        self.assertEqual(format_expr(sp.pi), "π")
        self.assertEqual(format_expr(sp.oo), "∞")

    def test_no_latex_braces_in_bounds(self) -> None:
        result = solve_integral("x^2", "x", "0", "pi")
        self.assertIn("∫₀^π", result.formula_text)
        self.assertNotIn("_{", result.formula_text)

    def test_json_serializable(self) -> None:
        result = solve_integral("exp(-x^2)", "x", "0", "1")
        payload = result.to_dict()
        encoded = json.dumps(payload, ensure_ascii=False)
        self.assertIn('"ok": true', encoded)
        self.assertEqual(payload["kind"], "definite")

    def test_report_contains_steps_and_verification(self) -> None:
        result = solve_integral("x^2")
        report = result.to_text()
        self.assertIn("【推导步骤】", report)
        self.assertIn("【校验】", report)
        self.assertIn("求导校验", report)


if __name__ == "__main__":
    unittest.main()
