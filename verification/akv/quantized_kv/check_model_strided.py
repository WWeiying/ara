"""Successor model-log checker: real strided cache admission, never timing proof."""

import argparse
import json
from pathlib import Path
import re

from check_model_live import KV_PATTERN, UINT, check_log as check_original, require


# core 4352 + maximum Q8_0 panel 8704 + four uint32 tags, rounded to 64.
WORKSPACE_BYTES = 13120
LAYOUT_PREFIX = "GGML_RISCV_QUANT_KV_LAYOUT"
LAYOUT_PATTERN = LAYOUT_PREFIX + " " + " ".join(
    f"{field}=(?P<{field}>{UINT})" for field in
    ("selection", "key_panels", "key_bytes", "workspace", "k_token_stride", "k_head_stride"))
CONTEXT_PATTERN = r"llama_context: n_ctx[ \t]+=[ \t]+(?P<context>[0-9]+)"


def check_log(text):
    lines = re.split(r"\r?\n", text)
    layouts = {}
    for index, line in enumerate(lines):
        if LAYOUT_PREFIX in line:
            match = re.fullmatch(LAYOUT_PATTERN, line, flags=re.ASCII)
            require(match is not None, f"malformed layout at line {index + 1}")
            require(index > 0 and re.fullmatch(KV_PATTERN, lines[index - 1], flags=re.ASCII),
                    "layout must immediately follow its native/fallback report")
            layouts[index] = {key: int(value) for key, value in match.groupdict().items()}
    # Strip only already validated layout records. Everything else, including
    # malformed/unknown original protocol records, remains visible to the parent checker.
    checked = check_original("\n".join(line for index, line in enumerate(lines) if index not in layouts))
    require(checked["prompt_tokens"] == 4, "fixed model prompt must yield four tokens")
    kind = mode = None
    step = 0
    contexts = []
    context_pending = False
    panels = copied = native_layouts = used_layouts = 0
    for index, line in enumerate(lines):
        if re.search(r"llama_context: n_ctx(?:\s|=|$)", line, flags=re.ASCII):
            match = re.fullmatch(CONTEXT_PATTERN, line, flags=re.ASCII)
            require(match is not None and int(match["context"]) == 256,
                    "effective model context must be exactly 256")
            require(not context_pending, "extra context initialization")
            contexts.append(256)
            context_pending = True
        begin = re.fullmatch(r"QUANT_MODEL_BEGIN kind=(q8_0|q4_0) mode=(baseline|candidate) .+", line)
        if begin:
            require(context_pending, "missing effective context before generation")
            context_pending = False
            kind, mode = begin.groups()
            step = 0
        token = re.fullmatch(r"QUANT_MODEL_TOKEN kind=\S+ mode=\S+ step=([0-2]) .+", line)
        if token:
            step = int(token[1]) + 1
        if re.fullmatch(KV_PATTERN, line, flags=re.ASCII):
            require(mode == "candidate" and step in (0, 1, 2), "layout outside candidate decode")
            require(index + 1 in layouts, "missing adjacent layout report")
            layout = layouts[index + 1]
            row_bytes = 136 if kind == "q8_0" else 72
            expected = dict(selection=0, key_panels=0 if step == 0 else 2,
                            key_bytes=0 if step == 0 else 2 * (4 + step) * row_bytes,
                            workspace=WORKSPACE_BYTES, k_token_stride=2 * row_bytes,
                            k_head_stride=row_bytes)
            require(layout == expected, f"wrong strided work/layout: {kind} step={step}: {layout}")
            used_layouts += 1
            if step:
                native_layouts += 1
                panels += layout["key_panels"]
                copied += layout["key_bytes"]
    require(contexts == [256] * 4 and not context_pending, "wrong effective context count/order")
    require(used_layouts == len(layouts) and native_layouts == 112,
            "extra or missing layout records")
    require(panels == 224 and copied == 128128, "wrong total panel copy work")
    checked.update(effective_contexts=contexts, requested_context=128,
                   native_layout_reports=native_layouts, key_panels=panels,
                   key_bytes=copied, workspace_bytes=WORKSPACE_BYTES)
    return checked


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(check_log(args.log.read_bytes().decode("utf-8")),
                     indent=2, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()
