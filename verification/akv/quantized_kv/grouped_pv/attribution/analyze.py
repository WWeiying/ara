"""Strict four-call ABBA retirement attribution using the actual linked ELF."""
from collections import Counter
import importlib.util
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[4]
sys.dont_write_bytecode=True
spec=importlib.util.spec_from_file_location('abba_retirement_primitives',
    ROOT/'verification/akv/quantized_kv/phase_diagnostic/analysis/analyze.py')
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
require=base.require


def analyze(instructions,stream,trials,boundaries,phase_map):
    require(len(trials)==4 and all(t['trial']==i and t['enabled']==(0,1,1,0)[i] and
            type(t['cycles']) is int and 0<t['cycles']<=base.MASK64 for i,t in enumerate(trials)),
            'Need complete own ABBA call timings')
    require(len(boundaries)==2 and len(set(boundaries))==2 and
            {pc for pc,item in instructions.items() if base.is_cycle_read(item)}==set(boundaries) and
            all(instructions[pc]['bits']>>7&31 for pc in boundaries),'Exactly two reviewed cycle CSR sites required')
    phase_for=base.phase_classifier(phase_map,instructions)
    windows=[];current=None;reads=[];order=-1;previous=-1;port=-1
    for row in base.csv_module.csv_records(stream,base.COMMIT_HEADER,base.EVENTS):
        require(all(0<=row[k]<=base.MASK64 for k in ('cycle','pc','rd_wdata','mem_addr','mem_wdata')) and
                0<=row['insn']<=0xffffffff and 0<=row['rd']<32 and row['trap'] in (0,1),
                'Out-of-range trace field')
        if row['event']!='retire':continue
        require(row['order']==order+1 and 0<=row['port']<2 and row['trans_id']==-1 and
                row['cycle']>=previous and (row['cycle']!=previous or row['port']>port),
                'Incomplete/reordered retirement')
        order,previous,port=row['order'],row['cycle'],row['port'];pc=row['pc']
        if current is None and pc not in boundaries:continue
        require(not row['trap'] and pc in instructions and row['insn']==instructions[pc]['bits'],
                'Trap, unknown PC or changed executed instruction')
        item=instructions[pc]
        if pc in boundaries:
            require(len(reads)<8 and pc==boundaries[len(reads)%2] and
                    row['rd']==(item['bits']>>7&31),'Wrong CSR boundary sequence/destination')
            reads.append(dict(pc=hex(pc),order=order,monitor_cycle=row['cycle'],value=row['rd_wdata']))
            if current is None:
                current={k:Counter() for k in ('types','functions','phases','mnemonics','function_gaps','phase_gaps','pcs','pc_gaps')}
                current.update(previous_cycle=row['cycle'],custom=[]);continue
            start,end=reads[-2:];delta=(end['value']-start['value'])&base.MASK64
            require(delta==trials[len(windows)]['cycles'],'Retired CSR values differ from own measured call')
            count=sum(current['types'].values());tail=row['cycle']-current['previous_cycle']
            span=end['monitor_cycle']-start['monitor_cycle']
            require(count==end['order']-start['order']-1 and current['custom']==base.CUSTOM_SEQUENCE,
                    'Incomplete instructions or wrong native command sequence')
            require(all(sum(current[key].values())==count for key in ('functions','phases','mnemonics','pcs')) and
                    all(sum(current[key].values())+tail==span for key in ('function_gaps','phase_gaps','pc_gaps')),
                    'Instruction/interval partition mismatch')
            window=dict(trial=len(windows),enabled=trials[len(windows)]['enabled'],csr_cycles=delta,
                monitor_retire_span=span,monitor_minus_csr_delta=span-delta,start=start,end=end,
                instructions=count,end_csr_gap_cycles=tail,
                custom_words=[f'{word:08x}' for word in current['custom']])
            window.update({key:dict(sorted(current[key].items())) for key in
                ('types','functions','phases','mnemonics','function_gaps','phase_gaps','pcs','pc_gaps')})
            windows.append(window);current=None;continue
        phase=phase_for(pc);label=hex(pc)
        for key,value in (('types',base.instruction_type(item)),('functions',item['function']),
                          ('phases',phase),('mnemonics',item['mnemonic']),('pcs',label)):
            current[key][value]+=1
        gap=row['cycle']-current['previous_cycle']
        for key,value in (('function_gaps',item['function']),('phase_gaps',phase),('pc_gaps',label)):
            current[key][value]+=gap
        current['previous_cycle']=row['cycle']
        if base.instruction_type(item)=='qbs_command':current['custom'].append(item['bits'])
    require(len(reads)==8 and len(windows)==4 and current is None,'Incomplete four-call retirement trace')
    return dict(state='FOUR_CALL_RETIREMENT_PROVEN',windows=windows,
                semantics='Previous-to-next retirement gaps charged to NEXT PC; end-CSR gap separate; not execution time or exclusive stalls',
                hardware_utilization_claimed=False,whole_model=False)


def phase_map(instructions):
    candidates={'quantize_row_q8_0':'query_quantize_leaf',
        'strided_value_decode':'value_decode_leaf','strided_value':'value_callback',
        'expf':'exponential_leaf','__ieee754_expf':'exponential_leaf',
        'quant_kv_ggml_scale_f32':'scale_leaf','quant_kv_ggml_mad_f32':'mad_leaf',
        'qbs_native_execute_command':'native_submission','strided_qk':'qk_callback',
        'memcpy':'shared_memory_helper','memset':'shared_memory_helper'}
    available={name for item in instructions.values() for name in item['function'].split('|')}
    return dict(schema='quantkv_phase_map_v1',
                functions={name:phase for name,phase in candidates.items() if name in available},ranges=[])
