"""Strict admission for the source-pinned all-lane FP16 leading scan."""
from pathlib import Path

import admit_fp64_scan as admission


original_sha = admission.sha
wrapper = Path(__file__).resolve()
wrapper_sha = original_sha(wrapper)
shared_source = Path(admission.__file__).resolve()
shared_sha = original_sha(shared_source)
original_save = admission.save


def checked_sha(path):
    admission.require(original_sha(wrapper) == wrapper_sha, "Gap93 admission source drift")
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
    "gap93": dict(stem="gap93-div16-leading", base="gap92-offline-admitted-699",
                  count=699, instructions=24, bytes=1536, checks=272,
                  signature=0x80002308),
}

if __name__ == "__main__":
    admission.main()
