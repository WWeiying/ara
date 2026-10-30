"""Generate isolated paired sources; never edit canonical runtime headers."""
from pathlib import Path
from query_guard_experiment import candidate, SOURCE, HERE, ROOT


def generate(out):
    raw=candidate(SOURCE.read_text())
    start=raw.index('static inline int candidate_prefill_admit(')
    end=raw.index('#undef PREFILL_CHECKED_ALIGNMENT',start)
    admission=raw[start:end]
    for name in ('input_t','admission_t'):
        admission=admission.replace('candidate_prefill_'+name,'quant_prefill_'+name)
    admission=admission.replace('CANDIDATE_PREFILL_MAX_QUERIES','QUANT_PREFILL_MAX_QUERIES')
    canonical=ROOT/'software/akv/experimental/quantized_kv/prefill/execute.h'
    raw=canonical.read_text()
    execute=raw[raw.index('static inline int quant_prefill_execute('):raw.rindex('#endif')]
    execute=execute.replace('quant_prefill_execute(', 'query_guard_execute(')
    execute=execute.replace('quant_prefill_admit(request,','candidate_prefill_admit(request,')
    (out/'query_guard_candidate.h').write_text(
        '#include "software/akv/experimental/quantized_kv/prefill/execute.h"\n'
        '#define PREFILL_CHECKED_ALIGNMENT(p,n) __builtin_assume_aligned((p),(n))\n'+
        admission+'\n#undef PREFILL_CHECKED_ALIGNMENT\n'+execute)
    raw=(HERE/'native_strided_main.c').read_text()
    raw=raw.replace('#include "execute.h"','#include "query_guard_candidate.h"')
    start=raw.index('    if(shared) {')
    end=raw.index('    drain();uint64_t elapsed=',start)
    raw=raw[:start]+'''    quant_prefill_report_t report;
    status=shared ? query_guard_execute(&input,&bindings,&full_workspace,sizeof(full_workspace),&report) :
                   quant_prefill_execute(&input,&bindings,&full_workspace,sizeof(full_workspace),&report);
    calls=report.native.command_attempts;values=report.native.value_decodes;
    panels=report.key_panels;key_bytes=report.key_bytes;
    if(!status && (report.queries_quantized!=8 || report.native.completed_groups!=1)) status=3;
'''+raw[end:]
    raw=raw.replace('values!=(shared?20:74)','values!=20')
    raw=raw.replace('panels!=(shared?1u:4u) || key_bytes!=(shared?20u:74u)*row_bytes',
                    'panels!=1u || key_bytes!=20u*row_bytes')
    raw=raw.replace('baseline=per_query_qbs','baseline=grouped_qbs_query_guard')
    raw=raw.replace('PREFILL_', 'QUERY_GUARD_')
    (out/'query_guard_main.c').write_text(raw)
    return [SOURCE,canonical,HERE/'native_strided_main.c',Path(__file__),HERE/'query_guard_experiment.py']
