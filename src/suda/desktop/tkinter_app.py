"""Lightweight Tkinter desktop editor and learning studio."""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any

from .content import LANGUAGE_REFERENCE, LESSONS, STARTER_SOURCE, STUDY_REPORT
from ..errors import SudaError
from .runner import RunResult, run_editor_source
from .voice import speak


class SudaDesktop:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("سُدى | استوديو تعلّم البرمجة")
        self.root.geometry("1180x820")
        self.root.minsize(900, 650)
        self.root.configure(background="#101a2d")
        self.events: queue.Queue[tuple[str, Any]] = queue.Queue()
        self.current_lesson = 0
        self.animation_progress = 0
        self.animation_job: str | None = None
        self.source_path: Path | None = None
        self.status = tk.StringVar(value="جاهز — اكتب برنامجك أو اختَر درسًا.")
        self._configure_style()
        self._build()
        self.root.after(80, self._drain_events)
        self._show_lesson(0)

    def _configure_style(self) -> None:
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure(
            "TNotebook",
            background="#101a2d",
            borderwidth=0,
        )
        style.configure(
            "TNotebook.Tab",
            background="#24344e",
            foreground="#dce8f5",
            padding=(18, 11),
            font=("Segoe UI", 11, "bold"),
        )
        style.map(
            "TNotebook.Tab",
            background=[("selected", "#2f927f")],
            foreground=[("selected", "#ffffff")],
        )
        style.configure(
            "TButton",
            background="#287a6d",
            foreground="#ffffff",
            padding=(11, 8),
            font=("Segoe UI", 10, "bold"),
        )
        style.map("TButton", background=[("active", "#37a48e")])
        style.configure(
            "TFrame",
            background="#101a2d",
        )
        style.configure(
            "TLabelframe",
            background="#101a2d",
            foreground="#dce8f5",
        )
        style.configure(
            "TLabelframe.Label",
            background="#101a2d",
            foreground="#7be0c9",
            font=("Segoe UI", 10, "bold"),
        )
        style.configure(
            "TLabel",
            background="#101a2d",
            foreground="#dce8f5",
            font=("Segoe UI", 10),
        )

    def _build(self) -> None:
        header = tk.Frame(self.root, bg="#101a2d", padx=22, pady=14)
        header.pack(fill="x")
        tk.Label(
            header,
            text="سُدى",
            bg="#101a2d",
            fg="#77e3cb",
            font=("Segoe UI", 27, "bold"),
        ).pack(side="right")
        tk.Label(
            header,
            text="استوديو تعلّم وكتابة لغة سُدى — النموذج التجريبي 0.6.0",
            bg="#101a2d",
            fg="#becde0",
            font=("Segoe UI", 11),
        ).pack(side="right", padx=16, pady=(9, 0))

        self.tabs = ttk.Notebook(self.root)
        self.tabs.pack(fill="both", expand=True, padx=18, pady=(0, 12))
        self._build_editor_tab()
        self._build_learning_tab()
        self._build_animation_tab()
        self._build_report_tab()
        self._build_reference_tab()
        ttk.Label(self.root, textvariable=self.status, anchor="e").pack(
            fill="x",
            padx=22,
            pady=(0, 9),
        )

    def _build_editor_tab(self) -> None:
        tab = ttk.Frame(self.tabs, padding=12)
        self.tabs.add(tab, text="المحرر والتشغيل")
        toolbar = ttk.Frame(tab)
        toolbar.pack(fill="x", pady=(0, 9))
        ttk.Button(toolbar, text="شغّل البرنامج", command=self._run_source).pack(
            side="right",
            padx=(0, 7),
        )
        ttk.Button(toolbar, text="مثال جاهز", command=self._load_starter).pack(
            side="right",
            padx=7,
        )
        ttk.Button(toolbar, text="افتح ملف", command=self._open_file).pack(
            side="right",
            padx=7,
        )
        ttk.Button(toolbar, text="احفظ ملف", command=self._save_file).pack(
            side="right",
            padx=7,
        )
        ttk.Label(
            toolbar,
            text="تُشغّل الشيفرة بحدود موارد افتراضية؛ هذا للتعلّم وليس sandbox أمنيًا.",
        ).pack(side="left", padx=6)

        panes = tk.PanedWindow(
            tab,
            orient="vertical",
            sashwidth=7,
            bg="#263952",
            bd=0,
        )
        panes.pack(fill="both", expand=True)
        editor_frame = ttk.LabelFrame(panes, text="اكتب برنامج سُدى هنا", padding=8)
        output_frame = ttk.LabelFrame(panes, text="الناتج أو رسالة الخطأ", padding=8)
        panes.add(editor_frame, minsize=220)
        panes.add(output_frame, minsize=140)
        self.editor = tk.Text(
            editor_frame,
            wrap="none",
            undo=True,
            bg="#0b1322",
            fg="#e1efff",
            insertbackground="#7be0c9",
            selectbackground="#285e68",
            font=("Consolas", 13),
            padx=12,
            pady=12,
            relief="flat",
        )
        editor_scroll = ttk.Scrollbar(
            editor_frame,
            orient="vertical",
            command=self.editor.yview,
        )
        self.editor.configure(yscrollcommand=editor_scroll.set)
        editor_scroll.pack(side="right", fill="y")
        self.editor.pack(fill="both", expand=True)
        self.output = tk.Text(
            output_frame,
            height=7,
            wrap="word",
            state="disabled",
            bg="#0b1322",
            fg="#bdebdc",
            font=("Consolas", 11),
            padx=12,
            pady=10,
            relief="flat",
        )
        self.output.pack(fill="both", expand=True)
        self._load_starter()

    def _build_learning_tab(self) -> None:
        tab = ttk.Frame(self.tabs, padding=12)
        self.tabs.add(tab, text="تعلم خطوة بخطوة")
        tab.columnconfigure(1, weight=1)
        tab.rowconfigure(0, weight=1)
        self.lesson_list = tk.Listbox(
            tab,
            width=23,
            exportselection=False,
            bg="#17263d",
            fg="#e1efff",
            selectbackground="#287a6d",
            font=("Segoe UI", 11),
            relief="flat",
        )
        for number, lesson in enumerate(LESSONS, start=1):
            self.lesson_list.insert("end", f"{number:02d}  {lesson.title}")
        self.lesson_list.grid(row=0, column=0, sticky="ns", padx=(0, 12))
        self.lesson_list.bind("<<ListboxSelect>>", self._lesson_selected)

        body = ttk.Frame(tab)
        body.grid(row=0, column=1, sticky="nsew")
        body.columnconfigure(0, weight=1)
        body.rowconfigure(1, weight=1)
        self.lesson_title = ttk.Label(
            body,
            text="",
            font=("Segoe UI", 18, "bold"),
            foreground="#7be0c9",
        )
        self.lesson_title.grid(row=0, column=0, sticky="e", pady=(0, 8))
        self.lesson_text = tk.Text(
            body,
            wrap="word",
            state="disabled",
            bg="#0b1322",
            fg="#dce8f5",
            font=("Segoe UI", 12),
            padx=18,
            pady=16,
            relief="flat",
        )
        self.lesson_text.grid(row=1, column=0, sticky="nsew")
        actions = ttk.Frame(body)
        actions.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        ttk.Button(
            actions,
            text="حمّل مثال الدرس بالمحرر",
            command=self._load_lesson_example,
        ).pack(side="right", padx=(0, 8))
        ttk.Button(
            actions,
            text="انطق بالعربي",
            command=lambda: self._speak_lesson("ar"),
        ).pack(side="right", padx=8)
        ttk.Button(
            actions,
            text="Narrate in English",
            command=lambda: self._speak_lesson("en"),
        ).pack(side="right", padx=8)

    def _build_animation_tab(self) -> None:
        tab = ttk.Frame(self.tabs, padding=12)
        self.tabs.add(tab, text="مشاهد متحركة")
        tk.Label(
            tab,
            text="دروس مرئية أصلية — رسوم متحركة بلا وجوه أو مواد مأخوذة من الإنترنت",
            bg="#101a2d",
            fg="#7be0c9",
            font=("Segoe UI", 12, "bold"),
        ).pack(anchor="e", pady=(0, 9))
        tk.Label(
            tab,
            text="هذه مشاهد تعليمية تتحرك داخل التطبيق وليست ملفات MP4. الصوت اختياري ويستخدم أصوات النظام المثبتة.",
            bg="#101a2d",
            fg="#becde0",
            font=("Segoe UI", 10),
        ).pack(anchor="e", pady=(0, 12))
        self.animation = tk.Canvas(
            tab,
            height=390,
            bg="#081222",
            highlightthickness=1,
            highlightbackground="#35506c",
        )
        self.animation.pack(fill="both", expand=True)
        self.animation.bind("<Configure>", lambda _event: self._draw_scene())
        controls = ttk.Frame(tab)
        controls.pack(fill="x", pady=(10, 0))
        ttk.Button(controls, text="▶ شغّل المشهد", command=self._play_animation).pack(
            side="right",
            padx=(0, 8),
        )
        ttk.Button(controls, text="إيقاف مؤقت", command=self._pause_animation).pack(
            side="right",
            padx=8,
        )
        ttk.Button(
            controls,
            text="الصوت العربي",
            command=lambda: self._speak_lesson("ar"),
        ).pack(side="left", padx=8)
        ttk.Button(
            controls,
            text="English voice",
            command=lambda: self._speak_lesson("en"),
        ).pack(side="left", padx=8)
        self.timeline = tk.Scale(
            controls,
            from_=0,
            to=100,
            orient="horizontal",
            showvalue=False,
            command=self._seek_animation,
            bg="#101a2d",
            fg="#dce8f5",
            troughcolor="#24344e",
            highlightthickness=0,
            length=340,
        )
        self.timeline.pack(side="left", fill="x", expand=True, padx=12)

    def _build_report_tab(self) -> None:
        tab = ttk.Frame(self.tabs, padding=12)
        self.tabs.add(tab, text="تقرير الفائدة والحدود")
        report = tk.Text(
            tab,
            wrap="word",
            state="normal",
            bg="#0b1322",
            fg="#dce8f5",
            font=("Segoe UI", 12),
            padx=18,
            pady=16,
            relief="flat",
        )
        report.insert("1.0", STUDY_REPORT)
        report.configure(state="disabled")
        report.pack(fill="both", expand=True)

    def _build_reference_tab(self) -> None:
        tab = ttk.Frame(self.tabs, padding=12)
        self.tabs.add(tab, text="مرجع اللغة")
        reference = tk.Text(
            tab,
            wrap="word",
            state="normal",
            bg="#0b1322",
            fg="#dce8f5",
            font=("Segoe UI", 11),
            padx=18,
            pady=16,
            relief="flat",
        )
        reference.insert("1.0", LANGUAGE_REFERENCE)
        reference.configure(state="disabled")
        reference.pack(fill="both", expand=True)

    def _load_starter(self) -> None:
        self.editor.delete("1.0", "end")
        self.editor.insert("1.0", STARTER_SOURCE)
        self.status.set("حمّلنا مثال البداية. عدّل عليه أو اضغط «شغّل البرنامج».")
        self.tabs.select(0)

    def _run_source(self) -> None:
        source = self.editor.get("1.0", "end-1c")
        self._set_output("دا أشغّل البرنامج...\n")
        self.status.set("التنفيذ جارٍ ضمن حدود موارد.")
        threading.Thread(
            target=self._run_worker,
            args=(source,),
            daemon=True,
            name="suda-vm-runner",
        ).start()

    def _run_worker(self, source: str) -> None:
        self.events.put(("run", run_editor_source(source)))

    def _drain_events(self) -> None:
        while True:
            try:
                kind, payload = self.events.get_nowait()
            except queue.Empty:
                break
            if kind == "run":
                result: RunResult = payload
                if result.error:
                    self._set_output(f"خطأ: {result.error}\n")
                    self.status.set(f"توقف البرنامج بعد {result.steps} تعليمة.")
                else:
                    self._set_output(result.output + ("\n" if result.output else ""))
                    self.status.set(f"اكتمل التنفيذ — {result.steps} تعليمة.")
            elif kind == "voice":
                self.status.set(str(payload))
        self.root.after(80, self._drain_events)

    def _set_output(self, text: str) -> None:
        self.output.configure(state="normal")
        self.output.delete("1.0", "end")
        self.output.insert("1.0", text)
        self.output.configure(state="disabled")

    def _open_file(self) -> None:
        filename = filedialog.askopenfilename(
            title="افتح ملف سُدى",
            filetypes=[("ملفات سُدى", "*.sada"), ("ملفات نصية", "*.txt"), ("الكل", "*.*")],
        )
        if not filename:
            return
        path = Path(filename)
        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as error:
            messagebox.showerror("تعذر فتح الملف", str(error), parent=self.root)
            return
        self.editor.delete("1.0", "end")
        self.editor.insert("1.0", source)
        self.source_path = path
        self.status.set(f"فتحنا الملف: {path.name}")

    def _save_file(self) -> None:
        path = self.source_path
        if path is None:
            filename = filedialog.asksaveasfilename(
                title="احفظ برنامج سُدى",
                defaultextension=".sada",
                filetypes=[("ملفات سُدى", "*.sada"), ("ملفات نصية", "*.txt")],
            )
            if not filename:
                return
            path = Path(filename)
        try:
            path.write_text(self.editor.get("1.0", "end-1c"), encoding="utf-8")
        except OSError as error:
            messagebox.showerror("تعذر حفظ الملف", str(error), parent=self.root)
            return
        self.source_path = path
        self.status.set(f"انحفظ الملف: {path.name}")

    def _lesson_selected(self, _event: tk.Event[tk.Misc]) -> None:
        selected = self.lesson_list.curselection()
        if selected:
            self._show_lesson(selected[0])

    def _show_lesson(self, index: int) -> None:
        self.current_lesson = index
        lesson = LESSONS[index]
        self.lesson_title.configure(text=f"{index + 1}. {lesson.title} — {lesson.summary}")
        content = (
            f"{lesson.explanation}\n\n"
            f"مثال الدرس:\n{lesson.source}\n"
            "تذكّر: سُدى حاليًا نموذج أولي؛ افتح الدليل الكامل حتى تعرف كل التفاصيل والحدود."
        )
        self.lesson_text.configure(state="normal")
        self.lesson_text.delete("1.0", "end")
        self.lesson_text.insert("1.0", content)
        self.lesson_text.configure(state="disabled")
        self.lesson_list.selection_clear(0, "end")
        self.lesson_list.selection_set(index)
        self.lesson_list.activate(index)
        self.animation_progress = 0
        self.timeline.set(0)
        self._draw_scene()

    def _load_lesson_example(self) -> None:
        self.editor.delete("1.0", "end")
        self.editor.insert("1.0", LESSONS[self.current_lesson].source)
        self.tabs.select(0)
        self.status.set(f"حمّلنا مثال درس «{LESSONS[self.current_lesson].title}».")

    def _speak_lesson(self, language: str) -> None:
        lesson = LESSONS[self.current_lesson]
        narration = lesson.narration_ar if language == "ar" else lesson.narration_en
        self.status.set("دا يجهز الصوت من صوت النظام المثبت...")
        threading.Thread(
            target=self._voice_worker,
            args=(narration, language),
            daemon=True,
            name="suda-local-narrator",
        ).start()

    def _voice_worker(self, text: str, language: str) -> None:
        try:
            speak(text, language)
        except (RuntimeError, OSError) as error:
            self.events.put(("voice", f"تعذر تشغيل الصوت: {error}"))
            return
        self.events.put(("voice", "انتهى التعليق الصوتي."))

    def _seek_animation(self, value: str) -> None:
        self.animation_progress = int(float(value))
        self._draw_scene()

    def _play_animation(self) -> None:
        if self.animation_job is None:
            self._tick_animation()
            self.status.set("المشهد التعليمي الأصلي دا يشتغل.")

    def _pause_animation(self) -> None:
        if self.animation_job is not None:
            self.root.after_cancel(self.animation_job)
            self.animation_job = None
            self.status.set("وقفنا المشهد مؤقتًا.")

    def _tick_animation(self) -> None:
        self.animation_progress += 1
        if self.animation_progress > 100:
            self.animation_progress = 0
        self.timeline.set(self.animation_progress)
        self._draw_scene()
        self.animation_job = self.root.after(60, self._tick_animation)

    def _draw_scene(self) -> None:
        canvas = self.animation
        if not canvas.winfo_exists():
            return
        canvas.delete("all")
        width = max(canvas.winfo_width(), 640)
        height = max(canvas.winfo_height(), 320)
        lesson = LESSONS[self.current_lesson]
        canvas.create_text(
            width - 30,
            30,
            text=f"مشهد {self.current_lesson + 1}: {lesson.title}",
            anchor="ne",
            fill="#dce8f5",
            font=("Segoe UI", 20, "bold"),
        )
        canvas.create_text(
            width - 30,
            68,
            text=lesson.summary,
            anchor="ne",
            fill="#82dec9",
            font=("Segoe UI", 12),
        )
        node_labels = {
            "pipeline": ("مصدر", "تحليل", "bytecode", "تشغيل"),
            "values": ("اسم", "قيمة", "نوع", "ناتج"),
            "branches": ("شرط", "صح؟", "مسار أ", "مسار ب"),
            "loops": ("بداية", "عنصر", "تحديث", "تكرار"),
            "functions": ("تعريف", "وسائط", "حساب", "إرجاع"),
            "collections": ("قائمة", "فهرسة", "تعديل", "عرض"),
            "bytecode": ("مصدر", "AST", "تحقق", "VM"),
            "roadmap": ("تعلّم", "اختبر", "قِس", "طوّر"),
        }[lesson.scene]
        center_y = int(height * 0.52)
        radius = max(24, min(34, width // 32))
        gap = (width - 180) / 3
        active = min(3, self.animation_progress * 4 // 101)
        positions = [int(90 + index * gap) for index in range(4)]
        for index in range(4):
            x = positions[index]
            lit = index <= active
            color = "#38b99b" if lit else "#253a55"
            canvas.create_oval(
                x - radius,
                center_y - radius,
                x + radius,
                center_y + radius,
                fill=color,
                outline="#a7f3e3" if lit else "#536b86",
                width=2,
            )
            canvas.create_text(
                x,
                center_y,
                text=str(index + 1),
                fill="#ffffff",
                font=("Segoe UI", 15, "bold"),
            )
            canvas.create_text(
                x,
                center_y + radius + 27,
                text=node_labels[index],
                fill="#d8e8f7",
                font=("Segoe UI", 12, "bold"),
            )
            if index < 3:
                canvas.create_line(
                    x + radius + 8,
                    center_y,
                    positions[index + 1] - radius - 8,
                    center_y,
                    fill="#58718e",
                    width=3,
                    arrow="last",
                )
        dot_x = positions[0] + (positions[-1] - positions[0]) * self.animation_progress / 100
        canvas.create_oval(
            dot_x - 7,
            center_y - radius - 32,
            dot_x + 7,
            center_y - radius - 18,
            fill="#ffcf70",
            outline="",
        )
        canvas.create_text(
            width // 2,
            height - 44,
            text=lesson.narration_ar,
            fill="#dce8f5",
            width=width - 100,
            font=("Segoe UI", 11),
        )

    def run(self) -> None:
        self.root.mainloop()


def launch() -> None:
    try:
        SudaDesktop().run()
    except tk.TclError as error:
        raise SudaError(f"تعذر فتح واجهة سطح المكتب: {error}") from error
