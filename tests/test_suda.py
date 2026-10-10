from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
import zlib
from pathlib import Path

from suda.bytecode import (
    COMPRESSED_BYTECODE_MAGIC,
    BytecodeProgram,
    disassemble,
    read_bytecode,
    write_bytecode,
)
from suda.cli import main
from suda.compiler import compile_source
from suda.errors import SudaError
from suda.lexer import tokenize
from suda.vm import VirtualMachine, run_source


class LexingTests(unittest.TestCase):
    def test_arabic_aliases_and_indentation(self) -> None:
        tokens = tokenize("اذا كان_صحيح:\n    اطبع(\"نعم\")\n")
        values = [(token.kind, token.value) for token in tokens]
        self.assertIn(("IDENT", "إذا"), values)
        self.assertIn(("INDENT", 4), values)
        self.assertIn(("DEDENT", 0), values)

    def test_rejects_inconsistent_indent(self) -> None:
        with self.assertRaisesRegex(SudaError, "لا تطابق"):
            tokenize("إذا صحيح:\n    اطبع(1)\n  اطبع(2)\n")

    def test_rejects_unterminated_string(self) -> None:
        with self.assertRaisesRegex(SudaError, "غير مغلق"):
            tokenize('اطبع("نص\n')

    def test_source_size_limit_counts_utf8_bytes(self) -> None:
        with self.assertRaisesRegex(SudaError, "1 MiB"):
            tokenize("س" * 600_000)

    def test_rejects_unpaired_unicode_surrogate(self) -> None:
        with self.assertRaisesRegex(SudaError, "Unicode غير صالح"):
            tokenize('اطبع("\\ud800")\n')

    def test_multiline_bracketed_expressions_do_not_change_indentation(self) -> None:
        source = """\
قيم = [
    1,
    2,
]
بيانات = {
    "أ": 1,
    "ب": 2,
}
اطبع(قيم, بيانات)
"""
        self.assertEqual(run_source(source), ["[1, 2] {\"أ\": 1, \"ب\": 2}"])

    def test_rejects_unclosed_and_mismatched_delimiters(self) -> None:
        with self.assertRaisesRegex(SudaError, "غير مغلق"):
            tokenize("قيم = [1, 2\n")
        with self.assertRaisesRegex(SudaError, "غير متطابق"):
            tokenize("قيم = [1, 2)\n")


class RuntimeTests(unittest.TestCase):
    def test_arithmetic_and_output(self) -> None:
        self.assertEqual(run_source('اطبع(2 + 3 * 4)\n'), ["14"])

    def test_functions_loops_and_global_lookup(self) -> None:
        source = """\
ثابت حد = 5
دالة مجموع_حتى(ن):
    مجموع = 0
    لكل عدد في مدى(1, ن + 1):
        مجموع = مجموع + عدد
    أرجع مجموع
اطبع(مجموع_حتى(حد))
"""
        self.assertEqual(run_source(source), ["15"])

    def test_short_circuit_does_not_evaluate_rhs(self) -> None:
        source = """\
اطبع(خطأ و (1 / 0))
اطبع(صحيح أو (1 / 0))
"""
        self.assertEqual(run_source(source), ["False", "True"])

    def test_if_else_and_while(self) -> None:
        source = """\
عدد = 0
طالما عدد < 3:
    عدد = عدد + 1
إذا عدد == 3:
    اطبع("اكتمل")
وإلا:
    اطبع("خطأ")
"""
        self.assertEqual(run_source(source), ["اكتمل"])

    def test_chained_comparisons_are_rejected(self) -> None:
        with self.assertRaisesRegex(SudaError, "المقارنات المتسلسلة"):
            compile_source("اطبع(1 < 2 < 3)\n")

    def test_dictionary_literals_and_index_assignment(self) -> None:
        source = """\
منتج = {"اسم": "قلم", "سعر": 3}
منتج["سعر"] = منتج["سعر"] + 2
ألوان = ["أحمر", "أزرق"]
ألوان[1] = "أخضر"
اطبع(منتج["اسم"], منتج["سعر"], ألوان[1])
"""
        self.assertEqual(run_source(source), ["قلم 5 أخضر"])

    def test_collection_builtins(self) -> None:
        source = """\
قائمة_العناصر = [1]
أضف(قائمة_العناصر, 2)
بيانات = {"أ": 10, "ب": 20}
قيمة = احذف(بيانات, "أ")
اطبع(قائمة_العناصر, مفاتيح(بيانات), قيم(بيانات), عناصر(بيانات), قيمة)
"""
        self.assertEqual(
            run_source(source),
            ["[1, 2] [\"ب\"] [20] [[\"ب\", 20]] 10"],
        )

    def test_sort_and_reverse_builtins(self) -> None:
        source = """\
قيم = [5, 2, 4, 1]
مرتبة = رتب(قيم)
معكوسة = اعكس(قيم)
اطبع(مرتبة, معكوسة, قيم)
"""
        self.assertEqual(run_source(source), ["[1, 2, 4, 5] [1, 4, 2, 5] [5, 2, 4, 1]"])

    def test_sort_and_reverse_respect_collection_limit(self) -> None:
        for function in ("رتب", "اعكس"):
            with self.subTest(function=function):
                with self.assertRaisesRegex(SudaError, "النتيجة أكبر من الحد"):
                    VirtualMachine(collection_limit=2).run(
                        compile_source(f'{function}("abc")\n')
                    )

    def test_sort_reports_incomparable_values(self) -> None:
        with self.assertRaisesRegex(SudaError, "فشل التنفيذ"):
            run_source('اطبع(رتب([1, "اثنان"]))\n')

    def test_dictionary_can_store_none_and_render_cycles(self) -> None:
        source = """\
بيانات = {"فارغ": لا_شيء}
بيانات["ذاتي"] = بيانات
اطبع(بيانات)
"""
        self.assertEqual(run_source(source), ['{"فارغ": None, "ذاتي": {...}}'])

    def test_break_and_continue_in_nested_loops(self) -> None:
        source = """\
مجموع = 0
لكل خارجي في مدى(3):
    لكل داخلي في مدى(5):
        إذا داخلي == 1:
            استمر
        إذا داخلي == 3:
            اكسر
        مجموع = مجموع + 1
اطبع(مجموع)
"""
        self.assertEqual(run_source(source), ["6"])

    def test_loop_control_outside_loop_is_compile_error(self) -> None:
        with self.assertRaisesRegex(SudaError, "داخل الحلقات"):
            compile_source("اكسر\n")

    def test_constant_cannot_be_reassigned(self) -> None:
        with self.assertRaisesRegex(SudaError, "الثابت"):
            run_source("ثابت قيمة = 1\nقيمة = 2\n")

    def test_step_budget_stops_infinite_loop(self) -> None:
        machine = VirtualMachine(step_limit=20)
        with self.assertRaisesRegex(SudaError, "حد التعليمات"):
            machine.run(compile_source("طالما صحيح:\n    قيمة = 1\n"))

    def test_output_is_bounded(self) -> None:
        machine = VirtualMachine(output_limit_bytes=5)
        with self.assertRaisesRegex(SudaError, "حد المخرجات"):
            machine.run(compile_source('اطبع("1234")\nاطبع("56")\n'))

    def test_large_string_repetition_is_rejected_before_allocation(self) -> None:
        machine = VirtualMachine(output_limit_bytes=100)
        with self.assertRaisesRegex(SudaError, "تكرار النص"):
            machine.run(compile_source('نص_كبير = "س" * 100000000\n'))

    def test_rendered_collection_respects_output_budget(self) -> None:
        machine = VirtualMachine(output_limit_bytes=40)
        source = 'قيم = ["س" * 10, "ص" * 10]\nاطبع(قيم)\n'
        with self.assertRaisesRegex(SudaError, "حد المخرجات"):
            machine.run(compile_source(source))

    def test_recursion_limit_is_reported(self) -> None:
        source = "دالة عودية():\n    أرجع عودية()\nاطبع(عودية())\n"
        with self.assertRaisesRegex(SudaError, "عمق الاستدعاء"):
            VirtualMachine(recursion_limit=8).run(compile_source(source))

    def test_recursion_limit_cannot_exceed_safe_host_bound(self) -> None:
        with self.assertRaisesRegex(ValueError, "بين 1 و128"):
            VirtualMachine(recursion_limit=129)

    def test_runtime_error_has_source_line(self) -> None:
        with self.assertRaisesRegex(SudaError, "السطر 1:.*القسمة"):
            run_source("اطبع(1 / 0)\n")


class BytecodeTests(unittest.TestCase):
    def test_bytecode_round_trip_and_execution(self) -> None:
        original = compile_source('اطبع("مرحبا", 7)\n')
        restored = BytecodeProgram.from_json(original.to_json())
        machine = VirtualMachine()
        machine.run(restored)
        self.assertEqual(machine.output_lines, ["مرحبا 7"])
        self.assertIn("CALL", disassemble(restored))

    def test_compressed_bytecode_round_trip_is_smaller(self) -> None:
        source = "\n".join(f'اطبع("رسالة عربية متكررة {index % 10}")' for index in range(100))
        program = compile_source(source)
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "program.sbc"
            write_bytecode(program, target, compress=True)
            compressed = target.read_bytes()
            self.assertTrue(compressed.startswith(COMPRESSED_BYTECODE_MAGIC))
            self.assertLess(len(compressed), len(program.to_json().encode("utf-8")))
            self.assertEqual(read_bytecode(target), program)

    def test_compressed_bytecode_rejects_expansion_over_limit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "oversized.sbc"
            target.write_bytes(
                COMPRESSED_BYTECODE_MAGIC + zlib.compress(b" " * 16_000_001)
            )
            with self.assertRaisesRegex(SudaError, "بعد فك الضغط.*16 MB"):
                read_bytecode(target)

    def test_compressed_bytecode_rejects_trailing_data(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "trailing.sbc"
            target.write_bytes(
                COMPRESSED_BYTECODE_MAGIC + zlib.compress(b"{}") + b"trailing"
            )
            with self.assertRaisesRegex(SudaError, "بيانات زائدة"):
                read_bytecode(target)

    def test_rejects_unknown_bytecode_instruction(self) -> None:
        payload = {
            "format": "suda-bytecode",
            "version": 1,
            "entry": 0,
            "functions": [
                {
                    "name": "main",
                    "parameters": [],
                    "instructions": [["EXEC", "danger", 1]],
                }
            ],
        }
        with self.assertRaisesRegex(SudaError, "تعليمة غير معروفة"):
            BytecodeProgram.from_json(json.dumps(payload))

    def test_rejects_bytecode_with_invalid_operand(self) -> None:
        payload = {
            "format": "suda-bytecode",
            "version": 1,
            "entry": 0,
            "functions": [
                {
                    "name": "main",
                    "parameters": [],
                    "instructions": [["JUMP", "0", 1]],
                }
            ],
        }
        with self.assertRaisesRegex(SudaError, "وجهة قفز"):
            BytecodeProgram.from_json(json.dumps(payload))

    def test_rejects_oversized_bytecode(self) -> None:
        with self.assertRaisesRegex(SudaError, "16 MB"):
            BytecodeProgram.from_json(" " * 16_000_001)

    def test_rejects_non_finite_float_constants(self) -> None:
        payload = {
            "format": "suda-bytecode",
            "version": 1,
            "entry": 0,
            "functions": [
                {
                    "name": "main",
                    "parameters": [],
                    "instructions": [["CONSTANT", float("inf"), 1]],
                }
            ],
        }
        with self.assertRaisesRegex(SudaError, "محدودًا"):
            BytecodeProgram.from_json(json.dumps(payload))

    def test_rejects_boolean_entry_index_without_coercion(self) -> None:
        payload = {
            "format": "suda-bytecode",
            "version": 1,
            "entry": True,
            "functions": [
                {"name": "main", "parameters": [], "instructions": []}
            ],
        }
        with self.assertRaisesRegex(SudaError, "نقطة الدخول"):
            BytecodeProgram.from_json(json.dumps(payload))


class CliTests(unittest.TestCase):
    def test_run_command(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "hello.sada"
            path.write_text('اطبع("أهلًا")\n', encoding="utf-8")
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                status = main(["run", str(path)])
            self.assertEqual(status, 0)
            self.assertEqual(stdout.getvalue(), "أهلًا\n")

    def test_compile_and_run_bytecode_commands(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "hello.sada"
            target = Path(directory) / "build" / "hello.sbc"
            source.write_text('اطبع("bytecode")\n', encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(["compile", str(source), "-o", str(target)]), 0)
                stdout = io.StringIO()
                with contextlib.redirect_stdout(stdout):
                    self.assertEqual(main(["run-bytecode", str(target)]), 0)
            self.assertEqual(stdout.getvalue(), "bytecode\n")

    def test_cli_compiles_and_runs_compressed_bytecode(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "hello.sada"
            target = Path(directory) / "hello.sbc"
            source.write_text('اطبع("مضغوط")\n', encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(
                    main(["compile", str(source), "-o", str(target), "--compress"]),
                    0,
                )
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(main(["run-bytecode", str(target)]), 0)
            self.assertEqual(output.getvalue(), "مضغوط\n")

    def test_bad_step_limit_is_argparse_error(self) -> None:
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as error:
                main(["run", "missing.sada", "--max-steps", "0"])
        self.assertEqual(error.exception.code, 2)

    def test_cli_rejects_unsafe_recursion_depth(self) -> None:
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as error:
                main(["run", "missing.sada", "--max-depth", "129"])
        self.assertEqual(error.exception.code, 2)

    def test_inventory_example(self) -> None:
        source_path = Path(__file__).parents[1] / "examples" / "المخزون.sada"
        source = source_path.read_text(encoding="utf-8")
        self.assertEqual(
            run_source(source),
            [
                "متاح: دفتر السعر: 2.5",
                "متاح: مسطرة السعر: 1.5",
                'المنتجات المتاحة: ["دفتر", "مسطرة"]',
            ],
        )

    def test_bubble_sort_example(self) -> None:
        source_path = Path(__file__).parents[1] / "examples" / "فرز.sada"
        self.assertEqual(
            run_source(source_path.read_text(encoding="utf-8")),
            ["[1, 2, 4, 5]"],
        )


if __name__ == "__main__":
    unittest.main()
