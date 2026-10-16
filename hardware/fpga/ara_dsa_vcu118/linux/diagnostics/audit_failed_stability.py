"""Separate observed faults from RTL attribution using the original binaries."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct

from analyze_loader_stall import IMAGE_SHA256, LOADER_SHA256


def metadata_fault(output, loader):
    def value(name):
        matches = re.findall(r'\b'+name+r'\s*:\s*([0-9a-f]{16})\b', output)
        if len(matches) != 1:
            raise ValueError('Missing/ambiguous fault register: '+name)
        return int(matches[0], 16)

    # These code offsets lie in the first, equal-file-offset PT_LOAD segment.
    for offset, instruction in ((0x10902, 0x3aa7bd23),
                                (0x11c44, 0x0009bd83),
                                (0x11c4c, 0x000db683)):
        if struct.unpack_from('<I', loader, offset)[0] != instruction:
            raise ValueError('Original loader instruction mismatch')
    pc, s3, s11 = (value(n) for n in ('epc', 's3', 's11'))
    base = pc-0x11c4c
    if base & 4095 or s3 != base+0x22cb8:
        raise ValueError('Fault does not match the reviewed loader global')
    if s11 or value('badaddr') or value('cause') != 13:
        raise ValueError('Not the observed NULL argv load-page fault')
    if value('status') & (1 << 8):
        raise ValueError('Fault is not from user privilege')
    signal = output.index('unhandled signal 11')
    rss = output.find('BUG: Bad rss-counter state')
    return dict(
        observed='user_loader_null_pointer_fault', loader_base=hex(base),
        store_instruction='sd a0,954(a5)', store_offset='0x10902',
        load_instruction='ld s11,0(s3)', load_offset='0x11c44',
        fault_instruction='ld a3,0(s11)', fault_offset='0x11c4c',
        global_address=hex(s3), loaded_s11=hex(s11),
        global_memory_at_fault_captured=False,
        rss_warning_follows_user_fault=rss > signal,
        direct_return_lane=3,
        limitation='Last R beat is lane 3 of a 32-byte line. Losing only an earlier '
                   'beat cannot by itself replace this lane with zero. Last-beat '
                   'loss suppresses ACK. Indirect corruption is not ruled out.',
        rtl_cause_proven_for_this_event=False,
    )


def snapshot_classification(snapshot, image):
    core = snapshot['core']
    pc, head = core['last_pc'], core['head_pc']
    result = dict(retired=core['retired'], last_pc=hex(pc), head_pc=hex(head),
                  historical_trap_pc=hex(core['last_trap_pc']),
                  historical_trap_cause=core['last_trap_cause'],
                  historical_trap_tval=hex(core['last_trap_tval']),
                  one_snapshot_is_not_stall_proof=True)
    if (pc, head) == (0xffffffff80b93828, 0xffffffff80b938c2):
        for offset, word in ((0xb93828, 0x08021d63), (0xb938c2, 0x00223c23)):
            if struct.unpack_from('<I', image, offset)[0] != word:
                raise ValueError('Original kernel exception instruction mismatch')
        result.update(observed='kernel_exception_entry',
                      last_instruction='bnez tp,handle_exception+0x9e',
                      head_instruction='sd sp,24(tp)', head_valid_unobserved=True,
                      pipe_implementation_bug_proven=False)
    elif (pc, head) == (0xffffffff80b87724, 0xffffffff80b87728):
        result['observed'] = 'kernel_arch_cpu_idle_after_test'
    elif pc < (1 << 38) and (pc & 4095, head & 4095) == (0xb4a, 0xb32):
        base = pc-0x11b4a
        result.update(observed='consistent_with_prior_loader_jump_signature',
                      candidate_loader_base=hex(base),
                      candidate_target=hex(base+0xd0dc),
                      candidate_trap_offset=hex(core['last_trap_pc']-base),
                      code_page_readback_required=True)
    else:
        result['observed'] = 'unclassified_snapshot'
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--evidence', type=Path, required=True)
    p.add_argument('--image', type=Path, required=True)
    p.add_argument('--loader', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    image, loader = a.image.read_bytes(), a.loader.read_bytes()
    for data, digest in ((image, IMAGE_SHA256), (loader, LOADER_SHA256)):
        if hashlib.sha256(data).hexdigest() != digest:
            raise ValueError('Wrong original executable')
    report = dict(scope='offline_failure_classification_not_full_RTL_attribution',
                  image_sha256=IMAGE_SHA256, loader_sha256=LOADER_SHA256,
                  inputs={}, snapshots={})
    path = a.evidence/'metadata/uart.bin'
    data = path.read_bytes()
    report['inputs'][str(path)] = hashlib.sha256(data).hexdigest()
    report['metadata'] = metadata_fault(data.decode(errors='replace'), loader)
    for path in sorted(a.evidence.rglob('snapshot.json')):
        data = path.read_bytes()
        report['inputs'][str(path)] = hashlib.sha256(data).hexdigest()
        report['snapshots'][str(path.relative_to(a.evidence))] = snapshot_classification(
            json.loads(data.decode('utf-8-sig')), image)
    with a.out.open('x') as f:
        json.dump(report, f, indent=2)
        f.write('\n')
    print(a.out)


if __name__ == '__main__':
    main()
