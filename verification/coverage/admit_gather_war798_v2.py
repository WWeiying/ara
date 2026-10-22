"""Repair the historical ELF inventory in a successor; never change old reports."""
import json
from pathlib import Path
from types import FunctionType

import admit_gather_war798 as prior

life, require = prior.life, prior.require


def historical(base, ledger, authority, manifest):
    path = prior.BASE / 'elf-ledger-dedup.json'
    old = life.read_bound(path, base['output_pins'][str(path)])
    require(old['ledger_members'] == 796 and old['baseline'] == 796 and
            old['duplicate'] is False and len(old['members']) == 796 and
            [m['vdb'] for m in old['members']] == ledger[1:-1] and len(ledger) == 798,
            'Exact sealed796 inventory and797 compile-first ledger')
    missing = Path(ledger[-1]).parent / 'manifest.json'
    record = life.read_bound(missing, authority[str(missing)])
    elves = [s.split('=', 1)[1] for s in record['command'] if s.startswith('+PRELOAD=')]
    require(len(elves) == 1, 'One historical797 preload')
    elf = elves[0]
    sha = old['new_ELF_sha256']
    require(authority.get(elf) == sha == record['pins'].get(elf) == life.digest(Path(elf)),
            'Historical797 ELF actual bytes and sealed command')
    known = {h for row in old['members'] for h in row['ELF_candidates'].values()}
    require(sha not in known, 'Historical797 must be a unique ELF')
    members = old['members'] + [dict(vdb=ledger[-1], ELF_candidates={elf: sha},
                                   command_sources=[str(missing)])]
    elves = [s.split('=', 1)[1] for s in manifest['command'] if s.startswith('+PRELOAD=')]
    require(len(elves) == 1, 'One new Gather preload')
    elf = elves[0]
    new_sha = manifest['elf_sha256']
    require(authority.get(elf) == new_sha == life.digest(Path(elf)) and
            new_sha not in known | {sha}, 'Actual Gather ELF distinct from all797')
    return dict(baseline=797, ledger_members=798, duplicate=False,
                new_ELF_sha256=new_sha, members=members + [dict(
                    vdb=str(prior.RUN / 'code.vdb'), ELF_candidates={elf: new_sha},
                    command_sources=[str(prior.RUN / 'manifest.json')])])


def evaluate(qual, seal):
    pins = {str(p): life.digest(p) for p in (Path(__file__).resolve(),
            Path(__file__).with_name('test_admit_gather_war798_v2.py').resolve())}
    products, ledger = FunctionType(prior.evaluate.__code__,
        dict(prior.evaluate.__globals__, historical=historical))(qual, seal)
    life.check(pins)
    products['evidence-pins.json'] = life.merge_pins(products['evidence-pins.json'], pins)
    return products, ledger


def main(argv=None):
    return FunctionType(prior.main.__code__, dict(prior.main.__globals__, evaluate=evaluate),
                        argdefs=prior.main.__defaults__)(argv)


if __name__ == '__main__':
    main()
