"""Non-freezing debug snapshots; no UART, reset, or memory writes."""
import argparse
import json
from pathlib import Path
import sys
import time

p = argparse.ArgumentParser()
p.add_argument('--software', type=Path, required=True)
p.add_argument('--probes', type=Path, required=True)
p.add_argument('--out', type=Path, required=True)
a = p.parse_args()
sys.path.insert(0, str(a.software))
import host_load as host
from host_transport import VivadoTransport
a.out.mkdir(parents=True, exist_ok=False)
samples = []
with VivadoTransport(a.out / 'transport', probes=a.probes,
                     vivado=r'D:\Xilinx\Vivado\2020.1\bin\vivado.bat') as t:
    for i in range(16):
        s = host.capture_snapshot(t)
        samples.append(s)
        (a.out / 'samples.json').write_text(json.dumps(samples, indent=2))
        print(i, {k: hex(v) for k, v in s['core'].items()}, flush=True)
        time.sleep(.137)
