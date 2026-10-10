"""Recursive-descent statement parser and Pratt expression parser."""

from __future__ import annotations

from dataclasses import dataclass, field

from .errors import SourceLocation, SudaError
from .lexer import Token


@dataclass
class Node:
    kind: str
    value: object = None
    children: list["Node"] = field(default_factory=list)
    line: int = 1


_PRECEDENCE = {
    "أو": 1,
    "و": 2,
    "==": 3,
    "!=": 3,
    "<": 3,
    "<=": 3,
    ">": 3,
    ">=": 3,
    "+": 4,
    "-": 4,
    "*": 5,
    "/": 5,
    "//": 5,
    "%": 5,
    "**": 6,
}


class Parser:
    def __init__(self, tokens: list[Token]):
        self.tokens = tokens
        self.index = 0

    @property
    def current(self) -> Token:
        return self.tokens[self.index]

    def _advance(self) -> Token:
        token = self.current
        if token.kind != "EOF":
            self.index += 1
        return token

    def _is(self, value: object) -> bool:
        return self.current.value == value

    def _match(self, value: object) -> bool:
        if self._is(value):
            self._advance()
            return True
        return False

    def _expect(self, value: object, description: str | None = None) -> Token:
        if not self._is(value):
            expected = description or repr(value)
            raise self._error(f"متوقع {expected}.")
        return self._advance()

    def _expect_kind(self, kind: str, description: str) -> Token:
        if self.current.kind != kind:
            raise self._error(f"متوقع {description}.")
        return self._advance()

    def _error(self, message: str) -> SudaError:
        return SudaError(message, SourceLocation(self.current.line, self.current.column))

    def parse(self) -> Node:
        statements: list[Node] = []
        while self.current.kind != "EOF":
            if self.current.kind == "NEWLINE":
                self._advance()
                continue
            if self.current.kind == "DEDENT":
                raise self._error("مسافة بادئة غير متوقعة.")
            statements.append(self._statement())
        return Node("program", children=statements, line=1)

    def _statement(self) -> Node:
        token = self.current
        if token.kind == "IDENT":
            if token.value == "إذا":
                return self._if_statement()
            if token.value == "طالما":
                return self._while_statement()
            if token.value == "لكل":
                return self._for_statement()
            if token.value in ("اكسر", "استمر"):
                self._advance()
                self._line_end()
                return Node("loop_control", token.value, line=token.line)
            if token.value == "دالة":
                return self._function_statement()
            if token.value == "أرجع":
                self._advance()
                value = self._expression()
                self._line_end()
                return Node("return", children=[value], line=token.line)
            if token.value == "ثابت":
                self._advance()
                name = self._expect_kind("IDENT", "اسم الثابت")
                self._expect("=")
                value = self._expression()
                self._line_end()
                return Node("const", name.value, [value], token.line)
        target = self._expression()
        if self._match("="):
            if target.kind == "name":
                value = self._expression()
                self._line_end()
                return Node("assign", target.value, [value], target.line)
            if target.kind == "index":
                value = self._expression()
                self._line_end()
                return Node("assign_index", children=[*target.children, value], line=target.line)
            raise SudaError("الجهة اليسرى للإسناد يجب أن تكون اسمًا أو عنصرًا مفهرسًا.", SourceLocation(target.line))
        self._line_end()
        return Node("expression_statement", children=[target], line=token.line)

    def _line_end(self) -> None:
        if self.current.kind != "NEWLINE":
            raise self._error("نهاية السطر متوقعة.")
        self._advance()

    def _block(self) -> list[Node]:
        self._expect(":")
        self._line_end()
        if self.current.kind != "INDENT":
            raise self._error("تحتاج هذه العبارة إلى كتلة بمسافة بادئة.")
        self._advance()
        statements: list[Node] = []
        while self.current.kind not in ("DEDENT", "EOF"):
            if self.current.kind == "NEWLINE":
                self._advance()
                continue
            statements.append(self._statement())
        if self.current.kind != "DEDENT":
            raise self._error("كتلة غير مكتملة.")
        self._advance()
        return statements

    def _if_statement(self) -> Node:
        token = self._advance()
        condition = self._expression()
        then_branch = Node("block", children=self._block(), line=token.line)
        else_branch = Node("block", children=[], line=token.line)
        if self.current.kind == "IDENT" and self._is("وإلا"):
            self._advance()
            if self.current.kind == "IDENT" and self._is("إذا"):
                nested = self._if_statement()
                else_branch.children.append(nested)
            else:
                else_branch.children = self._block()
        return Node("if", children=[condition, then_branch, else_branch], line=token.line)

    def _while_statement(self) -> Node:
        token = self._advance()
        condition = self._expression()
        body = Node("block", children=self._block(), line=token.line)
        return Node("while", children=[condition, body], line=token.line)

    def _for_statement(self) -> Node:
        token = self._advance()
        name = self._expect_kind("IDENT", "اسم متغير الحلقة")
        self._expect("في", "الكلمة «في»")
        iterable = self._expression()
        body = Node("block", children=self._block(), line=token.line)
        return Node("for", name.value, [iterable, body], token.line)

    def _function_statement(self) -> Node:
        token = self._advance()
        name = self._expect_kind("IDENT", "اسم الدالة")
        self._expect("(")
        parameters: list[str] = []
        if not self._is(")"):
            while True:
                parameters.append(str(self._expect_kind("IDENT", "اسم وسيط").value))
                if not self._match(","):
                    break
                if self._is(")"):
                    break
        self._expect(")")
        body = Node("block", children=self._block(), line=token.line)
        if len(parameters) != len(set(parameters)):
            raise self._error("لا يجوز تكرار اسم الوسيط في تعريف الدالة.")
        return Node("function", name.value, [Node("parameters", parameters), body], token.line)

    def _expression(self, minimum_precedence: int = 0) -> Node:
        left = self._prefix()
        comparison_seen = False
        while True:
            if self._is("("):
                left = self._call(left)
                continue
            if self._is("["):
                token = self._advance()
                index = self._expression()
                self._expect("]")
                left = Node("index", children=[left, index], line=token.line)
                continue
            operator = str(self.current.value)
            precedence = _PRECEDENCE.get(operator)
            if precedence is None or precedence < minimum_precedence:
                break
            if precedence == 3:
                if comparison_seen:
                    raise self._error("المقارنات المتسلسلة غير مدعومة؛ استخدم العامل «و».")
                comparison_seen = True
            token = self._advance()
            next_minimum = precedence if operator == "**" else precedence + 1
            right = self._expression(next_minimum)
            left = Node("binary", operator, [left, right], token.line)
        return left

    def _prefix(self) -> Node:
        token = self._advance()
        if token.kind in ("NUMBER", "STRING"):
            return Node("literal", token.value, line=token.line)
        if token.kind == "IDENT":
            if token.value == "صحيح":
                return Node("literal", True, line=token.line)
            if token.value == "خطأ":
                return Node("literal", False, line=token.line)
            if token.value == "لا_شيء":
                return Node("literal", None, line=token.line)
            if token.value in ("ليس",):
                return Node("unary", "ليس", [self._expression(6)], token.line)
            return Node("name", token.value, line=token.line)
        if token.value in ("-", "+"):
            return Node("unary", token.value, [self._expression(6)], token.line)
        if token.value == "(":
            expression = self._expression()
            self._expect(")")
            return expression
        if token.value == "[":
            elements: list[Node] = []
            if not self._is("]"):
                while True:
                    elements.append(self._expression())
                    if not self._match(","):
                        break
                    if self._is("]"):
                        break
            self._expect("]")
            return Node("list", children=elements, line=token.line)
        if token.value == "{":
            entries: list[Node] = []
            if not self._is("}"):
                while True:
                    key = self._expression()
                    self._expect(":", "النقطتين بين مفتاح وقيمة القاموس")
                    value = self._expression()
                    entries.extend((key, value))
                    if not self._match(","):
                        break
                    if self._is("}"):
                        break
            self._expect("}")
            return Node("dict", children=entries, line=token.line)
        raise SudaError("بداية تعبير غير صالحة.", SourceLocation(token.line, token.column))

    def _call(self, callee: Node) -> Node:
        token = self._advance()
        arguments: list[Node] = []
        if not self._is(")"):
            while True:
                arguments.append(self._expression())
                if not self._match(","):
                    break
                if self._is(")"):
                    break
        self._expect(")")
        return Node("call", children=[callee, *arguments], line=token.line)


def parse(tokens: list[Token]) -> Node:
    return Parser(tokens).parse()
