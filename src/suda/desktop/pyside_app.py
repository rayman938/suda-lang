"""Optional PySide6 learning studio with animated, source-based lessons."""

from __future__ import annotations

from pathlib import Path

from .content import LANGUAGE_REFERENCE, LESSONS, STARTER_SOURCE, STUDY_REPORT
from ..errors import SudaError
from .runner import RunResult, run_editor_source
from .voice import speak

try:
    from PySide6.QtCore import QThread, QTimer, Qt, Signal
    from PySide6.QtGui import (
        QColor,
        QFont,
        QFontMetrics,
        QLinearGradient,
        QPainter,
        QPen,
        QSyntaxHighlighter,
        QTextCharFormat,
    )
    from PySide6.QtWidgets import (
        QApplication,
        QFileDialog,
        QHBoxLayout,
        QLabel,
        QListWidget,
        QMainWindow,
        QMessageBox,
        QPushButton,
        QSlider,
        QTabWidget,
        QTextEdit,
        QVBoxLayout,
        QWidget,
    )
except ImportError as error:
    raise SudaError(
        "واجهة PySide6 تحتاج الإضافة الاختيارية: "
        'python -m pip install "suda-lang[qt]"'
    ) from error


class SudaHighlighter(QSyntaxHighlighter):
    KEYWORDS = (
        "إذا",
        "اذا",
        "وإلا",
        "طالما",
        "لكل",
        "في",
        "دالة",
        "أرجع",
        "ثابت",
        "اكسر",
        "استمر",
        "صحيح",
        "خطأ",
        "لا_شيء",
        "و",
        "أو",
        "ليس",
    )

    def highlightBlock(self, text: str) -> None:
        keyword_format = QTextCharFormat()
        keyword_format.setForeground(QColor("#70dec4"))
        keyword_format.setFontWeight(QFont.Weight.Bold)
        for keyword in self.KEYWORDS:
            start = 0
            while True:
                index = text.find(keyword, start)
                if index < 0:
                    break
                left_ok = index == 0 or (
                    not text[index - 1].isalnum() and text[index - 1] != "_"
                )
                end = index + len(keyword)
                right_ok = end == len(text) or (
                    not text[end].isalnum() and text[end] != "_"
                )
                if left_ok and right_ok:
                    self.setFormat(index, len(keyword), keyword_format)
                start = end


class AnimatedScene(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setMinimumHeight(380)
        self.progress = 0
        self.lesson_index = 0

    def paintEvent(self, _event: object) -> None:
        lesson = LESSONS[self.lesson_index]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        background = QLinearGradient(0, 0, self.width(), self.height())
        background.setColorAt(0, QColor("#0a1426"))
        background.setColorAt(1, QColor("#1c3551"))
        painter.fillRect(self.rect(), background)

        painter.setPen(QColor("#e0edf9"))
        painter.setFont(QFont("Segoe UI", 21, QFont.Weight.Bold))
        painter.drawText(
            self.rect().adjusted(24, 20, -24, -20),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop,
            f"مشهد {self.lesson_index + 1}: {lesson.title}",
        )
        painter.setPen(QColor("#80e5ce"))
        painter.setFont(QFont("Segoe UI", 12))
        painter.drawText(
            self.rect().adjusted(24, 62, -24, -20),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop,
            lesson.summary,
        )

        labels = {
            "pipeline": ("مصدر", "تحليل", "bytecode", "تشغيل"),
            "values": ("اسم", "قيمة", "نوع", "ناتج"),
            "branches": ("شرط", "صح؟", "مسار أ", "مسار ب"),
            "loops": ("بداية", "عنصر", "تحديث", "تكرار"),
            "functions": ("تعريف", "وسائط", "حساب", "إرجاع"),
            "collections": ("قائمة", "فهرسة", "تعديل", "عرض"),
            "bytecode": ("مصدر", "AST", "تحقق", "VM"),
            "roadmap": ("تعلّم", "اختبر", "قِس", "طوّر"),
        }[lesson.scene]
        centers = [int(self.width() * ratio) for ratio in (0.12, 0.38, 0.64, 0.9)]
        center_y = int(self.height() * 0.54)
        active = min(3, self.progress * 4 // 101)
        font = QFont("Segoe UI", 11, QFont.Weight.Bold)
        painter.setFont(font)
        for index, center_x in enumerate(centers):
            if index < len(centers) - 1:
                painter.setPen(QPen(QColor("#536d8b"), 3))
                painter.drawLine(center_x + 34, center_y, centers[index + 1] - 34, center_y)
            painter.setPen(QPen(QColor("#a4f1df" if index <= active else "#5b718a"), 2))
            painter.setBrush(QColor("#278c78" if index <= active else "#263d59"))
            painter.drawEllipse(center_x - 31, center_y - 31, 62, 62)
            painter.setPen(QColor("#ffffff"))
            painter.drawText(
                center_x - 22,
                center_y - 22,
                44,
                44,
                Qt.AlignmentFlag.AlignCenter,
                str(index + 1),
            )
            painter.setPen(QColor("#d9e8f7"))
            painter.drawText(
                center_x - 65,
                center_y + 54,
                130,
                30,
                Qt.AlignmentFlag.AlignCenter,
                labels[index],
            )

        dot_x = centers[0] + (centers[-1] - centers[0]) * self.progress / 100
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#ffd273"))
        painter.drawEllipse(int(dot_x - 7), center_y - 78, 14, 14)
        painter.setPen(QColor("#dbe9f7"))
        painter.setFont(QFont("Segoe UI", 11))
        caption = QFontMetrics(painter.font()).elidedText(
            lesson.narration_ar,
            Qt.TextElideMode.ElideRight,
            self.width() - 80,
        )
        painter.drawText(
            self.rect().adjusted(32, 0, -32, -24),
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom,
            caption,
        )


class SourceWorker(QThread):
    completed = Signal(object)

    def __init__(self, source: str):
        super().__init__()
        self.source = source

    def run(self) -> None:
        self.completed.emit(run_editor_source(self.source))


class VoiceWorker(QThread):
    completed = Signal(str)

    def __init__(self, text: str, language: str):
        super().__init__()
        self.text = text
        self.language = language

    def run(self) -> None:
        try:
            speak(self.text, self.language)
        except (RuntimeError, OSError) as error:
            self.completed.emit(f"تعذر تشغيل الصوت: {error}")
            return
        self.completed.emit("انتهى التعليق الصوتي.")


class SudaWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("سُدى | استوديو تعلّم البرمجة")
        self.resize(1220, 840)
        self.setMinimumSize(940, 660)
        self.current_lesson = 0
        self.source_path: Path | None = None
        self.workers: list[QThread] = []
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.setStyleSheet(
            """
            QMainWindow, QWidget { background: #101a2d; color: #dce8f5; }
            QTabWidget::pane { border: 1px solid #263952; }
            QTabBar::tab { background: #24344e; padding: 12px 20px; }
            QTabBar::tab:selected { background: #287a6d; }
            QPushButton { background: #287a6d; border: 0; border-radius: 6px; padding: 9px 14px; font-weight: bold; }
            QPushButton:hover { background: #37a48e; }
            QListWidget, QTextEdit { background: #0b1322; border: 1px solid #304661; selection-background-color: #287a6d; }
            """
        )
        central = QWidget()
        root = QVBoxLayout(central)
        heading = QLabel("سُدى — استوديو تعلّم وكتابة لغة سُدى")
        heading.setStyleSheet("color: #77e3cb; font-size: 24px; font-weight: bold;")
        root.addWidget(heading)
        self.tabs = QTabWidget()
        root.addWidget(self.tabs, 1)
        self._build_editor()
        self._build_learning()
        self._build_animation()
        self._build_report()
        self._build_reference()
        self.statusBar().showMessage("جاهز — اكتب برنامجك أو اختَر درسًا.")
        self.setCentralWidget(central)

    def _build_editor(self) -> None:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        toolbar = QHBoxLayout()
        self._button(toolbar, "شغّل البرنامج", self._run_source)
        self._button(toolbar, "مثال جاهز", self._load_starter)
        self._button(toolbar, "افتح ملف", self._open_file)
        self._button(toolbar, "احفظ ملف", self._save_file)
        toolbar.addStretch(1)
        layout.addLayout(toolbar)
        self.editor = QTextEdit()
        self.editor.setAcceptRichText(False)
        self.editor.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.editor.setFont(QFont("Consolas", 13))
        self.editor.setTabStopDistance(4 * self.editor.fontMetrics().horizontalAdvance(" "))
        self.highlighter = SudaHighlighter(self.editor.document())
        layout.addWidget(QLabel("محرر سُدى"))
        layout.addWidget(self.editor, 3)
        layout.addWidget(QLabel("الناتج أو رسالة الخطأ"))
        self.output = QTextEdit()
        self.output.setReadOnly(True)
        self.output.setMaximumHeight(180)
        self.output.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        layout.addWidget(self.output, 1)
        self._load_starter()
        self.tabs.addTab(tab, "المحرر والتشغيل")

    def _build_learning(self) -> None:
        tab = QWidget()
        layout = QHBoxLayout(tab)
        self.lesson_list = QListWidget()
        for lesson in LESSONS:
            self.lesson_list.addItem(lesson.title)
        self.lesson_list.setFixedWidth(200)
        self.lesson_list.currentRowChanged.connect(self._show_lesson)
        layout.addWidget(self.lesson_list)
        body = QVBoxLayout()
        self.lesson_title = QLabel()
        self.lesson_title.setStyleSheet("color: #7be0c9; font-size: 17px; font-weight: bold;")
        body.addWidget(self.lesson_title)
        self.lesson_text = QTextEdit()
        self.lesson_text.setReadOnly(True)
        self.lesson_text.setFont(QFont("Segoe UI", 12))
        body.addWidget(self.lesson_text, 1)
        actions = QHBoxLayout()
        self._button(actions, "حمّل المثال بالمحرر", self._load_lesson_example)
        self._button(actions, "انطق بالعربي", lambda: self._speak_lesson("ar"))
        self._button(actions, "Narrate in English", lambda: self._speak_lesson("en"))
        actions.addStretch(1)
        body.addLayout(actions)
        layout.addLayout(body, 1)
        self.tabs.addTab(tab, "تعلم خطوة بخطوة")
        self.lesson_list.setCurrentRow(0)

    def _build_animation(self) -> None:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        title = QLabel("دروس مرئية أصلية — رسوم متحركة بلا وجوه أو مواد من الإنترنت")
        title.setStyleSheet("color: #7be0c9; font-size: 14px; font-weight: bold;")
        layout.addWidget(title)
        note = QLabel(
            "هذه مشاهد تعليمية تتحرك داخل التطبيق وليست ملفات MP4. "
            "الصوت اختياري ويستخدم أصوات النظام المثبتة."
        )
        layout.addWidget(note)
        self.scene = AnimatedScene()
        layout.addWidget(self.scene, 1)
        controls = QHBoxLayout()
        self._button(controls, "▶ شغّل المشهد", self._play_animation)
        self._button(controls, "إيقاف مؤقت", self._pause_animation)
        self._button(controls, "الصوت العربي", lambda: self._speak_lesson("ar"))
        self._button(controls, "English voice", lambda: self._speak_lesson("en"))
        self.timeline = QSlider(Qt.Orientation.Horizontal)
        self.timeline.setRange(0, 100)
        self.timeline.valueChanged.connect(self._seek_animation)
        controls.addWidget(self.timeline, 1)
        layout.addLayout(controls)
        self.timer = QTimer(self)
        self.timer.setInterval(60)
        self.timer.timeout.connect(self._tick_animation)
        self.tabs.addTab(tab, "مشاهد متحركة")

    def _build_report(self) -> None:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        heading = QLabel("تقرير مختصر: شنو تتعلم وشنو تستفاد؟")
        heading.setStyleSheet("color: #7be0c9; font-size: 17px; font-weight: bold;")
        layout.addWidget(heading)
        report = QTextEdit()
        report.setReadOnly(True)
        report.setFont(QFont("Segoe UI", 12))
        report.setPlainText(STUDY_REPORT)
        layout.addWidget(report, 1)
        self.tabs.addTab(tab, "التقرير")

    def _build_reference(self) -> None:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        reference = QTextEdit()
        reference.setReadOnly(True)
        reference.setFont(QFont("Segoe UI", 11))
        reference.setPlainText(LANGUAGE_REFERENCE)
        layout.addWidget(reference, 1)
        self.tabs.addTab(tab, "مرجع اللغة")

    def _button(self, layout: QHBoxLayout, text: str, action: object) -> None:
        button = QPushButton(text)
        button.clicked.connect(action)
        layout.addWidget(button)

    def _load_starter(self) -> None:
        self.editor.setPlainText(STARTER_SOURCE)
        self.statusBar().showMessage("حمّلنا مثال البداية. عدّل عليه أو شغّل البرنامج.")

    def _run_source(self) -> None:
        self.output.setPlainText("دا أشغّل البرنامج...")
        worker = SourceWorker(self.editor.toPlainText())
        worker.completed.connect(self._show_run_result)
        worker.finished.connect(lambda: self._forget_worker(worker))
        self.workers.append(worker)
        worker.start()

    def _show_run_result(self, result: RunResult) -> None:
        if result.error:
            self.output.setPlainText(f"خطأ: {result.error}")
            self.statusBar().showMessage(f"توقف البرنامج بعد {result.steps} تعليمة.")
        else:
            self.output.setPlainText(result.output)
            self.statusBar().showMessage(f"اكتمل التنفيذ — {result.steps} تعليمة.")

    def _open_file(self) -> None:
        filename, _filter = QFileDialog.getOpenFileName(
            self,
            "افتح ملف سُدى",
            "",
            "ملفات سُدى (*.sada);;ملفات نصية (*.txt);;الكل (*)",
        )
        if not filename:
            return
        path = Path(filename)
        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as error:
            QMessageBox.critical(self, "تعذر فتح الملف", str(error))
            return
        self.editor.setPlainText(source)
        self.source_path = path
        self.statusBar().showMessage(f"فتحنا الملف: {path.name}")

    def _save_file(self) -> None:
        path = self.source_path
        if path is None:
            filename, _filter = QFileDialog.getSaveFileName(
                self,
                "احفظ برنامج سُدى",
                "",
                "ملفات سُدى (*.sada);;ملفات نصية (*.txt)",
            )
            if not filename:
                return
            path = Path(filename)
        try:
            path.write_text(self.editor.toPlainText(), encoding="utf-8")
        except OSError as error:
            QMessageBox.critical(self, "تعذر حفظ الملف", str(error))
            return
        self.source_path = path
        self.statusBar().showMessage(f"انحفظ الملف: {path.name}")

    def _show_lesson(self, index: int) -> None:
        if not 0 <= index < len(LESSONS):
            return
        self.current_lesson = index
        lesson = LESSONS[index]
        self.lesson_title.setText(f"{index + 1}. {lesson.title} — {lesson.summary}")
        self.lesson_text.setPlainText(
            f"{lesson.explanation}\n\nمثال الدرس:\n{lesson.source}\n"
            "تذكّر: سُدى حاليًا نموذج أولي؛ افتح الدليل الكامل حتى تعرف التفاصيل والحدود."
        )
        if hasattr(self, "scene"):
            self.scene.lesson_index = index
            self.scene.progress = 0
            self.scene.update()
            self.timeline.setValue(0)

    def _load_lesson_example(self) -> None:
        self.editor.setPlainText(LESSONS[self.current_lesson].source)
        self.tabs.setCurrentIndex(0)
        self.statusBar().showMessage(f"حمّلنا مثال درس «{LESSONS[self.current_lesson].title}».")

    def _speak_lesson(self, language: str) -> None:
        lesson = LESSONS[self.current_lesson]
        text = lesson.narration_ar if language == "ar" else lesson.narration_en
        worker = VoiceWorker(text, language)
        worker.completed.connect(self.statusBar().showMessage)
        worker.finished.connect(lambda: self._forget_worker(worker))
        self.workers.append(worker)
        self.statusBar().showMessage("دا يجهز الصوت من أصوات النظام...")
        worker.start()

    def _play_animation(self) -> None:
        self.timer.start()
        self.statusBar().showMessage("المشهد التعليمي الأصلي دا يشتغل.")

    def _pause_animation(self) -> None:
        self.timer.stop()
        self.statusBar().showMessage("وقفنا المشهد مؤقتًا.")

    def _tick_animation(self) -> None:
        self.timeline.setValue((self.timeline.value() + 1) % 101)

    def _seek_animation(self, value: int) -> None:
        if hasattr(self, "scene"):
            self.scene.progress = value
            self.scene.update()

    def _forget_worker(self, worker: QThread) -> None:
        if worker in self.workers:
            self.workers.remove(worker)


def launch() -> int:
    application = QApplication.instance() or QApplication([])
    window = SudaWindow()
    window.show()
    return application.exec()
