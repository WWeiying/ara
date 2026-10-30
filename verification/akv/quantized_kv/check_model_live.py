"""Strict functional-log acceptance for model_live/test.cpp, not timing evidence.

Only normal boot/GGML chatter is ignored. Reserved protocol namespaces are
recognized anywhere in a line, then parsed by full match in execution order.
This checks guest evidence, not model identity, source pins, or RTL performance;
the enclosing runner must establish those independently.
"""

import argparse
import json
import math
from pathlib import Path
import re
import sys


SUITE = ("QUANT_MODEL_SUITE_PASS profiles=2 generations=4 tokens_each=3 "
         "common_greedy_trajectory=1 performance=not_measured")
UINT = r"(?:0|[1-9][0-9]{0,19})"
FLOAT = r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?"
RESERVED = ("QUANT_MODEL", "GGML_RISCV_QUANT_KV", "GGML_RISCV_QBS_EXEC",
            "GUEST_TEST_EXIT")
FAILURE = re.compile(
    r"QUANT_MODEL_FAIL|Assertion[^\r\n]*failed|assertion[^\r\n]*failed|"
    r"GGML_ASSERT|terminate called|Segmentation fault|Illegal instruction|"
    r"Kernel panic|Aborted \(core dumped\)")
KV_FIELDS = ("status", "mapping", "memory", "runtime_called", "command_attempts",
             "groups", "value_decodes", "executor_status")
QBS_FIELDS = (
    "gemv_calls", "gemm_calls", "input_rows", "output_rows", "activation_elements",
    "output_elements", "dot_elements", "split_calls", "commands_m1", "commands_m2",
    "commands_m3", "commands_m4", "commands_m5", "commands_m6", "commands_m7",
    "commands_m8", "native_qbexec", "emulated_commands", "command_dot_elements",
    "segmented_commands", "context_fill", "context_reuse", "context_release")
QBS_TYPES = ("Q3_K", "Q4_K", "Q5_K", "Q6_K", "Q8_0", "Q4_0", "Q2_K",
             "Q5_0", "IQ4_NL")
KV_PATTERN = "GGML_RISCV_QUANT_KV " + " ".join(
    f"{key}=(?P<{key}>{UINT})" for key in KV_FIELDS)
QBS_PATTERN = ("GGML_RISCV_QBS_EXEC type=(?P<type>" + "|".join(QBS_TYPES) + ") "
               + " ".join(f"{key}=(?P<{key}>{UINT})" for key in QBS_FIELDS))


def require(condition, message):
    if not condition:
        raise ValueError(message)


class Records:
    def __init__(self, text):
        require(not FAILURE.search(text), "failure text in guest log")
        # Accept UART CRLF or LF, not splitlines()'s extra control separators.
        self.lines = [(number, line) for number, line in enumerate(re.split(r"\r?\n", text), 1)
                      if any(prefix in line for prefix in RESERVED)]
        self.position = 0

    def peek(self):
        return self.lines[self.position][1] if self.position < len(self.lines) else ""

    def take(self, pattern):
        require(self.position < len(self.lines), "missing protocol record: " + pattern)
        number, line = self.lines[self.position]
        match = re.fullmatch(pattern, line, flags=re.ASCII)
        require(match is not None, f"unexpected/malformed record at line {number}: {line}")
        self.position += 1
        return match.groupdict()


def unsigned_fields(record, fields):
    values = {key: int(record[key]) for key in fields}
    require(all(value <= (1 << 64) - 1 for value in values.values()),
            "counter exceeds uint64")
    return values


def check_log(text):
    records = Records(text)
    prompt_tokens = None
    vocabulary = None
    generations = []
    comparisons = []
    native_calls = attempts = prefill_reports = 0
    for kind in ("q8_0", "q4_0"):
        paired = []
        for mode in ("baseline", "candidate"):
            begin = records.take(
                f"QUANT_MODEL_BEGIN kind={kind} mode={mode} layers=28 "
                f"prompt_tokens=(?P<prompt>{UINT}) generated=3 context=128 threads=1")
            prompt = int(begin["prompt"])
            require(1 < prompt <= 32, "prompt_tokens outside 2..32")
            if prompt_tokens is None:
                prompt_tokens = prompt
            require(prompt == prompt_tokens, "prompt_tokens changed between generations")
            tokens, pieces = [], []
            for step in range(3):
                reports = []
                while "GGML_RISCV_QUANT_KV" in records.peek():
                    reports.append(unsigned_fields(records.take(KV_PATTERN), KV_FIELDS))
                    require(len(reports) <= 28, "extra layer report")
                if mode == "baseline":
                    require(not reports, "baseline emitted quantized-KV dispatch records")
                elif step == 0:
                    # Prefill may bypass the hook, or reject all 28 layers by shape.
                    require(len(reports) in (0, 28), "partial prefill fallback evidence")
                    expected = dict(zip(KV_FIELDS, (1, 5, 0, 0, 0, 0, 0, 0)))
                    require(all(report == expected for report in reports),
                            "unexpected prefill dispatch")
                    prefill_reports += len(reports)
                else:
                    require(len(reports) == 28, "decode must dispatch all 28 layers")
                    expected = dict(zip(KV_FIELDS, (0, 0, 1, 1, 4, 2,
                                                    2 * (prompt + step), 0)))
                    require(all(report == expected for report in reports),
                            "decode fallback or wrong native work")
                    native_calls += len(reports)
                    attempts += sum(report["command_attempts"] for report in reports)
                token = records.take(
                    f"QUANT_MODEL_TOKEN kind={kind} mode={mode} step={step} "
                    f"token=(?P<token>{UINT}) piece_hex=(?P<piece>[0-9a-f]{{0,1024}})")
                require(len(token["piece"]) % 2 == 0, "odd-length piece_hex")
                tokens.append(int(token["token"]))
                pieces.append(token["piece"])
            end = records.take(f"QUANT_MODEL_END kind={kind} mode={mode} "
                               f"generated=3 vocab=(?P<vocab>{UINT})")
            vocab = int(end["vocab"])
            require(1 < vocab <= (1 << 31) - 1, "invalid vocabulary size")
            require(all(token < vocab for token in tokens), "token outside vocabulary")
            if vocabulary is None:
                vocabulary = vocab
            require(vocab == vocabulary, "vocabulary changed between generations")
            generation = {"kind": kind, "mode": mode, "tokens": tokens,
                          "piece_hex": pieces}
            paired.append(generation)
            generations.append(generation)
        require(paired[0]["tokens"] == paired[1]["tokens"],
                "baseline/candidate greedy token IDs differ")
        require(paired[0]["piece_hex"] == paired[1]["piece_hex"],
                "same token IDs have inconsistent pieces")
        for step in range(3):
            compare = records.take(
                f"QUANT_MODEL_COMPARE kind={kind} step={step} common_prefix=1 "
                f"top1_equal=1 max_abs=(?P<max_abs>{FLOAT}) "
                f"rmse=(?P<rmse>{FLOAT}) kl=(?P<kl>{FLOAT})")
            metrics = {key: float(value) for key, value in compare.items()}
            require(all(math.isfinite(value) for value in metrics.values()),
                    "nonfinite comparison metric")
            require(metrics["max_abs"] >= 0 and metrics["rmse"] >= 0
                    and metrics["kl"] >= -1e-8, "invalid comparison metric")
            comparisons.append({"kind": kind, "step": step, **metrics})
    records.take(re.escape(SUITE))
    projections = {}
    while "GGML_RISCV_QBS_EXEC" in records.peek():
        record = records.take(QBS_PATTERN)
        kind = record["type"]
        require(kind not in projections, "duplicate projection summary type")
        counters = unsigned_fields(record, QBS_FIELDS)
        require(counters["emulated_commands"] == 0, "projection emulation occurred")
        require(counters["gemv_calls"] + counters["gemm_calls"] > 0,
                "projection summary without operations")
        projections[kind] = counters
    for kind in ("Q4_K", "Q6_K"):
        require(kind in projections and projections[kind]["native_qbexec"] > 0,
                f"missing positive native {kind} projection evidence")
    records.take("GUEST_TEST_EXIT=0")
    require(records.position == len(records.lines), "extra protocol records after guest exit")
    require(native_calls == 112 and attempts == 448, "incorrect native dispatch totals")
    return {"status": "PASS", "profiles": 2, "generations": generations,
            "prompt_tokens": prompt_tokens, "vocab": vocabulary,
            "native_calls": native_calls, "native_command_attempts": attempts,
            "prefill_fallback_reports": prefill_reports, "comparisons": comparisons,
            "projection_summaries": projections, "whole_model": True,
            "rtl_performance": False, "performance": "not_measured"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = check_log(args.log.read_bytes().decode("utf-8", errors="strict"))
    except (OSError, UnicodeError, ValueError) as error:
        print(f"model live check failed: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
