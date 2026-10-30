from __future__ import annotations

import sys
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from integral_solver import solve_integral

try:
    import tkinter as tk

    from integral_solver.gui import IntegralSolverApp
except Exception:  # noqa: BLE001 - 无图形环境时跳过
    tk = None  # type: ignore[assignment]
    IntegralSolverApp = None  # type: ignore[assignment,misc]


@unittest.skipIf(tk is None or IntegralSolverApp is None, "Tkinter 不可用")
class GuiSmokeTests(unittest.TestCase):
    app: "IntegralSolverApp"

    def setUp(self) -> None:
        self.app = IntegralSolverApp()
        self.app.withdraw()
        self.app.update_idletasks()
        self.app.update()

    def tearDown(self) -> None:
        try:
            self.app.destroy()
        except Exception:  # noqa: BLE001
            pass

    def test_initial_layout(self) -> None:
        self.assertGreater(self.app.winfo_width(), 900)
        self.assertEqual(self.app.result_panel.winfo_manager(), "")
        self.assertEqual(self.app.bounds_row.winfo_manager(), "")
        self.assertEqual(self.app.status_label.cget("text"), "就绪")

    def test_mode_switch(self) -> None:
        self.app._set_mode("definite")
        self.app.update_idletasks()
        self.assertEqual(self.app.bounds_row.winfo_manager(), "grid")
        self.assertEqual(self.app.mode_var.get(), "definite")
        self.app._set_mode("indefinite")
        self.app.update_idletasks()
        self.assertEqual(self.app.bounds_row.winfo_manager(), "")

    def test_render_result(self) -> None:
        result = solve_integral("x^2", "x", "0", "1")
        self.app._render_result(result)
        self.app.update_idletasks()
        self.assertIn("∫₀¹ x² dx = 1/3", self.app.formula_label.cget("text"))
        self.assertEqual(self.app.result_panel.winfo_manager(), "grid")
        self.assertEqual(self.app.notebook.index("current"), 0)
        steps = self.app.steps_text.get("1.0", "end")
        self.assertIn("牛顿–莱布尼茨公式", steps)

    def test_bound_symbol_buttons_insert_into_focused_limit(self) -> None:
        self.app._set_mode("definite")
        self.app.update_idletasks()
        self.assertEqual(
            [button.cget("text") for button in self.app.bound_symbol_buttons],
            ["π", "∞", "-∞"],
        )

        upper = self.app.upper_entry
        upper.delete(0, "end")
        self.app._remember_bound_entry(upper)
        self.app.bound_symbol_buttons[0].invoke()
        self.assertEqual(upper.get(), "π")
        self.assertIn("π", self.app.status_label.cget("text"))

        lower = self.app.lower_entry
        lower.delete(0, "end")
        lower.insert(0, "0")
        lower.icursor("end")
        self.app._remember_bound_entry(lower)
        self.app.bound_symbol_buttons[2].invoke()
        self.assertEqual(lower.get(), "0-∞")

    def test_bound_symbol_buttons_are_hidden_for_indefinite_integral(self) -> None:
        self.app._set_mode("indefinite")
        self.app.update_idletasks()
        self.assertEqual(self.app.bounds_row.winfo_manager(), "")
        self.assertFalse(self.app.bound_symbol_buttons[0].winfo_ismapped())

    def test_validation_error_banner(self) -> None:
        self.app.expr_entry.delete(0, "end")
        self.app._start_calculation()
        self.app.update_idletasks()
        self.assertEqual(self.app.error_label.winfo_manager(), "pack")
        self.assertIn("请先输入", self.app.error_label.cget("text"))

    def test_async_calculation(self) -> None:
        self.app.expr_entry.insert(0, "sin(x)")
        self.app._set_mode("definite")
        self.app._start_calculation()
        deadline = time.monotonic() + 20
        while self.app._busy and time.monotonic() < deadline:
            self.app.update()
            time.sleep(0.03)
        self.app.update()
        self.assertFalse(self.app._busy, "计算超时")
        formula = self.app.formula_label.cget("text")
        self.assertIn("sin(x)", formula)
        self.assertIn("1 - cos(1)", formula)


if __name__ == "__main__":
    unittest.main()
