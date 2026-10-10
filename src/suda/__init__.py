"""Arabic-first Suda language implementation."""

from .compiler import compile_source
from .errors import SudaError
from .vm import VirtualMachine, run_source

__all__ = ["SudaError", "VirtualMachine", "compile_source", "run_source"]
__version__ = "0.4.0"
