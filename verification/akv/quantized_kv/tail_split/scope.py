"""Exact successor source transformation; no numerical or diagnostic reductions."""
from pathlib import Path

HERE = Path(__file__).resolve().parent
PARENT = HERE.parent
ROOT = HERE.parents[3]


def command_count(visible):
    if type(visible) is not int or visible not in (5, 33):
        raise ValueError("Only the original visible5/33 scope is allowed")
    return 4 * ((visible + 31) // 32)


def suite(visible):
    command_count(visible)
    return (f"QUANT_TAIL_SPLIT_SUITE_PASS visible={visible} prefixes=1 trials=3 "
            "outputs=768 native_calls=2")


def render(source, visible):
    command_count(visible)
    replacements = (
        ("prefixes=5,33 native_repeats=2", f"prefixes={visible} native_repeats=2"),
        ("const unsigned prefixes[] = {5, 33};", f"const unsigned prefixes[] = {{{visible}}};"),
        ("prefix < 2; ++prefix", "prefix < 1; ++prefix"),
        ("const float *golden = prefix ? attention_tail_gold_33 : attention_tail_gold_5;",
         "const float *golden = visible_tokens == 33 ? attention_tail_gold_33 : attention_tail_gold_5;"),
        ("QUANT_TAIL_SUITE_PASS prefixes=2 trials=6 outputs=768 native_calls=4", suite(visible)),
    )
    for before, after in replacements:
        if source.count(before) != 1:
            raise ValueError("Predecessor source anchor changed: " + before)
        source = source.replace(before, after)
    return source

