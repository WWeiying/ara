"""Real reader/cut/boundary identities; reader-held is not inferred from cut-held."""
import importlib.util
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent


def load(name, path):
    spec=importlib.util.spec_from_file_location(name,path)
    mod=importlib.util.module_from_spec(spec)
    sys.modules[name]=mod
    spec.loader.exec_module(mod)
    return mod


legacy=load('reader_fault_old_profile',HERE.parent/'reader_handoff/wave_profile.py')
shared=load('reader_fault_shared_profile',HERE.parent/'shared_reader_integration/shared_wave.py')
VLSU=legacy.VLSU
CONTEXT=('ready_q','q_rows_q','head_dim_q','kv_length_q','q_base_q','k_base_q',
         'v_base_q','tile_count_q','v2_q')


def profile(is_shared):
    base=(shared if is_shared else legacy).profile()
    signals=[{**s,'path':s['path'].replace('/i_axi_cut/','/i_axi_cut/i_cut/')}
             for s in base['signals']]

    def add(alias,path):
        signals.append(dict(alias=alias,path='/'+path.replace('.','/'),format='h',required=True))

    reader=VLSU+('.i_shared_reader.i_read_engine' if is_shared else '.i_qbs_engine.i_read_engine')
    for field in ('ar_stalled_q','burst_fifo_count_q','response_drain_q','fault_pending_q',
                  'fault_valid_o','fault_ready_i','fault_kind_o','fault_vaddr_o','range_fifo_count_q',
                  'plan_state_q','completion_valid_q','busy_o','data_valid_o'):
        add('r_'+field,reader+'.'+field)
    wrapper=VLSU+'.i_axi_cut'
    for field in ('state_q','ordinal_q','count_q','held_q','empty_q','injected_q','target',
                  'block_ar','block_r','inject_resp'):
        add('shim_'+field,wrapper+'.'+field)
    for prefix,req,rsp in (('up','slv_req_i','slv_resp_o'),('down','cut_req','cut_resp'),
                           ('bus','mst_req_o','mst_resp_i')):
        for field in ('ar_valid','r_ready'):
            add(prefix+'_'+field,wrapper+'.'+req+'.'+field)
        for field in ('ar_ready','r_valid'):
            add(prefix+'_'+field,wrapper+'.'+rsp+'.'+field)
        add(prefix+'_ar',wrapper+'.'+req+'.ar')
        for field in ('addr','id','len','size','burst'):
            add(prefix+'_ar_'+field,wrapper+'.'+req+'.ar.'+field)
        for field in ('data','id','last','resp','user'):
            add(prefix+'_r_'+field,wrapper+'.'+rsp+'.r.'+field)
    if len({s['alias'] for s in signals}) != len(signals):
        raise ValueError('Duplicate profile alias')
    return {**base,'signals':signals,'topology':('shared' if is_shared else 'private'),
            'interposer':'before unchanged registered cut; actual memory responses only'}


def script(is_shared, duration_ns=250000):
    if type(duration_ns) is not int or not 1 <= duration_ns <= 500000:
        raise ValueError('Finite capture required')
    paths=['ara_tb.clk']+[s['path'][1:].replace('/','.') for s in profile(is_shared)['signals']]
    return '\n'.join(['dump -file reader.fsdb -type FSDB',
                      *('dump -add {'+p+'}' for p in paths),
                      f'run {duration_ns}ns','dump -close','run'])+'\n'
