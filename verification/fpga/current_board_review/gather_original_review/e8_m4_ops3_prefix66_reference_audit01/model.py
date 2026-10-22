"""Independent static source contract; no producer imports or raw-file access."""
import hashlib
import json
from pathlib import Path

CHILD = 'rvv_permute_restart_e8_m4_ops3'
RUNTIME = 'gather_prefix_e8_m4_ops3'
PART = Path('/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01/rvv_permute_partitions01')
SOURCE = Path('/home/wangwy/openproject/ara_dsa/hardware/fpga/ara_dsa_vcu118/linux/diagnostics/rvv_matrix/permutation_oracle.c')
C_SHA = 'b6e5fa032dfdc58ec621d0377f93cf824f27ad460d6bd102e173e244a65ec5ca'
S_SHA = '118a8c9572532a2b332749165cff3cea9323a49722641dcf64b14fd501ccd774'
ELF_SHA = 'a68279eaedf724eaf3efa03c71c6d039f40bc1d0c6d128b552d04e6e7ba4706b'
CAP, VLENB, CALLS = 512, 128, 66


def need(condition, reason):
    if not condition:
        raise ValueError(reason)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def original_source_identity():
    """Read only named archived source/manifest/ELF files, never trace/log files."""
    manifest_path = PART / 'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    selected = [c for c in manifest['cases'] if c['name'] == CHILD]
    need(len(selected) == 1, 'Unique original child')
    case = selected[0]
    need((case['sew'], case['lmul'], case['operation_ids'], case['configurations'])
         == (8, 'm4', [3], 2688), 'Original manifest selection')
    need(case['sha256'] == ELF_SHA, 'Original ELF manifest identity')
    assembly = PART / CHILD / 'operations.S'
    elf = PART / 'release/binaries' / CHILD
    need(sha(SOURCE) == manifest['source_sha256']['permutation_oracle.c'] == C_SHA,
         'Original C identity')
    need(sha(assembly) == S_SHA and sha(elf) == ELF_SHA, 'Original S/ELF identity')
    text = assembly.read_text()
    helper = text.split('op_3:\n', 1)[1].split('.global op_4\n', 1)[0].splitlines()
    expected = [
        'vsetvli t0,a4,e8,m4,tu,mu', 'vle8.v v8,(a0)', 'vle8.v v16,(a1)',
        'vle8.v v24,(a2)', 'vlm.v v0,(a5)', 'vsetvli t0,a3,e8,m4,tu,mu',
        'mv t3,a6', 'csrw vstart,a7', 'vrgather.vi v24,v8,31,v0.t',
        'csrr a0,vstart', 'vsetvli t0,a4,e8,m4,tu,mu', 'vse8.v v24,(a2)', 'ret',
    ]
    need(helper == expected, 'Original thirteen-instruction m4 helper')
    return dict(case=case, helper=helper,
                pins={str(p): sha(p) for p in (manifest_path, SOURCE, assembly, elf)})


def independent_model():
    """Transcribed from pinned C, not producer model or observed reference values."""
    state, data, indices, indices16 = 0xe736815b449aec21, [], [], []
    mask64 = (1 << 64) - 1
    for i in range(CAP):
        state ^= (state << 13) & mask64
        state ^= state >> 7
        state ^= (state << 17) & mask64
        data.append(state & 255)
        index = (0, 1, CAP-1, CAP, CAP+1, state % (CAP+32))[i % 6]
        indices.append(index & 255)
        indices16.append(index)
    rows = []
    # Only op3 is enabled. First66 calls stay at seed0, scalar-slot0.
    for length, vl in enumerate((0, 1, 2, 3, 256, 511, 512)):
        for mode in range(4):
            selected = [mode == 0 or (mode == 1 and i % 2 == 1)
                        or (mode == 2 and i % 7 == 2) for i in range(CAP)]
            predicate = [0] * 128
            for i, pick in enumerate(selected):
                if pick:
                    predicate[i // 8] |= 1 << (i % 8)
            for trial, start in enumerate((1, vl // 2, vl if vl <= VLENB*8-1 else CAP-1, CAP-1)):
                result = [91] * CAP
                for i in range(start, vl):
                    if selected[i]:
                        result[i] = data[31]
                rows.append(dict(ordinal=len(rows)+1, tuple=[0, 3, 0, length, mode, trial],
                                 vl=vl, vstart=start, scalar=0, predicate=list(predicate),
                                 output=result))
                if len(rows) == CALLS:
                    need(data[31] == 177, 'Independent source31')
                    need(result == [91]*128 + [177]*128 + [91]*256, 'Known numeric endpoint')
                    need(all(r['predicate'][64:] == [0]*64 for r in rows), 'Physical upper predicate')
                    return dict(input=data, indices=indices, indices16=indices16, rows=rows,
                                source_label=CHILD, runtime_id=RUNTIME, capacity=CAP,
                                vlenb=VLENB, physical_predicate_bytes=128,
                                consumed_predicate_bytes=64, result_checks=33792,
                                guard_checks=132, helper_instructions=858,
                                endpoint=[0, 3, 0, 4, 0, 1], predecessors=65)
    raise ValueError('Incomplete natural prefix')


def expected_prefix(original):
    """Allow only a cut after original full result/guard checks and ++cases."""
    anchor = '            ++cases;\n'
    finish = '    text(errors ? "RVV_PERMUTE_FAIL sew=":"RVV_PERMUTE_PASS sew=");'
    need(original.count(anchor) == original.count(finish) == 1, 'Unique source anchors')
    value = original.replace(anchor, anchor + '            if(cases==66)goto prefix_done;\n')
    return value.replace(finish, 'prefix_done:\n    if(cases!=66)++errors;\n'
                         '    text(errors ? "RVV_GATHER_PREFIX_FAIL sew=":"RVV_GATHER_PREFIX_PASS sew=");')


if __name__ == '__main__':
    raise SystemExit('PREPARATION ONLY: no audit authorized; await main final READY SHA and producer freeze')
