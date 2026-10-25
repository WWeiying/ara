#!/usr/bin/env python3
"""Raw paired acceptance of the AKV-fault to QBS-reuse SoC fixture."""
import argparse
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from run_handoff import s, ROOT, checked_soc
import fault_checks


def checked_run(directory, shared):
    directory = directory.resolve(strict=True)
    report, status = (s.read_json(directory / name) for name in ('result.json','status.json'))
    s.require(report.get('state') == status.get('state') == 'PASS' and status.get('child_pid') is None and
              report.get('post_pins_match') is True and report.get('independent_protocol_checked') is True and
              report.get('shared_image') is shared, 'Need checked terminal fault PASS')
    receipt = directory / 'source-pins.json'
    s.require(s.digest(receipt) == report['source_pins_sha256'], 'Run receipt changed')
    pins = s.read_json(receipt)
    s.verify_pins(pins)
    s.verify_pins(report['evidence_sha256'])
    simv = Path(status['simv'])
    image = s.hashes(s.image_files(simv))
    s.require(all(pins.get(k) == h for k,h in image.items()), 'Image not pinned by this run')
    if shared:
        _, snapshot, _, accepted = checked_soc(simv.parent.parent)
        s.require(image == accepted, 'Wrong shared image')
        source = Path(snapshot['source_mapping'][str(ROOT/'hardware/src/vlsu/vlsu.sv')])
    else:
        source = ROOT/'hardware/src/vlsu/vlsu.sv'
    raw = fault_checks.check_log((directory/'work/run.vcs.log').read_text(),source.read_text())
    for key,value in raw.items():
        s.require(key == 'state' or report.get(key) == value, 'Raw fault result mismatch: '+key)
    wave = fault_checks.check_cycles(directory/'cycles/cycles.csv',shared)
    s.require(wave == report['wave_evidence'], 'Raw fault wave mismatch')
    protocol = directory/'work/uvm_result.json'
    s.check_result(protocol,report['elf_sha256'],image)
    p = s.read_json(protocol)
    s.require(p['log_sha256'] == s.digest(directory/'work/run.vcs.log') and
              p['vector_trace_sha256'] == s.digest(directory/'work/vector_trace.csv'), 'Protocol raw mismatch')
    s.verify_pins(pins)
    s.verify_pins(report['evidence_sha256'])
    return report, dict(directory=str(directory), result_sha256=s.digest(directory/'result.json'),
        status_sha256=s.digest(directory/'status.json'), source_pins_sha256=s.digest(receipt),
        wave=wave, evidence_sha256=report['evidence_sha256'])


def audit(baseline, shared):
    old, old_evidence = checked_run(baseline,False)
    new, new_evidence = checked_run(shared,True)
    s.require(old['elf_sha256'] == new['elf_sha256'], 'Paired ELF differs')
    s.require(old['hardware_records'] == new['hardware_records'], 'Paired command cycles/work differ')
    return dict(state='REVERSE_READER_FAULT_PAIRED_RAW_RECHECKED', same_elf=True,
        elf_sha256=new['elf_sha256'], commands_per_image=14, command_counters_identical=True,
        fault_owner='akv', fault_kind='PMA', cause=5, tval=0, exact_trap_pc_checked=True,
        baseline=old_evidence, shared=new_evidence, independent_protocol_checked=True,
        current_inputs_match=True, qbs_context_reuse_after_foreign_fault=True,
        production_promoted=False, ppa_measured=False, model_performance=False,
        auditor_sha256=s.digest(Path(__file__)))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('baseline','shared','output'):
        parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args()
    s.require(not args.output.exists(),'New output required')
    result=audit(args.baseline,args.shared)
    with args.output.open('x') as stream:
        stream.write(json.dumps(result,indent=2,sort_keys=True)+'\n')
    print(result['state'])
