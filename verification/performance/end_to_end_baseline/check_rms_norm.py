"""Check real fused-RMSNorm ABBA, CSR/canaries and actual ordered RVV execution."""
import csv
import io
import re

from audit import require
from check_projection_native import fields,checksum

SCOPE='RMS_NORM_SCOPE source=ggml_fused_rms_norm width=2048 decode_rows=1 prefill_rows=4 order=ABBA timing=call_and_csr_completion'
ORDER=(0,1,1,0)


def check(text,prefill,decode):
    require(len(prefill)==32768 and len(decode)==8192,'RMSNorm golden geometry')
    lines=text.replace('\r','').splitlines()
    require(lines.count(SCOPE)==1 and 'RMS_NORM_FAIL' not in text and
            not re.search(r'Fatal:|Error:|^UVM_(?:ERROR|FATAL)\s+@',text,re.M),'RMSNorm scope or simulator failure')
    trials=[fields(line,'RMS_NORM_TRIAL') for line in lines if line.startswith('RMS_NORM_TRIAL ')]
    ends=[fields(line,'RMS_NORM_RESULT') for line in lines if line.startswith('RMS_NORM_RESULT ')]
    require(len(trials)==8 and ends==[dict(trials=8,outputs_checked=40960,boundary_cases=53,sum_cases=10,errors=0)],
            'Incomplete RMSNorm trials/boundaries')
    result=[]
    for i,(rows,golden) in enumerate(((1,decode),(4,prefill))):
        selected=trials[i*4:i*4+4];flags=selected[0].get('fcsr',0)
        require(flags&8 and 0<=flags<32,'Initial sticky flag/rounding changed')
        for trial,row in enumerate(selected):
            expected=dict(rows=rows,trial=trial,candidate=ORDER[trial],fcsr=flags,vcsr=5,vstart=0,
                          checksum=checksum(golden),errors=0)
            require(set(row)==set(expected)|{'cycles'} and row['cycles']>0 and
                    all(row[k]==v for k,v in expected.items()),'RMSNorm output/CSR/trial mismatch')
        a=[r['cycles'] for r in selected if not r['candidate']]
        b=[r['cycles'] for r in selected if r['candidate']]
        result.append(dict(phase='decode' if rows==1 else 'prefill',rows=rows,width=2048,
            baseline_cycles=a,candidate_cycles=b,call_speedup=sum(a)/sum(b),
            warmed_baseline_speedup=2*a[-1]/sum(b),outputs=rows*2048,fcsr=flags))
    return dict(cases=result,trials=8,outputs_checked=40960,boundary_cases=53,sum_cases=10,whole_model=False,
        complete_fused_call=True,timing_includes_csr_completion=True,
        rtl_changed=False,production_library_changed=False)


def check_activity(text):
    reader=csv.DictReader(io.StringIO(text))
    require(reader.fieldnames is not None and set(('cycle','event','arch_seq','insn','vl','vstart',
                                                 'nr_lanes','vlen_bits'))<=set(reader.fieldnames),'Vector trace fields')
    configs=[];ordered=[];seen=set()
    for row in reader:
        if row['event']=='config':configs.append((int(row['nr_lanes']),int(row['vlen_bits'])))
        if row['event']!='alloc':continue
        insn=int(row['insn'],16)
        if (insn&0x7f)==0x57 and ((insn>>12)&7)==1 and (insn>>26)==0b110011:
            seq=int(row['arch_seq']);require(seq not in seen,'Duplicate ordered-reduction allocation');seen.add(seq)
            require(1<=int(row['vl'])<=128 and int(row['vstart'])==0,'Ordered reduction VL/vstart')
            ordered.append(seq)
    # 160 in the eight complete calls; 95 in the five-rounding-mode width matrix;
    # eight in the IEEE cases and 25 in the raw-FP64 order-sensitive checks.
    require(configs==[(4,1024)] and len(ordered)==288,'Ordered reduction/configuration work differs')
    return dict(nr_lanes=4,vlen_bits=1024,ordered_widening_reduction_allocations=len(ordered))
