"""Source-only deterministic scoreboard-owner proposal; no software build or EDA."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'verification/out'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    paths = {
        OUT/'scalar-misalign-gain791-agent-20261008-01/combined-toggle-bits.json':
            'c1469ef375435722551b9a32644e3cfec54a758965174caf153ec12e43bf7a24',
        OUT/'scalar-misalign-gain791-agent-20261008-01/gain-receipt.json':
            'f2de96c61684916121d6c550cd77e4d18bb92ee3e30bd09a9442517293bd8ccc',
        OUT/'scalar-misalign789-soc-qualified-agent-20261008-03/native-fault-audit.json':
            'c744c5640c2729493f61d5d48534845dac98a7bf81988e4800f24409054abf51',
        OUT/'conservative-toggle785-static-agent-20261008-01.json':
            '035172c63269024e6e2171426fa8616dedaf6da442f766934806dcb181cdd1d5',
    }
    for path, expected in paths.items():
        assert sha(path) == expected
    merged = json.loads(next(p for p in paths if p.name == 'combined-toggle-bits.json').read_bytes())
    ranking = json.loads(next(p for p in paths if p.name == 'conservative-toggle785-static-agent-20261008-01.json').read_bytes())
    owners = json.loads(next(p for p in paths if p.name == 'native-fault-audit.json').read_bytes())['owners']
    row = next(r for r in ranking['ranking'] if r['scope'].endswith('.i_scoreboard'))
    native = merged[row['scope']]
    assert native['checksum'] == row['checksum'] == '264082867'
    targets = []
    for slot in (2,3,6,7):
        for stem in ('mem_q', 'mem_n', 'fwd_o.sbe'):
            name = f'{stem}[{slot}].'+('sbe.ex.tval' if stem.startswith('mem_') else 'ex.tval')
            obj = next(o for o in row['objects'] if o['name'] == name)
            assert not obj['partial_EL_direction_binding_HOLD'] and obj['width'] == 64
            remaining = [c for c in obj['coordinates'] if not (int(native['bits'],16) >> (native['width']-1-c)) & 1]
            assert len(remaining) == 64
            targets.append(dict(slot=slot, name=name, remaining_serialized_slots=64))
    book_path = OUT/'repaired-aligned-build-20260930-01/build-source-pins.json'
    assert sha(book_path) == ranking['input_pins'][str(book_path)]
    book = json.loads(book_path.read_bytes()); paths[book_path] = sha(book_path)
    for relative in ('hardware/deps/cva6/core/scoreboard.sv',
                     'hardware/deps/cva6/core/controller.sv',
                     'hardware/deps/cva6/core/cva6.sv',
                     'hardware/deps/cva6/core/include/build_config_pkg.sv',
                     'hardware/deps/cva6/core/include/cv64a6_imafdcv_sv39_config_pkg.sv'):
        path = ROOT/relative
        assert sha(path) == book[str(path)]
        paths[path] = book[str(path)]
    a = 0x0000002555555003
    b = a ^ ((1<<64)-1)
    assert b == 0xffffffdaaaaaaffc and a & 7 and b & 7
    result = dict(status='SOURCE_JUSTIFIED_NEW_SLOT_TARGETS_NOT_BUILT_OR_RUN',
        baseline='Formal791 plus qualified scalar-misalign singleton; not a claim of formal792 admission',
        input_pins={str(p):h for p,h in paths.items()}, scope=row['scope'], checksum=row['checksum'],
        targets=targets, residual_serialized_slots=768,
        prior_fault_owner_ids=[o['tid'] for o in owners],
        exclude_already_covered_slots=[1,4,5],
        allocation_proof=[
            'Config:8 scoreboard entries, TRANS_ID_BITS3, SuperscalarEn0 -> NrIssuePorts1.',
            'scoreboard:185..212 trans_id=issue_pointer; increment only accepted decoded valid && ack && !flush_unissued.',
            'scoreboard:315..317 issue_pointer_n=issue_pointer[num_issue], full flush overrides to0.',
            'controller:300..310 eret raises flush_id/ex/unissued; cva6:893 connects flush_id to issue stage; scoreboard flush resets pointer.',
            'scoreboard:225..227 FU_NONE NOP entries still allocated and made valid, so fixed NOPs advance pointer.',
            'scoreboard:257 writes exception to matching trans_id; :337..345 fwd copies mem_q exception unchanged.',
            'scoreboard:293..300 flush clears issued/valid/ex.valid, not stored ex.tval: prior tval survives until next owner writes the slot.',
        ],
        stimulus=dict(
            address_A=hex(a), address_B=hex(b), full64_complement=True,
            operations='For each slot k=2,3,6,7: LD(A), SD(B), LD(A), each from its own mret landing block:12 faults total.',
            landing='All address/data/sentinel/ledger setup before mret. .option norvc; exactly k words0x00000013 then one fixed32bit LD/SD. No call, branch, CSR, fence, load/store setup between landing and fault.',
            handler='Verify exact expected cause4/6, fault PC and tval; record old load destination and store guards. Set mepc to next landing, not PC+4; mret creates the next known allocation origin.',
            after_fault='Branchless NOP fail-stop region; handler never architecturally resumes there. Reject wrong return or any extra fault.',
            probes='Preedge fullflush/pointer_q, decoded_valid/ack/flush_unissued, allocation trans_id+PC/op, LSU exception owner and scoreboard wb/mem tval. Count accepted allocations, never infer VID from retirement count.',
            oracle='Independent12-frame PC/cause/tval/expectedVID table; full Spike scalar/GPR/memory reference, unchanged destination sentinel/guards, legal aligned recovery and full CSR restore.',
            estimate='Compact scalar-only source, <=600s proposed; no budget expansion or slot/NOP trial tuning.'),
        strict_limits=[
            'Stalls may extend time but cannot alter accepted allocation sequence. Any unexpected fullflush or instruction between landing and fault invalidates predicted owner and must HOLD.',
            '768 is remaining exact serialized capacity, not guaranteed measured gain or official percentage.',
            'Need newELF exact landing disassembly, Spike expected traps and historical ELF/instruction dedup before any build/run approval.',
            'No waived guestCSR, RVH fields, AMO unsupported memory semantics, or repeated mask-random targets.'
        ], software_built=False, EDA_launched=False, RTL_changed=False)
    for path, expected in paths.items():
        assert sha(path) == expected
    output = OUT/'scalar-misalign-slot-rotation791-static-agent-20261008-01.json'
    with output.open('x') as stream:
        json.dump(result, stream, indent=2); stream.write('\n')
    print(output, sha(output), '12_FIELDS_768_SLOTS_SOURCE_PROPOSAL_NO_BUILD_NO_EDA')


if __name__ == '__main__':
    main()
