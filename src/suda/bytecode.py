"""Bytecode representation, compiler, and readable disassembler."""

from __future__ import annotations

import json
import math
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .errors import SourceLocation, SudaError
from .parser import Node

MAX_BYTECODE_BYTES = 16_000_000
COMPRESSED_BYTECODE_MAGIC = b"SUDA\x00Z1"
MAX_COMPRESSED_BYTECODE_BYTES = (
    MAX_BYTECODE_BYTES
    + (MAX_BYTECODE_BYTES >> 12)
    + (MAX_BYTECODE_BYTES >> 14)
    + (MAX_BYTECODE_BYTES >> 25)
    + 13
    + len(COMPRESSED_BYTECODE_MAGIC)
)


@dataclass(frozen=True)
class Instruction:
    opcode: str
    argument: Any
    line: int


@dataclass
class CodeObject:
    name: str
    parameters: list[str]
    instructions: list[Instruction]


@dataclass
class BytecodeProgram:
    functions: list[CodeObject]
    entry: int

    def validate(self) -> None:
        if len(self.functions) > 10_000:
            raise ValueError("عدد الدوال يتجاوز الحد.")
        if type(self.entry) is not int or not 0 <= self.entry < len(self.functions):
            raise ValueError("مؤشر نقطة الدخول خارج حدود البرنامج.")
        instruction_total = 0
        unary_operators = {"+", "-", "ليس"}
        binary_operators = {
            "+", "-", "*", "/", "//", "%", "**",
            "==", "!=", "<", "<=", ">", ">=",
        }
        for function in self.functions:
            if not isinstance(function.name, str) or len(function.name) > 1024:
                raise ValueError("اسم الدالة غير صالح.")
            if len(function.parameters) > 10_000 or any(
                not isinstance(parameter, str) or len(parameter) > 1024
                for parameter in function.parameters
            ):
                raise ValueError("قائمة وسائط الدالة غير صالحة.")
            if len(function.parameters) != len(set(function.parameters)):
                raise ValueError("وسيط الدالة مكرر.")
            instruction_total += len(function.instructions)
            if instruction_total > 1_000_000:
                raise ValueError("عدد تعليمات bytecode يتجاوز الحد.")
            for instruction in function.instructions:
                if type(instruction.line) is not int or instruction.line < 1:
                    raise ValueError("رقم سطر bytecode غير صالح.")
                opcode = instruction.opcode
                argument = instruction.argument
                if opcode == "CONSTANT":
                    if not (
                        argument is None
                        or type(argument) in (bool, int, float, str)
                    ):
                        raise ValueError("نوع ثابت bytecode غير مدعوم.")
                    if isinstance(argument, float) and not math.isfinite(argument):
                        raise ValueError("الثابت العشري يجب أن يكون محدودًا.")
                    if isinstance(argument, int) and argument.bit_length() > 4096:
                        raise ValueError("ثابت bytecode أكبر من الحد.")
                    if isinstance(argument, str):
                        try:
                            encoded_size = len(argument.encode("utf-8"))
                        except UnicodeEncodeError as error:
                            raise ValueError("ثابت نصي يحوي Unicode غير صالح.") from error
                        if encoded_size > 1_000_000:
                            raise ValueError("نص ثابت bytecode أكبر من الحد.")
                elif opcode in ("LOAD", "STORE", "STORE_CONST"):
                    if not isinstance(argument, str) or not argument or len(argument) > 1024:
                        raise ValueError(f"اسم غير صالح في التعليمة {opcode}.")
                elif opcode in ("BUILD_LIST", "BUILD_MAP", "CALL"):
                    if type(argument) is not int or not 0 <= argument <= 100_000:
                        raise ValueError(f"معامل غير صالح في التعليمة {opcode}.")
                elif opcode in ("JUMP", "JUMP_IF_FALSE", "JUMP_IF_TRUE", "ITER_NEXT"):
                    if type(argument) is not int or not 0 <= argument <= len(function.instructions):
                        raise ValueError("وجهة قفز خارج حدود الدالة.")
                elif opcode == "MAKE_FUNCTION":
                    if type(argument) is not int or not 0 <= argument < len(self.functions):
                        raise ValueError("مؤشر دالة خارج حدود البرنامج.")
                elif opcode == "UNARY":
                    if argument not in unary_operators:
                        raise ValueError("عامل أحادي غير مدعوم.")
                elif opcode == "BINARY":
                    if argument not in binary_operators:
                        raise ValueError("عامل ثنائي غير مدعوم.")
                elif opcode in ("POP", "DUP", "INDEX", "STORE_INDEX", "GET_ITER", "RETURN"):
                    if argument is not None:
                        raise ValueError(f"لا يقبل {opcode} معاملًا.")
                else:
                    raise ValueError(f"تعليمة غير معروفة: {opcode}")

    def to_json(self) -> str:
        try:
            self.validate()
        except (TypeError, ValueError) as error:
            raise SudaError(f"تعذر تسلسل bytecode غير صالح: {error}") from error
        payload = {
            "format": "suda-bytecode",
            "version": 1,
            "entry": self.entry,
            "functions": [
                {
                    "name": function.name,
                    "parameters": function.parameters,
                    "instructions": [
                        [instruction.opcode, instruction.argument, instruction.line]
                        for instruction in function.instructions
                    ],
                }
                for function in self.functions
            ],
        }
        result = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        if len(result.encode("utf-8")) > MAX_BYTECODE_BYTES:
            raise SudaError("حجم bytecode الناتج يتجاوز الحد (16 MB).")
        return result

    @classmethod
    def from_json(cls, text: str) -> "BytecodeProgram":
        try:
            encoded_size = len(text.encode("utf-8"))
        except UnicodeEncodeError as error:
            raise SudaError("ملف bytecode يحوي Unicode غير صالح.") from error
        if encoded_size > MAX_BYTECODE_BYTES:
            raise SudaError("ملف bytecode يتجاوز الحد المسموح (16 MB).")
        try:
            payload = json.loads(text)
            if not isinstance(payload, dict):
                raise ValueError("جذر الملف يجب أن يكون كائن JSON.")
            if payload["format"] != "suda-bytecode" or payload["version"] != 1:
                raise ValueError("نسخة تنسيق bytecode غير مدعومة.")
            if type(payload["entry"]) is not int:
                raise ValueError("مؤشر نقطة الدخول يجب أن يكون عددًا صحيحًا.")
            if not isinstance(payload["functions"], list):
                raise ValueError("قائمة الدوال غير صالحة.")
            functions = []
            for function in payload["functions"]:
                if not isinstance(function, dict):
                    raise ValueError("تعريف دالة bytecode غير صالح.")
                name = function["name"]
                parameters = function["parameters"]
                rows = function["instructions"]
                if not isinstance(name, str) or not isinstance(parameters, list):
                    raise ValueError("اسم الدالة أو وسائطها غير صالحة.")
                if not all(isinstance(parameter, str) for parameter in parameters):
                    raise ValueError("وسيط الدالة يجب أن يكون نصًا.")
                if not isinstance(rows, list):
                    raise ValueError("تعليمات الدالة يجب أن تكون قائمة.")
                instructions = []
                for row in rows:
                    if (
                        not isinstance(row, list)
                        or len(row) != 3
                        or not isinstance(row[0], str)
                        or type(row[2]) is not int
                    ):
                        raise ValueError("سجل تعليمة bytecode غير صالح.")
                    instructions.append(Instruction(row[0], row[1], row[2]))
                functions.append(CodeObject(name, parameters, instructions))
            entry = payload["entry"]
            program = cls(functions, entry)
            program.validate()
            return program
        except (KeyError, TypeError, ValueError, IndexError, json.JSONDecodeError, RecursionError) as error:
            raise SudaError(f"ملف bytecode غير صالح: {error}") from error


class Compiler:
    def __init__(self):
        self.functions: list[CodeObject] = []
        self.instructions: list[Instruction] = []
        self._function_indices: dict[str, int] = {}
        self._loop_stack: list[dict[str, Any]] = []

    def compile(self, program: Node) -> BytecodeProgram:
        declarations = [statement for statement in program.children if statement.kind == "function"]
        for declaration in declarations:
            name = str(declaration.value)
            if name in self._function_indices:
                raise SudaError(
                    f"تعريف الدالة «{name}» مكرر.",
                    SourceLocation(declaration.line),
                )
            index = len(self.functions)
            self._function_indices[name] = index
            self.functions.append(CodeObject(name, [], []))

        entry = len(self.functions)
        self.functions.append(CodeObject("<الرئيسية>", [], []))
        self.instructions = self.functions[entry].instructions
        self._loop_stack = []

        for declaration in declarations:
            index = self._function_indices[str(declaration.value)]
            parameters = list(declaration.children[0].value)
            code = CodeObject(str(declaration.value), parameters, [])
            self.functions[index] = code
            previous = self.instructions
            self.instructions = code.instructions
            self._loop_stack = []
            for statement in declaration.children[1].children:
                self._statement(statement, in_function=True)
            self._emit("CONSTANT", None, declaration.line)
            self._emit("RETURN", None, declaration.line)
            self.instructions = previous

        for statement in program.children:
            if statement.kind == "function":
                index = self._function_indices[str(statement.value)]
                self._emit("MAKE_FUNCTION", index, statement.line)
                self._emit("STORE", str(statement.value), statement.line)
            else:
                self._statement(statement, in_function=False)
        self._emit("CONSTANT", None, program.line)
        self._emit("RETURN", None, program.line)
        return BytecodeProgram(self.functions, entry)

    def _emit(self, opcode: str, argument: Any, line: int) -> int:
        self.instructions.append(Instruction(opcode, argument, line))
        return len(self.instructions) - 1

    def _patch(self, index: int, target: int) -> None:
        old = self.instructions[index]
        self.instructions[index] = Instruction(old.opcode, target, old.line)

    def _statement(self, node: Node, in_function: bool) -> None:
        if node.kind == "assign":
            self._expression(node.children[0])
            self._emit("STORE", node.value, node.line)
        elif node.kind == "const":
            self._expression(node.children[0])
            self._emit("STORE_CONST", node.value, node.line)
        elif node.kind == "assign_index":
            self._expression(node.children[0])
            self._expression(node.children[1])
            self._expression(node.children[2])
            self._emit("STORE_INDEX", None, node.line)
        elif node.kind == "expression_statement":
            self._expression(node.children[0])
            self._emit("POP", None, node.line)
        elif node.kind == "return":
            if not in_function:
                raise SudaError("أرجع مسموح داخل الدوال فقط.", SourceLocation(node.line))
            self._expression(node.children[0])
            self._emit("RETURN", None, node.line)
        elif node.kind == "loop_control":
            if not self._loop_stack:
                raise SudaError(
                    f"«{node.value}» مسموح داخل الحلقات فقط.",
                    SourceLocation(node.line),
                )
            loop = self._loop_stack[-1]
            if node.value == "اكسر":
                if loop["break_pop_iterator"]:
                    self._emit("POP", None, node.line)
                loop["breaks"].append(self._emit("JUMP", None, node.line))
            else:
                self._emit("JUMP", loop["continue_target"], node.line)
        elif node.kind == "if":
            self._expression(node.children[0])
            false_jump = self._emit("JUMP_IF_FALSE", None, node.line)
            for statement in node.children[1].children:
                self._statement(statement, in_function)
            if node.children[2].children:
                end_jump = self._emit("JUMP", None, node.line)
                self._patch(false_jump, len(self.instructions))
                for statement in node.children[2].children:
                    self._statement(statement, in_function)
                self._patch(end_jump, len(self.instructions))
            else:
                self._patch(false_jump, len(self.instructions))
        elif node.kind == "while":
            start = len(self.instructions)
            self._expression(node.children[0])
            end_jump = self._emit("JUMP_IF_FALSE", None, node.line)
            loop = {
                "breaks": [],
                "continue_target": start,
                "break_pop_iterator": False,
            }
            self._loop_stack.append(loop)
            for statement in node.children[1].children:
                self._statement(statement, in_function)
            self._emit("JUMP", start, node.line)
            end = len(self.instructions)
            self._patch(end_jump, end)
            for jump in loop["breaks"]:
                self._patch(jump, end)
            self._loop_stack.pop()
        elif node.kind == "for":
            self._expression(node.children[0])
            self._emit("GET_ITER", None, node.line)
            start = len(self.instructions)
            next_instruction = self._emit("ITER_NEXT", None, node.line)
            self._emit("STORE", node.value, node.line)
            loop = {
                "breaks": [],
                "continue_target": start,
                "break_pop_iterator": True,
            }
            self._loop_stack.append(loop)
            for statement in node.children[1].children:
                self._statement(statement, in_function)
            self._emit("JUMP", start, node.line)
            end = len(self.instructions)
            self._patch(next_instruction, end)
            for jump in loop["breaks"]:
                self._patch(jump, end)
            self._loop_stack.pop()
        else:
            raise SudaError(f"تعليمة غير مدعومة: {node.kind}.", SourceLocation(node.line))

    def _expression(self, node: Node) -> None:
        if node.kind == "literal":
            self._emit("CONSTANT", node.value, node.line)
        elif node.kind == "name":
            self._emit("LOAD", node.value, node.line)
        elif node.kind == "list":
            for child in node.children:
                self._expression(child)
            self._emit("BUILD_LIST", len(node.children), node.line)
        elif node.kind == "dict":
            for child in node.children:
                self._expression(child)
            self._emit("BUILD_MAP", len(node.children) // 2, node.line)
        elif node.kind == "index":
            self._expression(node.children[0])
            self._expression(node.children[1])
            self._emit("INDEX", None, node.line)
        elif node.kind == "unary":
            self._expression(node.children[0])
            self._emit("UNARY", node.value, node.line)
        elif node.kind == "binary":
            operator = str(node.value)
            if operator in ("و", "أو"):
                self._expression(node.children[0])
                self._emit("DUP", None, node.line)
                jump = self._emit("JUMP_IF_FALSE" if operator == "و" else "JUMP_IF_TRUE", None, node.line)
                self._emit("POP", None, node.line)
                self._expression(node.children[1])
                self._patch(jump, len(self.instructions))
            else:
                self._expression(node.children[0])
                self._expression(node.children[1])
                self._emit("BINARY", operator, node.line)
        elif node.kind == "call":
            self._expression(node.children[0])
            for argument in node.children[1:]:
                self._expression(argument)
            self._emit("CALL", len(node.children) - 1, node.line)
        else:
            raise SudaError(f"تعبير غير مدعوم: {node.kind}.", SourceLocation(node.line))


def compile_ast(program: Node) -> BytecodeProgram:
    return Compiler().compile(program)


def disassemble(program: BytecodeProgram) -> str:
    lines: list[str] = []
    for index, function in enumerate(program.functions):
        parameters = ", ".join(function.parameters)
        lines.append(f"الدالة {index}: {function.name}({parameters})")
        for position, instruction in enumerate(function.instructions):
            argument = "" if instruction.argument is None else f" {instruction.argument!r}"
            lines.append(f"  {position:04d}  {instruction.opcode}{argument}  # سطر {instruction.line}")
    return "\n".join(lines)


def write_bytecode(
    program: BytecodeProgram,
    path: str | Path,
    *,
    compress: bool = False,
) -> None:
    encoded = program.to_json().encode("utf-8")
    if compress:
        encoded = COMPRESSED_BYTECODE_MAGIC + zlib.compress(encoded, level=9)
        Path(path).write_bytes(encoded)
    else:
        Path(path).write_bytes(encoded)


def read_bytecode(path: str | Path) -> BytecodeProgram:
    bytecode_path = Path(path)
    if bytecode_path.stat().st_size > MAX_COMPRESSED_BYTECODE_BYTES:
        raise SudaError("ملف bytecode يتجاوز الحد المسموح (16 MB).")
    encoded = bytecode_path.read_bytes()
    if len(encoded) > MAX_COMPRESSED_BYTECODE_BYTES:
        raise SudaError("ملف bytecode يتجاوز الحد المسموح (16 MB).")
    if encoded.startswith(COMPRESSED_BYTECODE_MAGIC):
        try:
            decompressor = zlib.decompressobj()
            payload = decompressor.decompress(
                encoded[len(COMPRESSED_BYTECODE_MAGIC):],
                MAX_BYTECODE_BYTES + 1,
            )
            if len(payload) > MAX_BYTECODE_BYTES or decompressor.unconsumed_tail:
                raise SudaError("محتوى bytecode بعد فك الضغط يتجاوز الحد (16 MB).")
            if not decompressor.eof or decompressor.unused_data:
                raise SudaError("تدفق bytecode المضغوط غير مكتمل أو يحوي بيانات زائدة.")
            payload += decompressor.flush()
            if len(payload) > MAX_BYTECODE_BYTES:
                raise SudaError("محتوى bytecode بعد فك الضغط يتجاوز الحد (16 MB).")
        except zlib.error as error:
            raise SudaError(f"تعذر فك ضغط bytecode: {error}") from error
    else:
        if len(encoded) > MAX_BYTECODE_BYTES:
            raise SudaError("ملف bytecode يتجاوز الحد المسموح (16 MB).")
        payload = encoded
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as error:
        raise SudaError("ملف bytecode يجب أن يكون بترميز UTF-8 صالح.") from error
    return BytecodeProgram.from_json(text)
