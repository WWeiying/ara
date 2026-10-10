"""Strict complete FP32 pack scan admission against the admitted704 union."""
from pathlib import Path

import admit_fp64_scan as admission


original_sha = admission.sha
wrapper = Path(__file__).resolve()
wrapper_sha = original_sha(wrapper)
shared_source = Path(admission.__file__).resolve()
shared_sha = original_sha(shared_source)
original_save = admission.save


def checked_sha(path):
    admission.require(original_sha(wrapper) == wrapper_sha, "Gap96 admission source drift")
    admission.require(original_sha(shared_source) == shared_sha, "Shared admission source drift")
    return original_sha(path)


def save_with_definition(path, value):
    if path.name == "evidence-pins.json":
        value = dict(value)
        value[str(wrapper)] = wrapper_sha
    original_save(path, value)


admission.sha = checked_sha
admission.save = save_with_definition
admission.SPECS = {
    "gap96": dict(stem="gap96-div32-pack", base="gap95-offline-admitted",
                  count=704, instructions=42, bytes=10752, checks=2758,
                  signature=0x80002288),
}


if __name__ == "__main__":
    admission.main()
