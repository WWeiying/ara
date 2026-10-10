"""Admit the all-lane FP32 exponent scan without changing sealed admissions."""
from pathlib import Path

import admit_fp64_scan as admission


# The shared implementation pins its own source; also pin this case definition.
original_sha = admission.sha
wrapper = Path(__file__).resolve()
wrapper_sha = original_sha(wrapper)


def checked_sha(path):
    admission.require(original_sha(wrapper) == wrapper_sha, "Gap91 admission source drift")
    return original_sha(path)


admission.sha = checked_sha
admission.SPECS = {
    "gap91": dict(stem="gap91-div32-exp-lanes", base="gap90-offline-admitted-697",
                  count=697, instructions=60, bytes=15360, checks=1320,
                  signature=0x80002308),
}
# Include this definition in the evidence accumulated by the shared driver.
admission.__file__ = str(wrapper)

if __name__ == "__main__":
    admission.main()
