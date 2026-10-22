"""Bound static candidates only; no native approval, array decoding or EDA."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'verification/out'
RANK = OUT / 'cva6-full-typed-residual768-agent-20261007-01.json'
RANK_SHA = 'a8fa1e5fb366175c9ac6c55955a969d54c2997a38fd43875c67e6d6a93cbb816'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def selection(field):
    name, scope = field['name'], field['scope']
    if re.fullmatch(r'(issue_entry_o_prev|decoded_instr_i_prev|issue_instr_i_prev)\[0\]\..+', name):
        return 'FPGA_PREVIOUS_ENTRY_CONSTANT_ZERO', None
    if name in ('jump_address', 'jump_address_i'):
        return 'ZCMT_DISABLED_JUMP_ADDRESS_ZERO', None
    prefix = ('instruction_o.' if scope.endswith('.i_accel_decoder') else
              'acc_instruction.' if scope.endswith('.decoder_i') else None)
    if prefix and name.startswith(prefix):
        tail = name[len(prefix):]
        if tail == 'result':
            return 'ACCEL_FIRST_PASS_ZERO_EXTEND_INSTRUCTION', (63, 32)
        if tail in ('pc', 'trans_id', 'bp.cf', 'bp.predict_address', 'ex.tval',
                    'ex.tval2', 'ex.tinst', 'ex.cause', 'ex.valid', 'ex.gva',
                    'is_compressed', 'is_macro_instr', 'is_last_macro_instr',
                    'is_double_rd_macro_instr', 'is_zcmt', 'valid', 'use_pc',
                    'use_zimm', 'use_imm'):
            return 'ACCEL_FIRST_PASS_DEFAULT_ZERO_FIELD', None
    if '.i_instr_queue.' in scope and name in ('fifo_ram_wdata', 'fifo_ram_rdata'):
        return 'HOLD_FPGA_DISABLED_UNDRIVEN_HELPER_NOT_ZERO', None
    return None


def collect():
    assert digest(RANK) == RANK_SHA, 'Ranking drift'
    rank = json.loads(RANK.read_bytes())
    pins = {str(RANK): RANK_SHA}
    bookpath = OUT / 'repaired-aligned-build-20260930-01/build-source-pins.json'
    assert digest(bookpath) == rank['pins'][str(bookpath)]
    book = json.loads(bookpath.read_bytes())
    pins[str(bookpath)] = digest(bookpath)
    sources = dict(rank['source_pins'])
    for rel in ('hardware/src/cva6_accel_first_pass_decoder.sv',
                'hardware/deps/cva6/core/cva6_fifo_v3.sv',
                'hardware/deps/cva6/core/cva6.sv'):
        path = ROOT / rel
        assert digest(path) == book[str(path)], 'Frozen source drift'
        sources[rel] = dict(path=str(path), sha256=book[str(path)])
    for source in sources.values():
        assert digest(Path(source['path'])) == source['sha256']
        pins[source['path']] = source['sha256']
    candidates, held = [], []
    for field in rank['owned_fields']:
        match = selection(field)
        if not match:
            continue
        reason, partial = match
        width = field['logical_width']
        left, right = (partial if partial else
                       (int(field.get('left', '0')), int(field.get('right', '0'))))
        assert left >= right >= 0
        offset = field['serialized_offset']
        # Ascending vectors require a different bit-to-slot mapping.
        assert int(field.get('left', '0')) >= int(field.get('right', '0'))
        coordinates = [offset + 2 * (b - int(field.get('right', '0'))) + d
                       for b in range(right, left + 1) for d in (0, 1)]
        assert set(coordinates) <= set(field['missing_coordinates']), 'Observed counterexample'
        record = dict(field, proof_class=reason, selected_left=left, selected_right=right,
                      selected_coordinates=coordinates, selected_positions=len(coordinates),
                      retained_bit_ranges=([[31, 0]] if partial else []),
                      native_qualification_required=True)
        (held if reason.startswith('HOLD') else candidates).append(record)
    el = OUT / 'native-batch-full766-agent-20261007-01/combined.el'
    pins[str(el)] = digest(el)
    for path in (Path(__file__), Path(__file__).with_name('test_review_cva6_fixed_fields768.py')):
        pins[str(path)] = digest(path)
    existing_scopes = set(re.findall(r'^INSTANCE:\s*(.*?)\s*$', el.read_text(), re.M))
    assert not existing_scopes.intersection(f['scope'] for f in candidates + held), 'Existing scope requires typed dedup'
    for path, sha in pins.items():
        assert digest(Path(path)) == sha, 'End-read drift'
    return dict(schema='CVA6_FIXED_FIELD_STATIC_REVIEW768_V1', population=768, pins=pins,
                sources=sources, candidates=candidates, held_config_inactive_helpers=held,
                candidate_positions_by_class=dict(Counter({reason: sum(f['selected_positions'] for f in candidates if f['proof_class'] == reason)
                                                          for reason in {f['proof_class'] for f in candidates}})),
                proof_references={
                    'FPGA_PREVIOUS_ENTRY_CONSTANT_ZERO': ['id_stage.sv:360', 'cva6.sv:771,897', 'issue_stage.sv:268', 'issue_read_operands.sv:852-855', 'config FpgaAlteraEn=0'],
                    'ZCMT_DISABLED_JUMP_ADDRESS_ZERO': ['id_stage.sv:233-237,331', 'config RVZCMT=0'],
                    'ACCEL_FIRST_PASS': ['cva6_accel_first_pass_decoder.sv:212-240; only field overrides fu/vfp/rs1/rs2/rd/op/result/use_imm', 'decoder.sv:145-162'],
                    'FPGA_HELPERS_HOLD': ['instr_queue.sv:463-467,492-496', 'cva6_fifo_v3.sv:53-61,74-98,174-211; FPGA_EN=0 removes RAM producer/consumer; merged shape parameter qualification pending']},
                retained=['All normal issue/decoded/scoreboard entries, exceptions, addresses and predictor targets',
                          'All accelerator fu/op/register-dependencies/illegal classification and result[31:0]',
                          'FIFO functional mem arrays/data_i/data_o/pointers/count/flush/handshake/assertions',
                          'All MDA arrays; no guessed flattened mapping', 'CSR/PTW/cache controls: other owner'],
                alias_note='Distinct compiled aliases count separately; same producer is not independent validation',
                nominal_positions_not_official_denominator=True, native_direction_labels_bound=False,
                native_approved=False, exclusion_applied=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = collect()
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2); stream.write('\n')
    print(digest(args.output), result['candidate_positions_by_class'], len(result['held_config_inactive_helpers']))
