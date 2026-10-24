"""Required control-only wave profile for the unchanged dual-reader baseline."""
import argparse
import json
from pathlib import Path

VLSU = 'ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu'


def profile():
    signals = []

    def add(alias, path):
        signals.append(dict(alias=alias, path='/' + path.replace('.', '/'), format='h', required=True))

    add('reset_n', 'ara_tb.rst_n')
    for name in ('qbs_active_q', 'akv_active_q', 'qbs_command_fire', 'akv_command_fire',
                 'qbs_terminal', 'akv_terminal', 'normal_vlsu_idle', 'prepare_inflight',
                 'ar_hold_empty', 'qbs_success_valid', 'qbs_fault_valid', 'akv_success_valid',
                 'akv_fault_valid'):
        add(name, VLSU+'.'+name)
    for owner in ('qbs', 'akv'):
        engine = VLSU+'.i_'+owner+'_engine'
        for name in ('state_q', 'read_busy'):
            add(owner+'_'+name, engine+'.'+name)
        reader = engine+'.i_read_engine'
        for name in ('range_fifo_count_q', 'burst_fifo_count_q', 'plan_state_q', 'ar_stalled_q',
                     'completion_valid_q', 'completion_ready_i', 'fault_pending_q', 'fault_valid_o',
                     'fault_ready_i', 'fault_kind_o', 'fault_vaddr_o', 'range_valid_i', 'range_ready_o',
                     'data_valid_o', 'data_ready_i', 'axi_ar_valid_o', 'axi_ar_ready_i',
                     'axi_r_valid_i', 'axi_r_ready_o', 'mmu_req_o', 'mmu_valid_i',
                     'mmu_exception_valid_i', 'range_vaddr_i', 'range_bytes_i',
                     'range_tag_i', 'data_tag_o', 'completion_tag_o', 'fault_tag_o',
                     'physical_check_valid_o', 'physical_check_addr_o',
                     'physical_range_allowed_i', 'counters_clear_i', 'busy_o'):
            add(owner+'_'+name, reader+'.'+name)
    for name in ('context_ready_q', 'context_q_rows_q', 'context_head_dim_q', 'context_kv_length_q',
                 'context_q_base_q', 'context_k_base_q', 'context_v_base_q', 'context_tile_count_q',
                 'context_v2_q', 'context_write_busy', 'payload_complete'):
        add('akv_'+name, VLSU+'.i_akv_engine.'+name)
    context = VLSU+'.i_qbs_engine.i_activation_context'
    for name in ('context_valid_q', 'context_id_q', 'context_generation_q', 'context_profile_q',
                 'context_layout_q', 'context_m_q', 'context_k_blocks_q', 'fill_in_progress_q',
                 'replay_active_q'):
        add('activation_'+name, context+'.'+name)
    for channel in ('ar', 'r', 'aw', 'w', 'b'):
        cut = VLSU+'.i_axi_cut.i_reg_'+channel
        for name in ('valid_i', 'ready_o', 'valid_o', 'ready_i'):
            add('cut_'+channel+'_'+name, cut+'.'+name)
        slots = cut+'.spill_register_flushable_i.gen_spill_reg'
        for name in ('a_full_q', 'b_full_q'):
            add('cut_'+channel+'_'+name, slots+'.'+name)
    return dict(clock='/ara_tb/clk', edge='negedge', raw_time_unit='100fs',
                sampling='Settled half-cycle snapshots; not pre-NBA posedge samples', signals=signals)


def script(duration_ns, capability_only=False):
    if type(duration_ns) is not int or not 1 <= duration_ns <= 500000:
        raise ValueError('Capture bound must be integer 1..500000 ns')
    selected = ['ara_tb.clk'] + [row['path'][1:].replace('/', '.') for row in profile()['signals']]
    return '\n'.join(['dump -file reader.fsdb -type FSDB',
                      *('dump -add {'+path+'}' for path in selected),
                      'run '+str(duration_ns)+'ns', 'dump -close',
                      'quit' if capability_only else 'run'])+'\n'


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--duration-ns', type=int, default=500000)
    parser.add_argument('--capability-only', action='store_true',
                        help='Quit after the bounded dump; not a functional execution')
    args = parser.parse_args()
    text = script(args.duration_ns, args.capability_only)
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output/'profile.json').write_text(json.dumps(profile(), indent=2)+'\n')
    (args.output/'probe.tcl').write_text(text)
