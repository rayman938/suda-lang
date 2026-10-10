"""Reproducible Suda VM versus equivalent Python loop benchmark."""

from __future__ import annotations

import argparse
import json
import platform
import statistics
import sys
import time
import tracemalloc
import zlib
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from suda.bytecode import BytecodeProgram, COMPRESSED_BYTECODE_MAGIC  # noqa: E402
from suda.compiler import compile_source  # noqa: E402
from suda.vm import VirtualMachine  # noqa: E402


def positive_int(raw: str) -> int:
    try:
        value = int(raw)
    except ValueError as error:
        raise argparse.ArgumentTypeError("أدخل عددًا صحيحًا موجبًا.") from error
    if value <= 0:
        raise argparse.ArgumentTypeError("أدخل عددًا أكبر من صفر.")
    return value


def python_sum(count: int) -> int:
    total = 0
    for value in range(count):
        total += value
    return total


def summarize(samples: list[float]) -> dict[str, float]:
    ordered = sorted(samples)
    p95_index = max(0, (95 * len(ordered) + 99) // 100 - 1)
    return {
        "median_seconds": statistics.median(ordered),
        "mean_seconds": statistics.mean(ordered),
        "stdev_seconds": statistics.stdev(ordered) if len(ordered) > 1 else 0.0,
        "p95_seconds": ordered[p95_index],
    }


def measure_peak_memory(operation: Callable[[], object]) -> int:
    tracemalloc.start()
    try:
        operation()
        _, peak = tracemalloc.get_traced_memory()
        return peak
    finally:
        tracemalloc.stop()


def main() -> int:
    parser = argparse.ArgumentParser(description="قياس قابل لإعادة التشغيل لمفسر سُدى")
    parser.add_argument("--items", type=positive_int, default=1_000)
    parser.add_argument("--rounds", type=positive_int, default=15)
    parser.add_argument("--warmup", type=positive_int, default=3)
    arguments = parser.parse_args()

    source = (
        f"مجموع = 0\n"
        f"لكل قيمة في مدى({arguments.items}):\n"
        f"    مجموع = مجموع + قيمة\n"
        f"اطبع(مجموع)\n"
    )
    compile_start = time.perf_counter()
    program = compile_source(source)
    compile_seconds = time.perf_counter() - compile_start
    bytecode_json = program.to_json().encode("utf-8")
    compressed_bytecode = zlib.compress(bytecode_json, level=9)
    if zlib.decompress(compressed_bytecode) != bytecode_json:
        raise RuntimeError("فك ضغط bytecode لم يُعد الملف الأصلي.")
    if BytecodeProgram.from_json(bytecode_json.decode("utf-8")) != program:
        raise RuntimeError("إعادة قراءة bytecode لم تُعد البرنامج الأصلي.")
    expected = arguments.items * (arguments.items - 1) // 2
    step_limit = max(10_000, arguments.items * 8 + 100)

    def run_suda() -> int:
        machine = VirtualMachine(step_limit=step_limit)
        machine.run(program)
        if machine.output_lines != [str(expected)]:
            raise RuntimeError("ناتج سُدى لا يطابق الناتج المتوقع.")
        return expected

    def run_python() -> int:
        result = python_sum(arguments.items)
        if result != expected:
            raise RuntimeError("ناتج Python لا يطابق الناتج المتوقع.")
        return result

    for _ in range(arguments.warmup):
        run_suda()
        run_python()

    suda_samples: list[float] = []
    python_samples: list[float] = []
    for _ in range(arguments.rounds):
        start = time.perf_counter()
        run_suda()
        suda_samples.append(time.perf_counter() - start)

        start = time.perf_counter()
        run_python()
        python_samples.append(time.perf_counter() - start)

    suda_peak = measure_peak_memory(run_suda)
    python_peak = measure_peak_memory(run_python)
    compression_samples: list[float] = []
    decompression_samples: list[float] = []
    for _ in range(arguments.rounds):
        start = time.perf_counter()
        zlib.compress(bytecode_json, level=9)
        compression_samples.append(time.perf_counter() - start)

        start = time.perf_counter()
        zlib.decompress(compressed_bytecode)
        decompression_samples.append(time.perf_counter() - start)
    compressed_file_bytes = len(COMPRESSED_BYTECODE_MAGIC) + len(compressed_bytecode)
    report = {
        "benchmark": "loop_sum_same_algorithm",
        "items": arguments.items,
        "rounds": arguments.rounds,
        "warmup": arguments.warmup,
        "result_verified": expected,
        "environment": {
            "python": platform.python_version(),
            "implementation": platform.python_implementation(),
            "system": platform.platform(),
            "machine": platform.machine(),
        },
        "suda": {
            **summarize(suda_samples),
            "peak_traced_bytes_one_run": suda_peak,
        },
        "python": {
            **summarize(python_samples),
            "peak_traced_bytes_one_run": python_peak,
        },
        "bytecode_compression": {
            "algorithm": "zlib level 9",
            "json_bytes": len(bytecode_json),
            "compressed_container_bytes": compressed_file_bytes,
            "bytes_saved": len(bytecode_json) - compressed_file_bytes,
            "percent_saved": round(
                (1 - compressed_file_bytes / len(bytecode_json)) * 100,
                2,
            ),
            "compression": summarize(compression_samples),
            "decompression": summarize(decompression_samples),
        },
        "compile_seconds_excluded_from_steady_state": compile_seconds,
        "limitations": [
            "This measures the Python-hosted Suda VM, not native compiled code.",
            "tracemalloc does not account for all process or operating-system memory.",
            "Compression size and timing apply only to this benchmark program.",
            "Power and thermal measurements are not collected by this script.",
        ],
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
