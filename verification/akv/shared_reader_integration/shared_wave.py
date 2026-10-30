"""One physical reader plus two client endpoints; no dual-reader aliases."""
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('dual_handoff_profile',
    HERE.parent / 'reader_handoff/wave_profile.py')
baseline = importlib.util.module_from_spec(spec)
spec.loader.exec_module(baseline)
VLSU = baseline.VLSU

READER_FIELDS = (
    'range_fifo_count_q', 'burst_fifo_count_q', 'plan_state_q', 'ar_stalled_q',
    'response_drain_q', 'completion_valid_q', 'completion_ready_i', 'fault_pending_q',
    'fault_valid_o', 'fault_ready_i', 'fault_kind_o', 'fault_vaddr_o',
    'range_valid_i', 'range_ready_o', 'data_valid_o', 'data_ready_i', 'data_o',
    'data_strb_o', 'data_offset_o', 'axi_ar_valid_o', 'axi_ar_ready_i',
    'axi_r_valid_i', 'axi_r_ready_o', 'mmu_req_o', 'mmu_valid_i',
    'mmu_exception_valid_i', 'range_vaddr_i', 'range_bytes_i', 'range_tag_i',
    'data_tag_o', 'completion_tag_o', 'fault_tag_o', 'physical_check_valid_o',
    'physical_check_addr_o', 'physical_range_allowed_i', 'counters_clear_i', 'busy_o')
ENDPOINT_FIELDS = (
    'read_range_valid', 'read_range_ready', 'read_range_tag', 'read_range_vaddr',
    'read_range_bytes', 'read_data_valid', 'read_data_ready',
    'read_data', 'read_data_strb', 'read_data_offset', 'read_data_tag',
    'read_completion_valid', 'read_completion_ready', 'read_completion_tag',
    'read_fault_valid', 'read_fault_ready', 'read_fault_kind', 'read_fault_vaddr',
    'read_fault_tag')


def profile():
    original = baseline.profile()
    signals = [s for s in original['signals'] if '/i_read_engine/' not in s['path']]

    def add(alias, path):
        signals.append(dict(alias=alias, path='/' + path.replace('.', '/'), format='h', required=True))

    add('reader_clk_en', VLSU + '.shared_read_clk_en')
    for field in READER_FIELDS:
        add('reader_' + field, VLSU + '.i_shared_reader.i_read_engine.' + field)
    for owner in ('qbs', 'akv'):
        for field in ENDPOINT_FIELDS:
            add(owner + '_' + field, VLSU + '.i_' + owner + '_engine.' + field)
    assert len({s['alias'] for s in signals}) == len(signals)
    return {**original, 'signals': signals,
            'topology': 'One real shared reader and two independently observed client endpoints'}


def script(duration_ns=500000):
    if type(duration_ns) is not int or not 1 <= duration_ns <= 500000:
        raise ValueError('Bounded dump duration required')
    paths = ['ara_tb.clk'] + [s['path'][1:].replace('/', '.') for s in profile()['signals']]
    return '\n'.join(['dump -file reader.fsdb -type FSDB',
        *('dump -add {' + p + '}' for p in paths),
        f'run {duration_ns}ns', 'dump -close', 'run']) + '\n'


if __name__ == '__main__':
    print(json.dumps(profile(), indent=2))
