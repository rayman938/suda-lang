"""Bounded source execution shared by the desktop interfaces."""

from __future__ import annotations

from dataclasses import dataclass

from ..compiler import compile_source
from ..errors import SudaError
from ..vm import VirtualMachine


@dataclass(frozen=True)
class RunResult:
    output: str
    error: str | None
    steps: int


def run_editor_source(source: str) -> RunResult:
    machine = VirtualMachine(
        step_limit=200_000,
        recursion_limit=64,
        collection_limit=10_000,
        output_limit_bytes=250_000,
    )
    try:
        machine.run(compile_source(source))
    except SudaError as error:
        return RunResult("", str(error), machine.steps)
    return RunResult("\n".join(machine.output_lines), None, machine.steps)
