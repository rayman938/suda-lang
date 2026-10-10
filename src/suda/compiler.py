"""Public compiler entry points."""

from .bytecode import BytecodeProgram, compile_ast
from .errors import SudaError
from .lexer import tokenize
from .parser import parse


def compile_source(source: str) -> BytecodeProgram:
    """Compile Suda source to portable versioned bytecode."""
    try:
        return compile_ast(parse(tokenize(source)))
    except RecursionError as error:
        raise SudaError("تداخل التعابير أو الكتل أعمق من الحد الآمن للمترجم.") from error
