#!/usr/bin/env python3
"""Select the existing package manifest's ordered FPU dependencies."""
import json
from pathlib import Path
import sys

root = Path(sys.argv[1])
for name in json.loads((root / "manifest.json").read_text())["files"]:
    if (name.startswith(("rtl/fpnew/", "rtl/fpu_div_sqrt_mvp/"))
            and not name.endswith("fpnew_pkg.sv")) or name in (
                "rtl/common_cells/src/rr_arb_tree.sv",
                "rtl/common_cells/src/fifo_v3.sv",
            ):
        print((root / name).as_posix())
