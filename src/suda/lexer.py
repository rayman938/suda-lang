"""Tokenizer for the Arabic-first Suda syntax."""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass

from .errors import SourceLocation, SudaError


@dataclass(frozen=True)
class Token:
    kind: str
    value: object
    line: int
    column: int


_IDENTIFIER = re.compile(r"[^\W\d]\w*", re.UNICODE)
_NUMBER = re.compile(r"(?:\d+\.\d+|\d+)")
_ALIASES = {
    "اذا": "إذا",
    "والا": "وإلا",
    "إلا": "وإلا",
    "ارجع": "أرجع",
    "تابع": "دالة",
    "طالما": "طالما",
    "صحيح": "صحيح",
    "خطأ": "خطأ",
    "لا_شيء": "لا_شيء",
    "ليس": "ليس",
    "و": "و",
    "او": "أو",
    "اكسر": "اكسر",
    "استمر": "استمر",
}


def _canonical_word(value: str) -> str:
    value = unicodedata.normalize("NFC", value)
    return _ALIASES.get(value, value)


def tokenize(source: str) -> list[Token]:
    try:
        source_bytes = len(source.encode("utf-8"))
    except UnicodeEncodeError as error:
        raise SudaError("المصدر يحتوي محرف Unicode غير صالح.") from error
    if source_bytes > 1_000_000:
        raise SudaError("حجم المصدر يتجاوز الحد المسموح (1 MiB).")

    tokens: list[Token] = []
    indentation = [0]
    delimiters: list[tuple[str, SourceLocation]] = []
    matching_delimiter = {")": "(", "]": "[", "}": "{"}
    lines = source.splitlines()
    for line_number, line in enumerate(lines, start=1):
        continuation = bool(delimiters)
        if not continuation and "\t" in line[: len(line) - len(line.lstrip())]:
            raise SudaError(
                "استخدم المسافات البادئة ولا تستخدم tab.",
                SourceLocation(line_number, 1),
            )
        content = line.lstrip(" ") if not continuation else line.lstrip(" \t")
        if not content or content.startswith("#"):
            if continuation:
                continue
            continue
        indent = len(line) - len(content)
        if not continuation:
            if indent > indentation[-1]:
                indentation.append(indent)
                tokens.append(Token("INDENT", indent, line_number, 1))
            else:
                while indent < indentation[-1]:
                    indentation.pop()
                    tokens.append(Token("DEDENT", indent, line_number, 1))
                if indent != indentation[-1]:
                    raise SudaError(
                        "المسافة البادئة لا تطابق مستوى كتلة سابقًا.",
                        SourceLocation(line_number, 1),
                    )

        index = indent
        while index < len(line):
            char = line[index]
            if char == " ":
                index += 1
                continue
            if char == "#":
                break

            location = SourceLocation(line_number, index + 1)
            if char == '"':
                start = index
                index += 1
                escaped = False
                while index < len(line):
                    current = line[index]
                    if current == '"' and not escaped:
                        index += 1
                        break
                    if current == "\\" and not escaped:
                        escaped = True
                    else:
                        escaped = False
                    index += 1
                else:
                    raise SudaError("نص غير مغلق؛ استخدم علامتي اقتباس مزدوجتين.", location)
                raw = line[start:index]
                try:
                    value = json.loads(raw)
                except json.JSONDecodeError as error:
                    raise SudaError(f"تهريب نصي غير صالح: {error.msg}.", location) from error
                try:
                    value.encode("utf-8")
                except UnicodeEncodeError as error:
                    raise SudaError("النص يحتوي محرف Unicode غير صالح.", location) from error
                tokens.append(Token("STRING", value, line_number, start + 1))
                continue

            number = _NUMBER.match(line, index)
            if number:
                raw = number.group()
                value = float(raw) if "." in raw else int(raw)
                tokens.append(Token("NUMBER", value, line_number, index + 1))
                index = number.end()
                continue

            identifier = _IDENTIFIER.match(line, index)
            if identifier:
                value = _canonical_word(identifier.group())
                tokens.append(Token("IDENT", value, line_number, index + 1))
                index = identifier.end()
                continue

            operator = next(
                (candidate for candidate in ("==", "!=", "<=", ">=", "//", "**", "->") if line.startswith(candidate, index)),
                None,
            )
            if operator is not None:
                tokens.append(Token("OP", operator, line_number, index + 1))
                index += len(operator)
                continue
            if char in "+-*/%=<>":
                tokens.append(Token("OP", char, line_number, index + 1))
                index += 1
                continue
            if char in "(),[]{}:.":
                if char in "([{":
                    delimiters.append((char, location))
                elif char in ")]}":
                    if not delimiters or delimiters[-1][0] != matching_delimiter[char]:
                        raise SudaError(f"قوس إغلاق غير متطابق: {char}.", location)
                    delimiters.pop()
                tokens.append(Token("PUNCT", char, line_number, index + 1))
                index += 1
                continue
            raise SudaError(f"رمز غير معروف: {char!r}.", location)

        if not delimiters:
            tokens.append(Token("NEWLINE", None, line_number, len(line) + 1))

    if delimiters:
        opening, location = delimiters[-1]
        raise SudaError(
            f"قوس غير مغلق: {opening}.",
            location,
        )
    while len(indentation) > 1:
        indentation.pop()
        tokens.append(Token("DEDENT", 0, max(1, len(lines)), 1))
    tokens.append(Token("EOF", None, max(1, len(lines)), 1))
    return tokens
