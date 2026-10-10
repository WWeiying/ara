#!/usr/bin/env python3
"""Bounded normal-input DIV repair regression; not a full IEEE signoff suite."""
import argparse
import csv
from fractions import Fraction
import hashlib
import json
from math import isqrt
from pathlib import Path
import shutil

import run_mvp_audit as audit


def oracle(a, b, width, rm):
    value = audit.finite_value(a, width) / audit.finite_value(b, width)
    negative = value < 0
    value = abs(value)
    fraction, exponent = (52, 11) if width == 64 else (23, 8)
    bias = (1 << (exponent - 1)) - 1
    power = value.numerator.bit_length() - value.denominator.bit_length()
    if value < Fraction(2) ** power:
        power -= 1
    if power < 1 - bias:
        raise ValueError("this suite intentionally excludes subnormal outputs")
    scaled = value / (Fraction(2) ** (power - fraction))
    significand, remainder = divmod(scaled.numerator, scaled.denominator)
    increment = (rm == 0 and (2 * remainder > scaled.denominator or
                             (2 * remainder == scaled.denominator and significand & 1)))
    increment |= rm == 4 and 2 * remainder >= scaled.denominator
    increment |= bool(remainder) and ((rm == 3 and not negative) or (rm == 2 and negative))
    significand += int(increment)
    if significand == 1 << (fraction + 1):
        significand >>= 1
        power += 1
    boxing = 0 if width == 64 else 0xffffffff00000000
    sign = int(negative) << (width - 1)
    infinity = ((1 << exponent) - 1) << fraction
    if power > bias:
        to_inf = rm in (0, 4) or (rm == 3 and not negative) or (rm == 2 and negative)
        return boxing | sign | (infinity if to_inf else infinity - 1), 5
    return boxing | sign | ((power + bias) << fraction) | (significand - (1 << fraction)), int(bool(remainder))


def cases():
    result = json.loads((audit.HERE / "cases.json").read_text())
    for width in (32, 64):
        fraction, exponent = (52, 11) if width == 64 else (23, 8)
        bias = (1 << (exponent - 1)) - 1
        box = 0 if width == 64 else 0xffffffff00000000
        one = box | (bias << fraction)
        pairs = [(one, one), (one + (1 << (fraction - 1)), one),
                 (one, one + (1 << (fraction - 1))), (one + 1, one + 1),
                 (one, one + (1 << fraction) + (1 << (fraction - 1))),
                 (box | ((((1 << exponent) - 1) << fraction) - 1), one - (1 << fraction))]
        for rm in range(5):
            for pair_index, (a, b) in enumerate(pairs):
                for negative in (False, True):
                    a_signed = a ^ (int(negative) << (width - 1))
                    expected, flags = oracle(a_signed, b, width, rm)
                    result.append(dict(name=f"fp{width}_pair{pair_index}_rm{rm}_neg{int(negative)}",
                                       format=width, rm=rm, a=f"{a_signed:016x}", b=f"{b:016x}",
                                       expected_result=f"{expected:016x}", expected_flags=f"{flags:02x}"))
    return result


def sqrt_cases():
    result = []
    for width in (32, 64):
        fraction, exponent = (52, 11) if width == 64 else (23, 8)
        bias = (1 << (exponent - 1)) - 1
        box = 0 if width == 64 else 0xffffffff00000000
        one = box | (bias << fraction)
        for power, mantissa in ((0, 0), (2, 0), (3, 1 << (fraction - 3)),
                                (1, 0), (1, 1 << (fraction - 1))):
            a = box | ((bias + power) << fraction) | mantissa
            x = audit.finite_value(a, width)
            output_power = power // 2
            squared = x / (Fraction(2) ** (2 * (output_power - fraction)))
            q = isqrt(squared.numerator // squared.denominator)
            exact = q * q * squared.denominator == squared.numerator
            midpoint = 4 * squared.numerator - (2 * q + 1) ** 2 * squared.denominator
            for rm in range(5):
                increment = ((rm == 0 and (midpoint > 0 or (midpoint == 0 and q & 1))) or
                             (rm == 4 and midpoint >= 0) or (rm == 3 and not exact))
                rounded = q + int(increment)
                expected = box | ((bias + output_power) << fraction) | (rounded - (1 << fraction))
                result.append(dict(name=f"sqrt_fp{width}_pow{power}_mant{mantissa}_rm{rm}",
                                   format=width, rm=rm, a=f"{a:016x}", b=f"{one:016x}",
                                   expected_result=f"{expected:016x}", expected_flags=f"{int(not exact):02x}",
                                   sqrt=True))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    inputs = output / "inputs"
    hashes = {}
    for relative in audit.SOURCES + (audit.HEADER,):
        source = audit.ORIGINAL / relative
        target = inputs / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        hashes[relative] = hashlib.sha256(source.read_bytes()).hexdigest()
    suite = cases() + sqrt_cases()
    audit_dir = inputs / "audit"
    audit_dir.mkdir()
    bench = (audit.HERE / "mvp_audit_tb.sv").read_text()
    bench = bench.replace("wire fire = div_start && ready", "wire fire = (div_start || sqrt_start) && ready")
    bench = bench.replace("input logic [4:0] oracle_flags", "input logic [4:0] oracle_flags, input bit sqrt_op")
    bench = bench.replace("div_start = 1;", "div_start = !sqrt_op; sqrt_start = sqrt_op;")
    bench = bench.replace("div_start = 0;\n\n    latency", "div_start = 0; sqrt_start = 0;\n\n    latency")
    bench = bench.replace("div_enable !== 1'b1", "div_enable !== !sqrt_op")
    bench = bench.replace("accepted != 8 || completed != 8", f"accepted != {len(suite)} || completed != {len(suite)}")
    bench = bench.replace("AUDIT_COMPLETE cases=8", f"AUDIT_COMPLETE cases={len(suite)}")
    bench = bench.replace("#6000;", f"#{(len(suite) + 1) * 800};")
    (audit_dir / "mvp_audit_tb.sv").write_text(bench)
    (audit_dir / "cases.svh").write_text("\n".join(
        f'run_case({i}, "{c["name"]}", 2\'d{int(c["format"] == 64)}, 3\'d{c["rm"]}, '
        f'64\'h{c["a"]}, 64\'h{c["b"]}, 64\'h{c["expected_result"]}, 5\'h{c["expected_flags"]}, 1\'b{int(c.get("sqrt", False))});'
        for i, c in enumerate(suite)) + "\n")
    audit.save_json(output / "inputs.json", hashes)
    audit.save_json(output / "cases.json", suite)
    command = [shutil.which("vcs"), "-full64", "-sverilog", "-timescale=1ns/1ps",
               f"+incdir+{inputs / 'common_cells/include'}", f"+incdir+{audit_dir}",
               *[str(inputs / relative) for relative in audit.SOURCES],
               str(audit_dir / "mvp_audit_tb.sv"), "-top", "mvp_audit_tb", "-o", "simv", "-l", "compile.log"]
    compile_result = audit.execute(command, output / "build", 180)
    report = dict(compile=compile_result, status="COMPILE_ERROR", case_count=len(suite))
    if compile_result["status"] == "COMPLETED":
        report["run"] = audit.execute([output / "build/simv", "-l", "run.log"], output / "sim", 30)
        rows = list(csv.DictReader((output / "sim/results.csv").open()))
        failures = [row for row in rows if row["oracle_match"] != "1"]
        complete = f"AUDIT_COMPLETE cases={len(suite)} accepted={len(suite)} completed={len(suite)} pending=0"
        log = (output / "sim/console.log").read_text()
        valid = report["run"]["status"] == "COMPLETED" and complete in log and not audit.SIM_ERROR.search(log)
        valid &= len(rows) == len(suite) and [row["name"] for row in rows] == [c["name"] for c in suite]
        report.update(status="PASS" if valid and not failures else "FAIL", failures=failures,
                      completed_cases=len(rows), latencies=sorted({int(row["latency"]) for row in rows}))
    report["sources_unchanged"] = all(hashlib.sha256((audit.ORIGINAL / rel).read_bytes()).hexdigest() == digest
                                      for rel, digest in hashes.items())
    audit.save_json(output / "summary.json", report)
    print(json.dumps(report, indent=2))
    return int(report["status"] != "PASS" or not report["sources_unchanged"])


if __name__ == "__main__":
    raise SystemExit(main())
