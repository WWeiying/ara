#!/usr/bin/env python3
"""Read sealed software artifacts; no execution of a firmware or reference."""
import hashlib
import json
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def main():
    pins = json.loads((HERE/'pins.json').read_text())
    assert all(sha(path) == digest for path, digest in pins.items())
    proof = json.loads((HERE/'proof.json').read_text())
    text = (HERE/'soc/program.dis').read_text()
    code = {}
    for match in re.finditer(r'^\s*([0-9a-f]+):\s+([0-9a-f]{4,8})\s+([^\n]+)', text, re.M):
        code[int(match[1], 16)] = dict(insn=int(match[2], 16), asm=match[3].strip())
    init = [0x800004f8] + list(range(0x800004fc, 0x8000051c, 4))
    reads = [0x80000548] + list(range(0x80000812, 0x80000858, 10)) + [0x80000860]
    assert len(init) == len(reads) == 9
    assert code[init[0]]['asm'].startswith('sh\t')
    assert all(code[pc]['asm'].startswith('sd\t') for pc in init[1:])
    assert all(code[pc]['asm'].startswith('ld\t') for pc in reads[:-1])
    assert code[reads[-1]]['asm'].startswith('lhu\t')
    assert code[0x80000344]['asm'] == 'addi\tsp,sp,-304'
    def count(lo, hi):
        return sum(lo <= pc <= hi for pc in code)
    counts = {
        'call_setup_initialize_jalr_and_vstart_branch': count(0x800004f0, 0x80000536),
        'original_helper_instructions': 13,
        'compare_first_word_address_and_branch': count(0x8000053a, 0x80000558),
        'remaining_compare_and_counter_updates': count(0x80000812, 0x80000888),
        'mask_copy_first_iteration': count(0x800004c6, 0x800004ce),
        'mask_copy_later_iteration': count(0x800004c2, 0x800004ce),
    }
    counts['mask_copy_all16_iterations'] = counts['mask_copy_first_iteration'] + 15*counts['mask_copy_later_iteration']
    actual_receipts = []
    for path in sorted(HERE.glob('host_*/case*.log.exit.json')):
        item = json.loads(path.read_text())
        mutation = int(re.search(r'case(\d+)', path.name)[1])
        assert item['returncode'] == (-4 if mutation == 8 else 0 if mutation == 0 else 1)
        actual_receipts.append(dict(path=str(path),sha256=sha(path),**item))
    assert len(actual_receipts) == 20
    backends = {key: {k: v for k, v in value.items() if k != 'helpers'}
                for key, value in proof['backends'].items()}
    report = dict(status='HOST_COMPILED_STATIC_COST_ONLY_NOT_REFERENCE_NOT_DUT',
        prepare_actual_returncode=0, prepare_command=['python3','-B','prepare.py'],
        prepare_terminal_evidence=dict(session_id=54883,completed_chunk='2a75cc'),
        pins=len(pins),pins_unchanged=True,pins_sha256=sha(HERE/'pins.json'),
        proof_sha256=sha(HERE/'proof.json'),backends=backends,
        actual_soc_init=[dict(pc=hex(pc),**code[pc]) for pc in init],
        actual_soc_output_reads=[dict(pc=hex(pc),**code[pc]) for pc in reads],
        static_instruction_counts=counts,main_frame_bytes=304,
        scope=dict(calls=4095,results=262080,guards=8190,vstart_checks=4095,
                   helper_instructions=53235,mask_buffers=1575,physical_mask_bytes=128),
        host_actual_receipts=actual_receipts,
        estimate=dict(success_path_only=True,not_measured_retired=True,
            conservative_firmware_envelope=1200000,
            note='Per-call <=200 plus per-mask-group <=200, remaining setup/console allowance30000; rounded upward. Not an execution result.',
            arithmetic=4095*200+1575*200+30000),
        reference_proposal=dict(instruction_limit=3000000,wall_s=120,raw_bytes=768*1024**2,
            attempts=1,requires_independent_checker_review=True,started=False),
        DUT_authorized=False)
    with (HERE/'compiled_review.json').open('x') as stream:
        json.dump(report, stream, indent=2);stream.write('\n')
    print(json.dumps({k:report[k] for k in ('status','pins','static_instruction_counts','backends')}),flush=True)

if __name__ == '__main__':
    main()
