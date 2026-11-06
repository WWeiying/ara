#!/usr/bin/env python3
"""Wait for both FFN worker results using filesystem events, then audit once."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

from audit import digest, require
from watch_projection_pair import wait_for_results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base',type=Path,required=True); parser.add_argument('--wide',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True); args = parser.parse_args()
    require(not args.output.exists(),'Fresh collection required')
    collector = Path(__file__).with_name('collect_ffn_native.py'); sha = digest(collector)
    print(json.dumps(dict(state='WAITING_FOR_FFN_RESULT_EVENTS',collector_sha256=sha)),flush=True)
    wait_for_results([args.base,args.wide],timeout=7800)
    require(digest(collector) == sha,'Collector changed while waiting')
    subprocess.run([sys.executable,'-B',collector,'--base',args.base,'--wide',args.wide,
                    '--output',args.output],check=True,timeout=600)


if __name__ == '__main__': main()
