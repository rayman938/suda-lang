"""Command-line interface for compiling and running Suda programs."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .bytecode import disassemble, read_bytecode, write_bytecode
from .compiler import compile_source
from .errors import SudaError
from .vm import MAX_RECURSION_DEPTH, VirtualMachine


def _positive_int(value: str) -> int:
    try:
        result = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("أدخل عددًا صحيحًا موجبًا.") from error
    if result <= 0:
        raise argparse.ArgumentTypeError("أدخل عددًا أكبر من صفر.")
    return result


def _recursion_limit(value: str) -> int:
    result = _positive_int(value)
    if result > MAX_RECURSION_DEPTH:
        raise argparse.ArgumentTypeError(
            f"أقصى عمق استدعاء مسموح هو {MAX_RECURSION_DEPTH}."
        )
    return result


def _read_source(path: str) -> str:
    try:
        return Path(path).read_text(encoding="utf-8")
    except OSError as error:
        raise SudaError(f"تعذرت قراءة الملف «{path}»: {error}") from error
    except UnicodeError as error:
        raise SudaError(f"يجب حفظ الملف «{path}» بترميز UTF-8: {error}") from error


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="suda", description="مترجم ومشغل لغة سُدى")
    parser.add_argument("--version", action="version", version=f"suda {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)

    run = commands.add_parser("run", help="ترجمة ملف وتشغيله")
    run.add_argument("source")
    run.add_argument("--max-steps", type=_positive_int, default=1_000_000)
    run.add_argument("--max-depth", type=_recursion_limit, default=128)

    check = commands.add_parser("check", help="التحقق من صحة الملف بترجمته")
    check.add_argument("source")

    compile_command = commands.add_parser("compile", help="إنشاء ملف bytecode")
    compile_command.add_argument("source")
    compile_command.add_argument("-o", "--output", required=True)
    compile_command.add_argument(
        "--compress",
        action="store_true",
        help="ضغط bytecode باستخدام zlib لتقليل حجم الملف",
    )

    disassemble_command = commands.add_parser("disassemble", help="عرض تعليمات bytecode")
    disassemble_command.add_argument("bytecode")

    run_bytecode = commands.add_parser("run-bytecode", help="تشغيل ملف bytecode")
    run_bytecode.add_argument("bytecode")
    run_bytecode.add_argument("--max-steps", type=_positive_int, default=1_000_000)

    desktop = commands.add_parser("gui", help="فتح استوديو تعلّم سُدى")
    desktop.add_argument(
        "--backend",
        choices=("tkinter", "pyside6"),
        default="tkinter",
        help="واجهة خفيفة مدمجة أو واجهة PySide6 الاختيارية",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        if arguments.command == "run":
            program = compile_source(_read_source(arguments.source))
            machine = VirtualMachine(
                step_limit=arguments.max_steps,
                recursion_limit=arguments.max_depth,
                output=print,
            )
            machine.run(program)
            return 0
        if arguments.command == "check":
            compile_source(_read_source(arguments.source))
            print(f"سليم نحويًا: {arguments.source}")
            return 0
        if arguments.command == "compile":
            program = compile_source(_read_source(arguments.source))
            Path(arguments.output).parent.mkdir(parents=True, exist_ok=True)
            write_bytecode(program, arguments.output, compress=arguments.compress)
            suffix = " (مضغوط)" if arguments.compress else ""
            print(f"أُنشئ bytecode{suffix}: {arguments.output}")
            return 0
        if arguments.command == "disassemble":
            print(disassemble(read_bytecode(arguments.bytecode)))
            return 0
        if arguments.command == "run-bytecode":
            machine = VirtualMachine(step_limit=arguments.max_steps, output=print)
            machine.run(read_bytecode(arguments.bytecode))
            return 0
        if arguments.command == "gui":
            if arguments.backend == "pyside6":
                from .desktop.pyside_app import launch

                return launch()
            from .desktop.tkinter_app import launch

            launch()
            return 0
    except (SudaError, OSError) as error:
        print(f"خطأ: {error}", file=sys.stderr)
        return 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
