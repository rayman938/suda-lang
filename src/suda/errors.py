"""Source-aware diagnostics shared by the compiler and virtual machine."""

from dataclasses import dataclass


@dataclass(frozen=True)
class SourceLocation:
    line: int
    column: int = 1


class SudaError(Exception):
    """An expected, user-facing language error."""

    def __init__(self, message: str, location: SourceLocation | None = None):
        super().__init__(message)
        self.message = message
        self.location = location

    def __str__(self) -> str:
        if self.location is None:
            return self.message
        return f"السطر {self.location.line}:{self.location.column}: {self.message}"
