"""Overlay the tested UI reset fix onto a verified repaired dual-DDR package."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import zipfile

from ui_reset_fpga import patch_ui_reset_distribution

WRAPPER = 'rtl/board/dram_wrapper_xilinx.sv'


def stage(source, target, cdc):
    source = source.resolve(strict=True)
    target = target.absolute()
    if target.exists() or source in target.parents:
        raise ValueError('Require new output outside original package')
    digest = lambda data: hashlib.sha256(data).hexdigest()
    inventory = (source / 'SHA256SUMS').read_bytes()
    files = {}
    for row in inventory.decode().splitlines():
        expected, name = row.split('  ', 1)
        path = PurePosixPath(name)
        if path.is_absolute() or '..' in path.parts or '\\' in name or ':' in name or name in files:
            raise ValueError('Unsafe or duplicate inventory path')
        data = (source / name).read_bytes()
        if digest(data) != expected:
            raise ValueError('Source hash mismatch: ' + name)
        files[name] = data
    for provenance in ('dual_inval_clock_fix', 'dual_ethernet', 'mmu_ppn_fix'):
        if 'provenance/' + provenance + '.json' not in files:
            raise ValueError('Missing preserved fix: ' + provenance)
    wrapper = files[WRAPPER].decode()
    if 'gen_ethernet' not in wrapper or 'if (Channel == 0)' not in wrapper:
        raise ValueError('Expected channel-zero-only Ethernet wrapper')
    changes = {}
    for name, data in ((WRAPPER, patch_ui_reset_distribution(wrapper).encode()),
                       ('constraints/cdc.xdc', cdc.read_bytes())):
        changes[name] = {'before': digest(files[name]), 'after': digest(data)}
        files[name] = data
    record = {'source': str(source), 'source_inventory_sha256': digest(inventory),
              'changes': changes, 'profile': 'dual_ddr_ethernet',
              'board_modified': False, 'physical_signoff': False}
    files['provenance/dual_reset_distribution.json'] = (json.dumps(record, indent=2) + '\n').encode()
    files['SHA256SUMS'] = ''.join(f'{digest(data)}  {name}\n' for name, data in sorted(files.items())).encode()
    target.mkdir(parents=True)
    for name, data in files.items():
        path = target / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    with zipfile.ZipFile(target.parent / 'sealed_sources.zip', 'x', zipfile.ZIP_DEFLATED) as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    print(json.dumps(record, indent=2))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('source', type=Path)
    p.add_argument('target', type=Path)
    p.add_argument('cdc', type=Path)
    a = p.parse_args()
    stage(a.source, a.target, a.cdc)
