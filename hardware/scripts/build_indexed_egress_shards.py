#!/usr/bin/env python3
"""Build the indexed-egress regression as 16 independent width-pair ELFs.

Each ELF retains both ordering modes, both mask modes, and all eight AVL
requests from the canonical regression: 16 * 32 = 512 checked scenarios.
"""
import json
from pathlib import Path
import subprocess


def main():
    root = Path(__file__).resolve().parents[2]
    source = (root / "apps/indexed_egress_regression/main.c").read_text()
    functions = source[:source.index("int main(void)")]
    output = root / "hardware/build/rce/indexed_egress_shards"
    output.mkdir(parents=True, exist_ok=True)
    apps = []
    for sew in (8, 16, 32, 64):
        for eew in (8, 16, 32, 64):
            name = f"indexed_egress_{sew}_{eew}"
            apps.append(name)
            folder = root / "apps" / name
            folder.mkdir(exist_ok=True)
            body = functions + "int main(void){ const unsigned sizes[]={1,3,5,7,9,16,17,31};\n"
            for ordered in (0, 1):
                body += (f"for(unsigned k=0;k<8;k++)for(unsigned m=0;m<2;m++)"
                         f"if(case_{sew}_{eew}_{ordered}(sizes[k],m))return 1;\n")
            body += (f'printf("PASS indexed sew={sew} eew={eew} cases=%u\\n",cases);'
                     'return 0;}\n')
            (folder / "main.c").write_text(body)
            (folder / "data.S").touch()
    with (output / "build.log").open("w") as log:
        subprocess.run(["make", "-C", str(root / "apps"),
                        *[f"bin/{name}" for name in apps],
                        "nr_lanes=4", "vlen=1024"],
                       stdout=log, stderr=subprocess.STDOUT, check=True)
    (output / "apps.json").write_text(json.dumps(apps, indent=2) + "\n")
    print(f"Built {len(apps)} programs; list: {output / 'apps.json'}")


if __name__ == "__main__":
    main()
