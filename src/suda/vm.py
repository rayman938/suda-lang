"""Bounded stack-based Suda bytecode virtual machine."""

from __future__ import annotations

import json
import math
import operator
from dataclasses import dataclass, field
from typing import Any, Callable

from .bytecode import BytecodeProgram, CodeObject
from .compiler import compile_source
from .errors import SourceLocation, SudaError


@dataclass
class UserFunction:
    code_index: int


@dataclass
class Frame:
    code: CodeObject
    locals: dict[str, Any]
    constants: set[str] = field(default_factory=set)


_BINARY: dict[str, Callable[[Any, Any], Any]] = {
    "+": operator.add,
    "-": operator.sub,
    "*": operator.mul,
    "/": operator.truediv,
    "//": operator.floordiv,
    "%": operator.mod,
    "**": operator.pow,
    "==": operator.eq,
    "!=": operator.ne,
    "<": operator.lt,
    "<=": operator.le,
    ">": operator.gt,
    ">=": operator.ge,
}

MAX_RECURSION_DEPTH = 128


def json_quote(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


class VirtualMachine:
    def __init__(
        self,
        *,
        step_limit: int = 1_000_000,
        recursion_limit: int = 128,
        collection_limit: int = 100_000,
        output: Callable[[str], None] | None = None,
        output_limit_bytes: int = 1_000_000,
    ):
        if (
            step_limit <= 0
            or recursion_limit <= 0
            or recursion_limit > MAX_RECURSION_DEPTH
            or collection_limit <= 0
            or output_limit_bytes <= 0
        ):
            raise ValueError(
                f"حدود الآلة الافتراضية غير صالحة؛ عمق الاستدعاء يجب أن يكون بين 1 و{MAX_RECURSION_DEPTH}."
            )
        self.step_limit = step_limit
        self.recursion_limit = recursion_limit
        self.collection_limit = collection_limit
        self.output = output
        self.output_limit_bytes = output_limit_bytes
        self.output_bytes = 0
        self.output_lines: list[str] = []
        self.globals: dict[str, Any] = {}
        self.global_constants: set[str] = set()
        self.steps = 0
        self._builtin_functions = self._builtins()

    def run(self, program: BytecodeProgram) -> Any:
        try:
            program.validate()
        except (TypeError, ValueError) as error:
            raise SudaError(f"برنامج bytecode غير صالح: {error}") from error
        self.steps = 0
        self.output_lines = []
        self.output_bytes = 0
        self.globals = {}
        self.global_constants = set()
        self._invoke(program, UserFunction(program.entry), [], 0)
        return None

    def _emit_output(self, value: str) -> None:
        byte_count = len(value.encode("utf-8"))
        if (
            self.output_bytes + byte_count > self.output_limit_bytes
            or len(self.output_lines) >= self.collection_limit
        ):
            raise SudaError("تجاوز البرنامج حد المخرجات.")
        self.output_bytes += byte_count
        if self.output is not None:
            self.output(value)
        self.output_lines.append(value)

    def _builtins(self) -> dict[str, Callable[..., Any]]:
        def bounded_range(*args: int) -> range:
            result = range(*args)
            if len(result) > self.collection_limit:
                raise ValueError(f"المدى أكبر من الحد ({self.collection_limit}).")
            return result

        def bounded_values(iterable: Any) -> list[Any]:
            values = []
            for value in iterable:
                if len(values) >= self.collection_limit:
                    raise ValueError(
                        f"النتيجة أكبر من الحد ({self.collection_limit})."
                    )
                values.append(value)
            return values

        def sort_values(iterable: Any) -> list[Any]:
            return sorted(bounded_values(iterable))

        def reverse_values(iterable: Any) -> list[Any]:
            return list(reversed(bounded_values(iterable)))

        def append_bounded(collection: list[Any], value: Any) -> None:
            if not isinstance(collection, list):
                raise TypeError("أضف يتطلب قائمة.")
            if len(collection) >= self.collection_limit:
                raise ValueError(f"القائمة بلغت الحد ({self.collection_limit}).")
            collection.append(value)

        def remove_key(mapping: dict[Any, Any], key: Any) -> Any:
            if not isinstance(mapping, dict):
                raise TypeError("احذف يتطلب قاموسًا.")
            return mapping.pop(key)

        def print_arabic(*values: Any) -> None:
            chunks: list[str] = []
            remaining = self.output_limit_bytes - self.output_bytes

            def append(text: str) -> None:
                nonlocal remaining
                size = len(text.encode("utf-8"))
                remaining -= size
                if remaining < 0:
                    raise SudaError("تجاوز البرنامج حد المخرجات.")
                chunks.append(text)

            def render(value: Any, active: set[int], depth: int, nested: bool) -> None:
                if isinstance(value, str):
                    append(json_quote(value) if nested else value)
                    return
                if isinstance(value, (list, dict)):
                    identity = id(value)
                    if identity in active:
                        append("[...]" if isinstance(value, list) else "{...}")
                        return
                    if depth >= 64:
                        append("...")
                        return
                    active.add(identity)
                    opening, closing = ("[", "]") if isinstance(value, list) else ("{", "}")
                    append(opening)
                    if isinstance(value, list):
                        for position, item in enumerate(value):
                            if position:
                                append(", ")
                            render(item, active, depth + 1, True)
                    else:
                        for position, (key, item) in enumerate(value.items()):
                            if position:
                                append(", ")
                            render(key, active, depth + 1, True)
                            append(": ")
                            render(item, active, depth + 1, True)
                    append(closing)
                    active.remove(identity)
                    return
                append(str(value))

            for index, value in enumerate(values):
                if index:
                    append(" ")
                render(value, set(), 0, False)
            self._emit_output("".join(chunks))

        return {
            "اطبع": print_arabic,
            "اطبع_سطر": print_arabic,
            "طول": len,
            "مدى": bounded_range,
            "نطاق": bounded_range,
            "نص": str,
            "عدد": int,
            "عائم": float,
            "نوع": lambda value: type(value).__name__,
            "أقصى": max,
            "أدنى": min,
            "مجموع": sum,
            "اجمع": sum,
            "رتب": sort_values,
            "اعكس": reverse_values,
            "أضف": append_bounded,
            "مفاتيح": lambda mapping: list(mapping.keys()),
            "قيم": lambda mapping: list(mapping.values()),
            "عناصر": lambda mapping: [list(item) for item in mapping.items()],
            "احذف": remove_key,
        }

    def _invoke(
        self,
        program: BytecodeProgram,
        function: UserFunction,
        arguments: list[Any],
        depth: int,
    ) -> Any:
        if depth >= self.recursion_limit:
            raise SudaError(f"تجاوز عمق الاستدعاء الحد ({self.recursion_limit}).")
        code = program.functions[function.code_index]
        if len(arguments) != len(code.parameters):
            raise SudaError(
                f"الدالة «{code.name}» تتوقع {len(code.parameters)} وسيطًا، "
                f"لكن وصلها {len(arguments)}."
            )
        local_scope = (
            self.globals
            if function.code_index == program.entry
            else dict(zip(code.parameters, arguments))
        )
        frame = Frame(code, local_scope)
        stack: list[Any] = []
        ip = 0
        builtins = self._builtin_functions
        while ip < len(code.instructions):
            instruction = code.instructions[ip]
            ip += 1
            self.steps += 1
            if self.steps > self.step_limit:
                raise SudaError(f"تجاوز التنفيذ حد التعليمات ({self.step_limit}).")
            location = SourceLocation(instruction.line)
            try:
                opcode = instruction.opcode
                argument = instruction.argument
                if opcode == "CONSTANT":
                    self._check_value(argument, location)
                    stack.append(argument)
                elif opcode == "LOAD":
                    if argument in frame.locals:
                        stack.append(frame.locals[argument])
                    elif argument in self.globals:
                        stack.append(self.globals[argument])
                    elif argument in builtins:
                        stack.append(builtins[argument])
                    else:
                        raise SudaError(f"اسم غير معرّف: «{argument}».", location)
                elif opcode in ("STORE", "STORE_CONST"):
                    value = stack.pop()
                    if argument in frame.constants or (
                        frame is not None
                        and frame.locals is self.globals
                        and argument in self.global_constants
                    ):
                        raise SudaError(f"لا يمكن إعادة إسناد الثابت «{argument}».", location)
                    frame.locals[argument] = value
                    if opcode == "STORE_CONST":
                        frame.constants.add(argument)
                        if frame.locals is self.globals:
                            self.global_constants.add(argument)
                elif opcode == "POP":
                    stack.pop()
                elif opcode == "DUP":
                    stack.append(stack[-1])
                elif opcode == "BUILD_LIST":
                    count = int(argument)
                    values = stack[-count:] if count else []
                    if count:
                        del stack[-count:]
                    if len(values) > self.collection_limit:
                        raise SudaError("القائمة أكبر من حد العناصر.", location)
                    stack.append(list(values))
                elif opcode == "BUILD_MAP":
                    count = int(argument)
                    pair_count = count * 2
                    values = stack[-pair_count:] if pair_count else []
                    if pair_count:
                        del stack[-pair_count:]
                    result = {}
                    for index in range(0, pair_count, 2):
                        result[values[index]] = values[index + 1]
                    if len(result) > self.collection_limit:
                        raise SudaError("القاموس أكبر من حد العناصر.", location)
                    stack.append(result)
                elif opcode == "INDEX":
                    index = stack.pop()
                    collection = stack.pop()
                    stack.append(collection[index])
                elif opcode == "STORE_INDEX":
                    value = stack.pop()
                    index = stack.pop()
                    collection = stack.pop()
                    if not isinstance(collection, (list, dict)):
                        raise SudaError("الإسناد بالفهرس متاح للقوائم والقواميس فقط.", location)
                    if isinstance(collection, list) and not isinstance(index, int):
                        raise SudaError("فهرس القائمة يجب أن يكون عددًا صحيحًا.", location)
                    if (
                        isinstance(collection, dict)
                        and index not in collection
                        and len(collection) >= self.collection_limit
                    ):
                        raise SudaError("القاموس بلغ حد العناصر.", location)
                    collection[index] = value
                    self._check_value(collection, location)
                elif opcode == "UNARY":
                    value = stack.pop()
                    if argument == "-":
                        stack.append(-value)
                    elif argument == "+":
                        stack.append(+value)
                    elif argument == "ليس":
                        stack.append(not value)
                    else:
                        raise SudaError(f"عامل أحادي غير مدعوم: {argument}.", location)
                    self._check_value(stack[-1], location)
                elif opcode == "BINARY":
                    right = stack.pop()
                    left = stack.pop()
                    if argument == "**" and isinstance(right, (int, float)) and abs(right) > 10000:
                        raise SudaError("قيمة الأس تتجاوز الحد (10000).", location)
                    self._check_binary_size(str(argument), left, right, location)
                    if (
                        argument == "**"
                        and type(left) is int
                        and type(right) is int
                        and right > 1
                        and abs(left) not in (0, 1)
                        and (abs(left).bit_length() - 1) * right + 1 > 4096
                    ):
                        raise SudaError("نتيجة الأس تتجاوز حد 4096 بت.", location)
                    stack.append(_BINARY[argument](left, right))
                    self._check_value(stack[-1], location)
                    if isinstance(stack[-1], float) and not math.isfinite(stack[-1]):
                        raise SudaError("نتيجة عددية غير محدودة.", location)
                elif opcode == "JUMP":
                    ip = int(argument)
                elif opcode == "JUMP_IF_FALSE":
                    if not stack.pop():
                        ip = int(argument)
                elif opcode == "JUMP_IF_TRUE":
                    if stack.pop():
                        ip = int(argument)
                elif opcode == "GET_ITER":
                    stack.append(iter(stack.pop()))
                elif opcode == "ITER_NEXT":
                    try:
                        stack.append(next(stack[-1]))
                    except StopIteration:
                        stack.pop()
                        ip = int(argument)
                elif opcode == "MAKE_FUNCTION":
                    stack.append(UserFunction(int(argument)))
                elif opcode == "CALL":
                    count = int(argument)
                    call_arguments = stack[-count:] if count else []
                    if count:
                        del stack[-count:]
                    callee = stack.pop()
                    if isinstance(callee, UserFunction):
                        stack.append(
                            self._invoke(program, callee, call_arguments, depth + 1)
                        )
                    elif callable(callee):
                        result = callee(*call_arguments)
                        self._check_value(result, location)
                        stack.append(result)
                    else:
                        raise SudaError("القيمة المطلوبة ليست دالة قابلة للاستدعاء.", location)
                elif opcode == "RETURN":
                    return stack.pop()
                else:
                    raise SudaError(f"تعليمة bytecode غير معروفة: {opcode}.", location)
                if len(stack) > self.collection_limit:
                    raise SudaError("تجاوز مكدس القيم الحد المسموح.", location)
            except SudaError:
                raise
            except ZeroDivisionError as error:
                raise SudaError("القسمة على صفر غير مسموحة.", location) from error
            except (ArithmeticError, IndexError, KeyError, TypeError, ValueError, OverflowError) as error:
                raise SudaError(f"فشل التنفيذ: {error}.", location) from error
        return None

    def _check_binary_size(
        self,
        operator_name: str,
        left: Any,
        right: Any,
        location: SourceLocation,
    ) -> None:
        if operator_name == "+":
            if isinstance(left, str) and isinstance(right, str):
                size = len(left.encode("utf-8")) + len(right.encode("utf-8"))
                if size > self.output_limit_bytes:
                    raise SudaError("نتيجة ضم النصوص تتجاوز الحد.", location)
            elif isinstance(left, list) and isinstance(right, list):
                if len(left) + len(right) > self.collection_limit:
                    raise SudaError("نتيجة ضم القوائم تتجاوز الحد.", location)
        if operator_name == "*":
            sequence, count = (left, right) if type(right) is int else (right, left)
            if type(count) is int and isinstance(sequence, (str, list, tuple)):
                if isinstance(sequence, str):
                    size = len(sequence.encode("utf-8")) * max(0, count)
                    if size > self.output_limit_bytes:
                        raise SudaError("نتيجة تكرار النص تتجاوز الحد.", location)
                elif len(sequence) * max(0, count) > self.collection_limit:
                    raise SudaError("نتيجة تكرار القائمة تتجاوز الحد.", location)

    def _check_value(self, value: Any, location: SourceLocation) -> None:
        if isinstance(value, int) and value.bit_length() > 4096:
            raise SudaError("حجم العدد الصحيح تجاوز 4096 بت.", location)
        if isinstance(value, float) and not math.isfinite(value):
            raise SudaError("القيمة العشرية يجب أن تكون محدودة.", location)
        if isinstance(value, str):
            try:
                encoded_size = len(value.encode("utf-8"))
            except UnicodeEncodeError as error:
                raise SudaError("النص يحتوي محرف Unicode غير صالح.", location) from error
            if encoded_size > self.output_limit_bytes:
                raise SudaError("حجم النص تجاوز حد البايتات.", location)
        if isinstance(value, (bytes, list, tuple, dict, set, range)) and len(value) > self.collection_limit:
            raise SudaError("حجم المجموعة تجاوز الحد.", location)


def run_source(
    source: str,
    *,
    step_limit: int = 1_000_000,
    recursion_limit: int = 128,
    collection_limit: int = 100_000,
) -> list[str]:
    machine = VirtualMachine(
        step_limit=step_limit,
        recursion_limit=recursion_limit,
        collection_limit=collection_limit,
    )
    machine.run(compile_source(source))
    return machine.output_lines
