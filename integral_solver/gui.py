"""Tkinter 图形界面。"""

from __future__ import annotations

import queue
import sys
import threading
import tkinter as tk
import traceback
from pathlib import Path
from tkinter import font as tkfont
from tkinter import ttk

from . import __version__
from .core import (
    IntegralError,
    IntegralResult,
    format_expr,
    solve_integral,
)

APP_TITLE = "积分求解器"
APP_SUBTITLE = "定积分 · 不定积分 · 符号推导与数值校验"

# 配色
BG = "#F2F6FA"
CARD = "#FFFFFF"
NAVY = "#12324C"
NAVY_LIGHT = "#1B486A"
ACCENT = "#0E7490"
ACCENT_DARK = "#0A586D"
ACCENT_SOFT = "#E7F4F7"
TEXT = "#172B3B"
MUTED = "#62788B"
MUTED_LIGHT = "#8BA0B2"
BORDER = "#DCE6EF"
SOFT = "#F6F9FC"
SUCCESS = "#067647"
SUCCESS_BG = "#ECFDF3"
WARNING = "#B54708"
WARNING_BG = "#FFFAEB"
ERROR = "#B42318"
ERROR_BG = "#FEF3F2"

EXAMPLES = (
    ("x²·sin(x)", "x^2*sin(x)"),
    ("e^(-x²)", "exp(-x^2)"),
    ("1/(1+x²)", "1/(1+x^2)"),
    ("sin(x)/x", "sin(x)/x"),
)


class IntegralSolverApp(tk.Tk):
    """积分求解器主窗口。"""

    def __init__(self) -> None:
        super().__init__()
        self._queue: queue.Queue[tuple[int, str, object]] = queue.Queue()
        self._job_token = 0
        self._busy = False
        self._last_result: IntegralResult | None = None

        self._font_ui = self._pick_font(
            "Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI", "Arial"
        )
        # 注意：Tk 读取 Cambria Math 的行高异常大，会把按钮和标签撑高，
        # 因此数学文本统一使用 Cambria（并保留常见衬线字体作为回退）。
        self._font_math = self._pick_font(
            "Cambria", "Times New Roman", "Georgia", "Segoe UI"
        )
        self._font_mono = self._pick_font(
            "Cascadia Mono", "Consolas", "Courier New"
        )

        self._setup_window()
        self._setup_style()
        self._build_ui()
        self._bind_shortcuts()
        self.after_idle(self._focus_expression)

    # ------------------------------------------------------------------
    # 基础设置
    # ------------------------------------------------------------------

    def _pick_font(self, *candidates: str) -> str:
        available = set(tkfont.families(self))
        for candidate in candidates:
            if candidate in available:
                return candidate
        return "TkDefaultFont"

    def _setup_window(self) -> None:
        self.title(f"{APP_TITLE} · 定积分与不定积分")
        width = min(1180, max(1040, self.winfo_screenwidth() - 160))
        height = min(790, max(700, self.winfo_screenheight() - 120))
        x = max(20, (self.winfo_screenwidth() - width) // 2)
        y = max(20, (self.winfo_screenheight() - height) // 2 - 20)
        self.geometry(f"{width}x{height}+{x}+{y}")
        self.minsize(1040, 700)
        self.configure(bg=BG)
        try:
            self.tk.call("tk", "scaling", max(1.0, self.winfo_fpixels("1i") / 72.0))
        except tk.TclError:
            pass

        docs_dir = Path(__file__).resolve().parent.parent / "docs"
        png_icon = docs_dir / "app_icon.png"
        ico_icon = docs_dir / "app_icon.ico"
        self._app_icon = None
        if png_icon.exists():
            try:
                self._app_icon = tk.PhotoImage(file=str(png_icon))
                self.iconphoto(True, self._app_icon)
            except tk.TclError:
                self._app_icon = None
        # Windows 下优先使用多尺寸 ICO，标题栏和任务栏会更清晰。
        if sys.platform == "win32" and ico_icon.exists():
            try:
                self.iconbitmap(str(ico_icon))
                self.iconbitmap(default=str(ico_icon))
            except tk.TclError:
                pass

    def _setup_style(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure(
            "Primary.TButton",
            background=ACCENT,
            foreground="#FFFFFF",
            borderwidth=0,
            focusthickness=0,
            focuscolor=ACCENT,
            padding=(18, 12),
            font=(self._font_ui, 11, "bold"),
        )
        style.map(
            "Primary.TButton",
            background=[
                ("disabled", "#A9C8D3"),
                ("pressed", ACCENT_DARK),
                ("active", ACCENT_DARK),
            ],
            foreground=[("disabled", "#F4FAFC")],
        )

        style.configure(
            "Ghost.TButton",
            background=CARD,
            foreground=ACCENT,
            borderwidth=0,
            focusthickness=0,
            focuscolor=CARD,
            padding=(10, 6),
            font=(self._font_ui, 9),
        )
        style.map(
            "Ghost.TButton",
            background=[("active", ACCENT_SOFT), ("disabled", CARD)],
            foreground=[("disabled", "#B5C4CF")],
        )

        style.configure(
            "TNotebook",
            background=CARD,
            borderwidth=0,
            tabmargins=(0, 8, 0, 0),
        )
        style.configure(
            "TNotebook.Tab",
            background=SOFT,
            foreground=MUTED,
            padding=(18, 8),
            borderwidth=0,
            font=(self._font_ui, 10),
        )
        style.map(
            "TNotebook.Tab",
            background=[("selected", CARD)],
            foreground=[("selected", ACCENT)],
            expand=[("selected", (0, 0, 0, 0))],
        )

        style.configure(
            "Vertical.TScrollbar",
            background="#C5D4DF",
            troughcolor=SOFT,
            bordercolor=SOFT,
            arrowcolor=MUTED,
            borderwidth=0,
        )
        style.configure(
            "Horizontal.TProgressbar",
            background=ACCENT,
            troughcolor="#DEEAF0",
            borderwidth=0,
            thickness=4,
        )

    # ------------------------------------------------------------------
    # 界面
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        self._build_header()
        self._build_status_bar()

        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True, padx=22, pady=(16, 12))
        body.grid_columnconfigure(0, weight=0, minsize=420)
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(0, weight=1)

        self._build_input_card(body)

        right = tk.Frame(
            body,
            bg=CARD,
            highlightbackground=BORDER,
            highlightthickness=1,
        )
        right.grid(row=0, column=1, sticky="nsew", padx=(18, 0))
        right.grid_columnconfigure(0, weight=1)
        right.grid_rowconfigure(1, weight=1)
        self._build_result_card(right)

    def _build_header(self) -> None:
        header = tk.Frame(self, bg=NAVY, height=92)
        header.pack(fill="x")
        header.pack_propagate(False)

        accent = tk.Frame(header, bg=ACCENT, width=6)
        accent.pack(side="left", fill="y")

        text_box = tk.Frame(header, bg=NAVY)
        text_box.pack(side="left", fill="y", padx=(22, 0), pady=10)
        tk.Label(
            text_box,
            text=APP_TITLE,
            bg=NAVY,
            fg="#FFFFFF",
            font=(self._font_ui, 21, "bold"),
            anchor="w",
        ).pack(anchor="w")
        tk.Label(
            text_box,
            text=APP_SUBTITLE,
            bg=NAVY,
            fg="#A9C6D8",
            font=(self._font_ui, 10),
            anchor="w",
        ).pack(anchor="w", pady=(3, 0))

        badge = tk.Label(
            header,
            text="  SymPy 符号引擎  ",
            bg=NAVY_LIGHT,
            fg="#D8ECF3",
            font=(self._font_ui, 9),
            padx=8,
            pady=6,
        )
        badge.pack(side="right", padx=24)
        tk.Label(
            header,
            text="∫",
            bg=NAVY,
            fg="#2C607D",
            font=(self._font_math, 34),
        ).pack(side="right", padx=(0, 10))

    def _build_input_card(self, parent: tk.Widget) -> None:
        card = tk.Frame(
            parent,
            bg=CARD,
            width=420,
            highlightbackground=BORDER,
            highlightthickness=1,
        )
        card.grid(row=0, column=0, sticky="nsew")
        card.grid_rowconfigure(0, weight=1)
        card.grid_columnconfigure(0, weight=1)
        # 左栏固定宽度，避免窗口变窄时表单把结果区挤得太小。
        card.grid_propagate(False)

        inner = tk.Frame(card, bg=CARD)
        inner.grid(row=0, column=0, sticky="nsew", padx=22, pady=16)
        inner.pack_propagate(True)

        action = tk.Frame(inner, bg=CARD)
        action.pack(side="bottom", fill="x", pady=(12, 0))

        self._build_action_area(action)

        content = tk.Frame(inner, bg=CARD)
        content.pack(side="top", fill="both", expand=True)

        heading = tk.Frame(content, bg=CARD)
        heading.pack(fill="x", pady=(0, 12))
        tk.Label(
            heading,
            text="输入题目",
            bg=CARD,
            fg=TEXT,
            font=(self._font_ui, 14, "bold"),
        ).pack(side="left")
        tk.Label(
            heading,
            text="01",
            bg=ACCENT_SOFT,
            fg=ACCENT,
            font=(self._font_ui, 8, "bold"),
            padx=7,
            pady=2,
        ).pack(side="left", padx=(8, 0))
        self.clear_button = tk.Button(
            heading,
            text="清空",
            command=self._clear_all,
            bg=CARD,
            fg=MUTED,
            activebackground=CARD,
            activeforeground=ACCENT,
            relief="flat",
            bd=0,
            cursor="hand2",
            font=(self._font_ui, 9),
            padx=4,
            pady=2,
        )
        self.clear_button.pack(side="right")

        # 模式选择
        mode_bar = tk.Frame(content, bg="#EDF3F7", padx=3, pady=3)
        mode_bar.pack(fill="x", pady=(0, 18))
        self.mode_var = tk.StringVar(value="indefinite")
        self.mode_buttons: dict[str, tk.Button] = {}
        for value, label in (("indefinite", "不定积分"), ("definite", "定积分")):
            button = tk.Button(
                mode_bar,
                text=label,
                command=lambda v=value: self._set_mode(v),
                relief="flat",
                bd=0,
                highlightthickness=0,
                cursor="hand2",
                font=(self._font_ui, 10, "bold"),
                padx=14,
                pady=6,
            )
            button.pack(side="left", expand=True, fill="x")
            self.mode_buttons[value] = button
        self._refresh_mode_buttons()

        # 被积函数
        row = tk.Frame(content, bg=CARD)
        row.pack(fill="x")
        tk.Label(
            row,
            text="被积函数",
            bg=CARD,
            fg=TEXT,
            font=(self._font_ui, 10, "bold"),
        ).pack(side="left")
        tk.Label(
            row,
            text="f(x)",
            bg=CARD,
            fg=MUTED_LIGHT,
            font=(self._font_math, 10, "italic"),
        ).pack(side="right")

        entry_wrap, self.expr_entry = self._make_entry(content, font_size=17, ipady=8)
        entry_wrap.pack(fill="x", pady=(7, 0))
        self.expr_entry.bind("<Return>", self._start_calculation)
        self.expr_entry.bind("<KP_Enter>", self._start_calculation)

        tk.Label(
            content,
            text="支持 x^2、sin(x)、exp(-x^2)、ln(x)；π、e、∞ 可直接写。",
            bg=CARD,
            fg=MUTED_LIGHT,
            font=(self._font_ui, 8),
            anchor="w",
            justify="left",
            wraplength=360,
        ).pack(fill="x", pady=(6, 0))

        # 变量与积分限
        fields = tk.Frame(content, bg=CARD)
        fields.pack(fill="x", pady=(13, 0))
        fields.grid_columnconfigure(1, weight=1)

        tk.Label(
            fields,
            text="积分变量",
            bg=CARD,
            fg=MUTED,
            font=(self._font_ui, 9),
        ).grid(row=0, column=0, sticky="w", padx=(0, 10))
        var_wrap, self.var_entry = self._make_entry(fields, font_size=11, ipady=5)
        var_wrap.grid(row=0, column=1, sticky="w")
        self.var_entry.configure(width=10)
        self.var_entry.insert(0, "x")

        self.bounds_row = tk.Frame(fields, bg=CARD)
        self.bounds_row.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        self.bounds_row.grid_columnconfigure(1, weight=1)
        self.bounds_row.grid_columnconfigure(4, weight=1)

        tk.Label(
            self.bounds_row,
            text="积分下限",
            bg=CARD,
            fg=MUTED,
            font=(self._font_ui, 9),
        ).grid(row=0, column=0, padx=(0, 7))
        lower_wrap, self.lower_entry = self._make_entry(
            self.bounds_row, font_size=11, ipady=5
        )
        lower_wrap.grid(row=0, column=1, sticky="ew")
        tk.Label(
            self.bounds_row,
            text="到",
            bg=CARD,
            fg=MUTED_LIGHT,
            font=(self._font_ui, 9),
        ).grid(row=0, column=2, padx=7)
        tk.Label(
            self.bounds_row,
            text="上限",
            bg=CARD,
            fg=MUTED,
            font=(self._font_ui, 9),
        ).grid(row=0, column=3, sticky="w")
        upper_wrap, self.upper_entry = self._make_entry(
            self.bounds_row, font_size=11, ipady=5
        )
        upper_wrap.grid(row=0, column=4, sticky="ew", padx=(5, 0))
        self.lower_entry.insert(0, "0")
        self.upper_entry.insert(0, "1")
        self._last_bound_entry = self.upper_entry
        for entry in (self.lower_entry, self.upper_entry):
            entry.bind("<Return>", self._start_calculation)
            entry.bind("<KP_Enter>", self._start_calculation)
            entry.bind(
                "<FocusIn>",
                lambda _event, target=entry: self._remember_bound_entry(target),
                add="+",
            )

        # 上下限快捷符号按钮：插入到最近编辑过的那个输入框。
        quick_row = tk.Frame(self.bounds_row, bg=CARD)
        quick_row.grid(
            row=1,
            column=0,
            columnspan=5,
            sticky="ew",
            pady=(4, 0),
        )
        quick_row.grid_columnconfigure(0, weight=1)
        self.bounds_hint = tk.Label(
            quick_row,
            text="快捷插入到当前输入框",
            bg=CARD,
            fg=MUTED_LIGHT,
            font=(self._font_ui, 8),
            anchor="w",
        )
        self.bounds_hint.grid(row=0, column=0, sticky="w")
        self.bound_symbol_buttons: list[tk.Button] = []
        for index, symbol in enumerate(("π", "∞", "-∞"), start=1):
            button = tk.Button(
                quick_row,
                text=symbol,
                command=lambda value=symbol: self._insert_bound_symbol(value),
                bg=ACCENT_SOFT,
                fg=ACCENT_DARK,
                activebackground="#D4EEF4",
                activeforeground=ACCENT_DARK,
                relief="flat",
                bd=0,
                highlightthickness=0,
                cursor="hand2",
                font=(self._font_math, 10, "bold"),
                padx=8,
                pady=3,
            )
            button.grid(row=0, column=index, padx=(4, 0))
            self._bind_hover(button, ACCENT_SOFT, "#D4EEF4")
            self.bound_symbol_buttons.append(button)
        self.bounds_row.grid_remove()

        # 示例
        examples_header = tk.Frame(content, bg=CARD)
        examples_header.pack(fill="x", pady=(14, 5))
        tk.Label(
            examples_header,
            text="快速填入",
            bg=CARD,
            fg=MUTED,
            font=(self._font_ui, 8, "bold"),
        ).pack(side="left")
        tk.Label(
            examples_header,
            text="点击即可试用",
            bg=CARD,
            fg=MUTED_LIGHT,
            font=(self._font_ui, 8),
        ).pack(side="right")

        example_grid = tk.Frame(content, bg=CARD)
        example_grid.pack(fill="x")
        for index, (display, expression) in enumerate(EXAMPLES):
            chip = tk.Button(
                example_grid,
                text=display,
                command=lambda exp=expression: self._use_example(exp),
                bg=SOFT,
                fg="#31536A",
                activebackground=ACCENT_SOFT,
                activeforeground=ACCENT_DARK,
                relief="flat",
                bd=0,
                highlightthickness=0,
                cursor="hand2",
                font=(self._font_math, 9),
                padx=6,
                pady=5,
            )
            chip.grid(
                row=index // 2,
                column=index % 2,
                sticky="ew",
                padx=(0 if index % 2 == 0 else 3, 3 if index % 2 == 0 else 0),
                pady=(0, 5),
            )
            self._bind_hover(chip, SOFT, ACCENT_SOFT)
        example_grid.grid_columnconfigure(0, weight=1)
        example_grid.grid_columnconfigure(1, weight=1)

    def _build_action_area(self, parent: tk.Widget) -> None:
        self.error_label = tk.Label(
            parent,
            text="",
            bg=ERROR_BG,
            fg=ERROR,
            font=(self._font_ui, 9),
            justify="left",
            anchor="w",
            wraplength=356,
            padx=10,
            pady=8,
        )

        self.calc_button = ttk.Button(
            parent,
            text="开始计算  →",
            style="Primary.TButton",
            command=self._start_calculation,
        )
        self.calc_button.pack(fill="x")

        shortcut = tk.Frame(parent, bg=CARD)
        shortcut.pack(fill="x", pady=(7, 0))
        tk.Label(
            shortcut,
            text="Enter 计算",
            bg=CARD,
            fg=MUTED_LIGHT,
            font=(self._font_ui, 8),
        ).pack(side="left")
        tk.Label(
            shortcut,
            text="Ctrl+Enter 任意位置计算",
            bg=CARD,
            fg=MUTED_LIGHT,
            font=(self._font_ui, 8),
        ).pack(side="right")

    def _build_result_card(self, parent: tk.Widget) -> None:
        header = tk.Frame(parent, bg=CARD)
        header.grid(row=0, column=0, sticky="ew", padx=22, pady=(16, 0))
        header.grid_columnconfigure(0, weight=1)

        title_box = tk.Frame(header, bg=CARD)
        title_box.grid(row=0, column=0, sticky="w")
        tk.Label(
            title_box,
            text="计算结果",
            bg=CARD,
            fg=TEXT,
            font=(self._font_ui, 14, "bold"),
        ).pack(side="left")
        self.result_badge = tk.Label(
            title_box,
            text="等待输入",
            bg=ACCENT_SOFT,
            fg=ACCENT,
            font=(self._font_ui, 8, "bold"),
            padx=8,
            pady=3,
        )
        self.result_badge.pack(side="left", padx=(9, 0))

        self.copy_button = ttk.Button(
            header,
            text="复制报告",
            style="Ghost.TButton",
            command=self._copy_report,
            state="disabled",
        )
        self.copy_button.grid(row=0, column=1, sticky="e")

        self.result_header = header

        content = tk.Frame(parent, bg=CARD)
        content.grid(row=1, column=0, sticky="nsew", padx=22, pady=(6, 20))
        content.grid_rowconfigure(0, weight=1)
        content.grid_columnconfigure(0, weight=1)
        self.result_content = content

        self._build_placeholder(content)
        self._build_result_panel(content)

    def _build_placeholder(self, parent: tk.Widget) -> None:
        placeholder = tk.Frame(parent, bg=CARD)
        placeholder.grid(row=0, column=0, sticky="nsew")
        placeholder.grid_rowconfigure(0, weight=1)
        placeholder.grid_columnconfigure(0, weight=1)
        self.placeholder = placeholder

        box = tk.Frame(placeholder, bg=CARD)
        box.grid(row=0, column=0)

        symbol = tk.Label(
            box,
            text="∫",
            bg=CARD,
            fg="#C9DEE8",
            font=(self._font_math, 72),
        )
        symbol.pack()
        tk.Label(
            box,
            text="等待你的第一道积分",
            bg=CARD,
            fg=TEXT,
            font=(self._font_ui, 15, "bold"),
        ).pack(pady=(2, 7))
        tk.Label(
            box,
            text="输入被积函数，选择积分类型，然后点击“开始计算”。\n"
            "结果会给出原函数、推导步骤、求导验算或数值积分校验。",
            bg=CARD,
            fg=MUTED,
            font=(self._font_ui, 10),
            justify="center",
        ).pack()

        chips = tk.Frame(box, bg=CARD)
        chips.pack(pady=(22, 0))
        for text in ("不定积分", "定积分", "发散判定", "数值校验"):
            tk.Label(
                chips,
                text=text,
                bg=SOFT,
                fg=MUTED,
                font=(self._font_ui, 8),
                padx=9,
                pady=4,
            ).pack(side="left", padx=3)

    def _build_result_panel(self, parent: tk.Widget) -> None:
        panel = tk.Frame(parent, bg=CARD)
        panel.grid(row=0, column=0, sticky="nsew")
        panel.grid_columnconfigure(0, weight=1)
        panel.grid_rowconfigure(2, weight=1)
        panel.grid_remove()
        self.result_panel = panel

        summary = tk.Frame(panel, bg=CARD)
        summary.grid(row=0, column=0, sticky="ew")
        summary.grid_columnconfigure(0, weight=1)

        self.formula_label = tk.Label(
            summary,
            text="",
            bg=CARD,
            fg=NAVY,
            font=(self._font_math, 19, "bold"),
            anchor="w",
            justify="left",
            wraplength=650,
        )
        self.formula_label.grid(row=0, column=0, sticky="ew", pady=(5, 7))

        meta = tk.Frame(summary, bg=CARD)
        meta.grid(row=1, column=0, sticky="ew")
        self.exact_badge = tk.Label(
            meta,
            text="精确解",
            bg=SUCCESS_BG,
            fg=SUCCESS,
            font=(self._font_ui, 8, "bold"),
            padx=8,
            pady=3,
        )
        self.exact_badge.pack(side="left")
        self.numeric_label = tk.Label(
            meta,
            text="",
            bg=CARD,
            fg=MUTED,
            font=(self._font_math, 10),
            anchor="w",
        )
        self.numeric_label.pack(side="left", padx=(9, 0))
        self.elapsed_label = tk.Label(
            meta,
            text="",
            bg=CARD,
            fg=MUTED_LIGHT,
            font=(self._font_ui, 8),
        )
        self.elapsed_label.pack(side="right")

        self.summary_note = tk.Label(
            summary,
            text="",
            bg=WARNING_BG,
            fg=WARNING,
            font=(self._font_ui, 8),
            anchor="w",
            justify="left",
            wraplength=650,
            padx=9,
            pady=6,
        )
        self.summary_note.grid(row=2, column=0, sticky="ew", pady=(9, 0))
        self.summary_note.grid_remove()

        divider = tk.Frame(panel, bg=BORDER, height=1)
        divider.grid(row=1, column=0, sticky="ew", pady=(14, 0))

        notebook = ttk.Notebook(panel)
        notebook.grid(row=2, column=0, sticky="nsew", pady=(0, 0))
        self.notebook = notebook

        steps_tab = tk.Frame(notebook, bg=CARD)
        notebook.add(steps_tab, text="推导步骤")
        self.steps_text = self._make_readonly_text(steps_tab)

        verify_tab = tk.Frame(notebook, bg=CARD)
        notebook.add(verify_tab, text="校验与提示")
        self.verify_banner = tk.Label(
            verify_tab,
            text="",
            bg=SOFT,
            fg=TEXT,
            font=(self._font_ui, 10, "bold"),
            anchor="w",
            justify="left",
            wraplength=620,
            padx=12,
            pady=9,
        )
        self.verify_banner.pack(fill="x", padx=10, pady=(10, 0))
        self.verify_text = self._make_readonly_text(verify_tab, height=6)

    def _make_readonly_text(
        self,
        parent: tk.Widget,
        *,
        height: int = 10,
    ) -> tk.Text:
        wrapper = tk.Frame(parent, bg=CARD)
        wrapper.pack(fill="both", expand=True, padx=(0, 0), pady=(6, 0))
        wrapper.grid_rowconfigure(0, weight=1)
        wrapper.grid_columnconfigure(0, weight=1)

        text = tk.Text(
            wrapper,
            wrap="word",
            bg=CARD,
            fg=TEXT,
            relief="flat",
            bd=0,
            highlightthickness=0,
            font=(self._font_ui, 10),
            padx=10,
            pady=8,
            spacing1=2,
            spacing3=5,
            height=height,
            cursor="arrow",
            selectbackground="#CBE7EF",
            selectforeground=TEXT,
        )
        scrollbar = ttk.Scrollbar(
            wrapper,
            orient="vertical",
            command=text.yview,
            style="Vertical.TScrollbar",
        )
        text.configure(yscrollcommand=scrollbar.set)
        text.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

        text.tag_configure(
            "step_title",
            font=(self._font_ui, 10, "bold"),
            foreground=ACCENT_DARK,
            spacing1=7,
            spacing3=3,
        )
        text.tag_configure(
            "step_body",
            font=(self._font_ui, 10),
            foreground=TEXT,
            lmargin1=18,
            lmargin2=18,
            spacing3=2,
        )
        text.tag_configure(
            "math",
            font=(self._font_math, 11),
            foreground=NAVY,
            lmargin1=18,
            lmargin2=18,
            spacing1=2,
            spacing3=3,
        )
        text.tag_configure(
            "section",
            font=(self._font_ui, 10, "bold"),
            foreground=TEXT,
            spacing1=9,
            spacing3=4,
        )
        text.tag_configure(
            "muted",
            font=(self._font_ui, 9),
            foreground=MUTED,
            lmargin1=18,
            lmargin2=18,
        )
        text.tag_configure(
            "good",
            font=(self._font_ui, 9),
            foreground=SUCCESS,
        )
        text.tag_configure(
            "warn",
            font=(self._font_ui, 9),
            foreground=WARNING,
            lmargin1=18,
            lmargin2=18,
        )
        text.configure(state="disabled")
        return text

    def _build_status_bar(self) -> None:
        bar = tk.Frame(self, bg="#E7EEF4", height=28)
        bar.pack(fill="x", side="bottom")
        bar.pack_propagate(False)

        self.status_dot = tk.Label(
            bar,
            text="●",
            bg="#E7EEF4",
            fg=SUCCESS,
            font=(self._font_ui, 8),
        )
        self.status_dot.pack(side="left", padx=(22, 4))
        self.status_label = tk.Label(
            bar,
            text="就绪",
            bg="#E7EEF4",
            fg=MUTED,
            font=(self._font_ui, 8),
            anchor="w",
        )
        self.status_label.pack(side="left")

        self.progress = ttk.Progressbar(
            bar,
            mode="indeterminate",
            length=110,
            style="Horizontal.TProgressbar",
        )

        tk.Label(
            bar,
            text=f"v{__version__}  ·  SymPy 符号计算",
            bg="#E7EEF4",
            fg=MUTED_LIGHT,
            font=(self._font_ui, 8),
        ).pack(side="right", padx=22)

    def _make_entry(
        self,
        parent: tk.Widget,
        *,
        font_size: int,
        ipady: int,
    ) -> tuple[tk.Frame, tk.Entry]:
        wrapper = tk.Frame(parent, bg=BORDER)
        entry = tk.Entry(
            wrapper,
            relief="flat",
            bd=0,
            highlightthickness=0,
            bg=CARD,
            fg=TEXT,
            insertbackground=ACCENT,
            font=(self._font_math, font_size),
            selectbackground="#CBE7EF",
            selectforeground=TEXT,
        )
        entry.pack(fill="x", padx=10, pady=1, ipady=ipady)
        entry.bind("<FocusIn>", lambda _event: wrapper.configure(bg=ACCENT))
        entry.bind("<FocusOut>", lambda _event: wrapper.configure(bg=BORDER))
        return wrapper, entry

    @staticmethod
    def _bind_hover(widget: tk.Widget, normal: str, hover: str) -> None:
        widget.bind("<Enter>", lambda _event: widget.configure(bg=hover))
        widget.bind("<Leave>", lambda _event: widget.configure(bg=normal))

    # ------------------------------------------------------------------
    # 交互
    # ------------------------------------------------------------------

    def _bind_shortcuts(self) -> None:
        self.bind("<Control-Return>", self._start_calculation)
        self.bind("<Control-KP_Enter>", self._start_calculation)
        self.bind("<F5>", self._start_calculation)
        self.bind("<Escape>", lambda _event: self._hide_error())
        self.bind("<Configure>", self._on_window_configure, add="+")

    def _on_window_configure(self, event: tk.Event) -> None:
        if event.widget is self and self._last_result is not None:
            self.after_idle(self._update_formula_wrap)

    def _focus_expression(self) -> None:
        self.expr_entry.focus_set()

    def _refresh_mode_buttons(self) -> None:
        selected = self.mode_var.get()
        for value, button in self.mode_buttons.items():
            if value == selected:
                button.configure(
                    bg=ACCENT,
                    fg="#FFFFFF",
                    activebackground=ACCENT_DARK,
                    activeforeground="#FFFFFF",
                )
            else:
                button.configure(
                    bg="#EDF3F7",
                    fg=MUTED,
                    activebackground="#E1EAF0",
                    activeforeground=TEXT,
                )

    def _set_mode(self, mode: str) -> None:
        if mode not in ("indefinite", "definite"):
            return
        self.mode_var.set(mode)
        self._refresh_mode_buttons()
        if mode == "definite":
            self.bounds_row.grid()
            if not self.lower_entry.get().strip():
                self.lower_entry.insert(0, "0")
            if not self.upper_entry.get().strip():
                self.upper_entry.insert(0, "1")
        else:
            self.bounds_row.grid_remove()
        self._hide_error()

    def _remember_bound_entry(self, entry: tk.Entry) -> None:
        self._last_bound_entry = entry

    def _insert_bound_symbol(self, symbol: str) -> None:
        """把 π、∞ 等符号插入到最近编辑的上限或下限输入框。"""

        if self.mode_var.get() != "definite":
            return
        entry = getattr(self, "_last_bound_entry", None)
        if not isinstance(entry, tk.Entry) or not entry.winfo_exists():
            entry = self.upper_entry
        try:
            entry.focus_set()
            if entry.selection_present():
                entry.delete("sel.first", "sel.last")
            position = entry.index("insert")
            entry.insert(position, symbol)
            entry.icursor(position + len(symbol))
        except tk.TclError:
            return
        self._hide_error()
        target = "下限" if entry is self.lower_entry else "上限"
        self._set_status(f"已插入 {symbol} 到{target}。", "ready")

    def _use_example(self, expression: str) -> None:
        self.expr_entry.delete(0, "end")
        self.expr_entry.insert(0, expression)
        self.expr_entry.focus_set()
        self._hide_error()
        self._set_status("示例已填入，按 Enter 或点击“开始计算”。", "ready")

    def _clear_all(self) -> None:
        if self._busy:
            return
        self.expr_entry.delete(0, "end")
        self.lower_entry.delete(0, "end")
        self.upper_entry.delete(0, "end")
        self.lower_entry.insert(0, "0")
        self.upper_entry.insert(0, "1")
        self._last_bound_entry = self.upper_entry
        self._hide_error()
        self._focus_expression()
        self._set_status("已清空，请输入被积函数。", "ready")

    def _show_error(self, message: str) -> None:
        self.error_label.configure(text=message)
        self.error_label.pack(fill="x", pady=(0, 8), before=self.calc_button)
        self._set_status("计算未完成，请检查输入。", "error")

    def _hide_error(self) -> None:
        self.error_label.pack_forget()

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        if busy:
            self.calc_button.configure(state="disabled", text="正在计算…")
            self.clear_button.configure(state="disabled")
            for button in self.mode_buttons.values():
                button.configure(state="disabled", cursor="arrow")
            for button in self.bound_symbol_buttons:
                button.configure(state="disabled", cursor="arrow")
            self.progress.pack(side="right", padx=(0, 14))
            self.progress.start(12)
            self._set_status("正在求解，请稍候…", "busy")
        else:
            self.calc_button.configure(state="normal", text="开始计算  →")
            self.clear_button.configure(state="normal")
            for button in self.mode_buttons.values():
                button.configure(state="normal", cursor="hand2")
            for button in self.bound_symbol_buttons:
                button.configure(state="normal", cursor="hand2")
            self.progress.stop()
            self.progress.pack_forget()

    def _set_status(self, text: str, kind: str = "ready") -> None:
        colors = {
            "ready": (SUCCESS, "●"),
            "busy": (ACCENT, "●"),
            "error": (ERROR, "●"),
            "done": (SUCCESS, "●"),
            "warning": (WARNING, "●"),
        }
        color, dot = colors.get(kind, colors["ready"])
        self.status_label.configure(text=text)
        self.status_dot.configure(fg=color, text=dot)

    # ------------------------------------------------------------------
    # 计算
    # ------------------------------------------------------------------

    def _start_calculation(self, _event: tk.Event | None = None) -> None:
        if self._busy:
            return

        expression = self.expr_entry.get().strip()
        variable = self.var_entry.get().strip() or "x"
        if not expression:
            self._show_error("请先输入被积函数，例如 x^2 或 sin(x)。")
            self._focus_expression()
            return

        definite = self.mode_var.get() == "definite"
        lower = self.lower_entry.get().strip() if definite else None
        upper = self.upper_entry.get().strip() if definite else None
        if definite and (not lower or not upper):
            self._show_error("定积分需要同时填写下限和上限。")
            return

        self._hide_error()
        self._job_token += 1
        token = self._job_token
        self._set_busy(True)

        def worker() -> None:
            try:
                result = solve_integral(expression, variable, lower, upper)
            except IntegralError as exc:
                self._queue.put((token, "error", str(exc)))
            except Exception as exc:  # noqa: BLE001
                try:
                    if sys.stderr is not None:
                        traceback.print_exc()
                except Exception:  # noqa: BLE001
                    pass
                self._queue.put(
                    (token, "error", f"计算过程中出现意外错误：{exc}")
                )
            else:
                self._queue.put((token, "ok", result))

        threading.Thread(target=worker, daemon=True).start()
        self.after(80, lambda: self._poll_queue(token))

    def _poll_queue(self, token: int) -> None:
        if token != self._job_token:
            return
        try:
            result_token, kind, payload = self._queue.get_nowait()
        except queue.Empty:
            self.after(80, lambda: self._poll_queue(token))
            return

        if result_token != self._job_token:
            return

        self._set_busy(False)
        if kind == "error":
            message = str(payload)
            self._show_error(message)
            self._set_status("计算失败。", "error")
            return

        assert isinstance(payload, IntegralResult)
        self._last_result = payload
        self._render_result(payload)
        if payload.divergent or payload.undefined:
            self._set_status("计算完成：该积分发散或未定义。", "warning")
        elif not payload.exact and payload.numeric_text:
            self._set_status("计算完成：已给出数值近似结果。", "warning")
        elif not payload.exact:
            self._set_status("计算完成：未求出闭式结果。", "warning")
        else:
            self._set_status("计算完成。", "done")

    # ------------------------------------------------------------------
    # 渲染结果
    # ------------------------------------------------------------------

    def _render_result(self, result: IntegralResult) -> None:
        self.placeholder.grid_remove()
        self.result_panel.grid()

        if result.divergent:
            badge_text, badge_bg, badge_fg = "发散", ERROR_BG, ERROR
        elif result.undefined:
            badge_text, badge_bg, badge_fg = "未定义", ERROR_BG, ERROR
        elif result.unevaluated:
            badge_text, badge_bg, badge_fg = "无闭式解", WARNING_BG, WARNING
        elif result.kind == "indefinite":
            badge_text, badge_bg, badge_fg = "不定积分", ACCENT_SOFT, ACCENT
        else:
            badge_text, badge_bg, badge_fg = "定积分", ACCENT_SOFT, ACCENT
        self.result_badge.configure(text=badge_text, bg=badge_bg, fg=badge_fg)

        self.formula_label.configure(text=result.formula_text)
        self._update_formula_wrap()

        if result.divergent:
            exact_text = "发散"
        elif result.undefined:
            exact_text = "未定义"
        elif result.unevaluated:
            exact_text = "数值近似" if result.numeric_text else "无闭式解"
        elif result.exact:
            exact_text = "精确解"
        else:
            exact_text = "数值近似"
        exact_bg = SUCCESS_BG if exact_text == "精确解" else WARNING_BG
        exact_fg = SUCCESS if exact_text == "精确解" else (
            ERROR if exact_text in ("发散", "未定义") else WARNING
        )
        self.exact_badge.configure(text=exact_text, bg=exact_bg, fg=exact_fg)

        numeric = f"≈ {result.numeric_text}" if result.numeric_text else ""
        if result.kind == "indefinite":
            numeric = "+ C" if not result.unevaluated else ""
        self.numeric_label.configure(text=numeric)
        self.elapsed_label.configure(text=f"用时 {result.elapsed:.2f} 秒")

        note = ""
        if result.divergence_reason and (result.divergent or result.undefined):
            note = result.divergence_reason
        elif result.warnings:
            note = result.warnings[0]
        if note:
            self.summary_note.configure(text=note)
            self.summary_note.grid()
        else:
            self.summary_note.grid_remove()

        self._render_steps(result)
        self._render_verification(result)
        self.copy_button.configure(state="normal")
        self.notebook.select(0)

    def _render_steps(self, result: IntegralResult) -> None:
        text = self.steps_text
        text.configure(state="normal")
        text.delete("1.0", "end")

        text.insert("end", "计算过程\n", "section")
        text.insert(
            "end",
            "以下步骤由符号计算引擎生成，定积分使用牛顿–莱布尼茨公式。\n",
            "muted",
        )
        for index, step in enumerate(result.steps, start=1):
            text.insert("end", f"{index:02d}  {step.title}\n", "step_title")
            for line in step.lines:
                tag = "math" if any(
                    token in line for token in ("=", "∫", "≈")
                ) else "step_body"
                text.insert("end", f"{line}\n", tag)
            text.insert("end", "\n")

        if result.warnings:
            text.insert("end", "提示\n", "section")
            for warning in result.warnings:
                text.insert("end", f"• {warning}\n", "warn")

        text.configure(state="disabled")
        text.yview_moveto(0)

    def _render_verification(self, result: IntegralResult) -> None:
        verification = result.verification
        if verification is None:
            title = "未进行校验"
            detail = "本次计算没有生成校验信息。"
            bg, fg = SOFT, MUTED
        else:
            title = verification.title
            detail = verification.detail
            styles = {
                "verified": (SUCCESS_BG, SUCCESS),
                "sampled": (SUCCESS_BG, SUCCESS),
                "warning": (WARNING_BG, WARNING),
                "failed": (ERROR_BG, ERROR),
                "skipped": (SOFT, MUTED),
            }
            bg, fg = styles.get(verification.status, (SOFT, MUTED))

        self.verify_banner.configure(text=title, bg=bg, fg=fg)

        text = self.verify_text
        text.configure(state="normal")
        text.delete("1.0", "end")
        text.insert("end", detail or "无更多信息。", "step_body")
        text.insert("end", "\n\n输入解析\n", "section")
        text.insert(
            "end",
            f"被积函数：{format_expr(result.integrand)}\n",
            "math",
        )
        if result.lower is not None and result.upper is not None:
            text.insert(
                "end",
                f"积分区间：[{format_expr(result.lower)}, "
                f"{format_expr(result.upper)}]\n",
                "math",
            )
        else:
            text.insert("end", f"积分变量：{result.variable}（不定积分）\n", "math")
        if result.warnings:
            text.insert("end", "\n注意\n", "section")
            for warning in result.warnings:
                text.insert("end", f"• {warning}\n", "warn")
        text.configure(state="disabled")
        text.yview_moveto(0)

    def _update_formula_wrap(self) -> None:
        width = max(320, self.result_content.winfo_width() - 12)
        self.formula_label.configure(wraplength=width)
        self.summary_note.configure(wraplength=width)
        self.verify_banner.configure(wraplength=max(280, width - 36))

    def _copy_report(self) -> None:
        if self._last_result is None:
            return
        report = self._last_result.to_text(include_steps=True)
        self.clipboard_clear()
        self.clipboard_append(report)
        self._set_status("完整报告已复制到剪贴板。", "done")


def _set_windows_app_id() -> None:
    """让 Windows 将程序识别为独立应用，便于任务栏使用应用图标。"""

    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "IntegralSolver.Desktop.1.0"
        )
    except Exception:  # noqa: BLE001
        pass


def run() -> None:
    """启动图形界面。"""

    _set_windows_app_id()
    app = IntegralSolverApp()
    app.mainloop()


# 兼容直接运行本模块
if __name__ == "__main__":
    run()
