"""Same-ELF Attention observation check; not an expf-only or model speedup gate."""
import re

from audit import require
from check_output_gqa6 import SCOPE as OLD_SCOPE, check as check_original
from check_projection_native import fields

SCOPE = ('OUTPUT_PHASE_SCOPE model=qwen25 query=0 heads=6 kv=1 dim=128 visible=128 '
         'token_major=1 trials=4 whole_call=1 baseline=output_tile candidate=output_tile_probed')
PHASES = ('init','quantize','qk','coefficients','pv','finish','binding')
CALLS = (1,1,4,4,4,1,8)


def check(text, golden):
    require(not re.search(r'Fatal:|Error:|OUTPUT_PHASE_FAIL|^UVM_(?:ERROR|FATAL)\s+@',text,re.M),
            'Simulation/guest failure')
    lines = text.splitlines()
    require(lines.count(SCOPE) == 1 and lines.count('OUTPUT_PHASE_SUITE_PASS') == 1,
            'Scope/unique terminal')
    pending, stats, rows = None, None, []
    projection = [OLD_SCOPE,'OUTPUT_GQA6_FORMAT q4=0']
    for line in lines:
        if line.startswith('OUTPUT_GQA6_'):
            raise AssertionError('Old-fixture markers cannot substitute for probe results')
        if line.startswith('OUTPUT_PHASE_BEGIN '):
            require(pending is None and len(rows) < 4,'Nested/extra call')
            pending = fields(line,'OUTPUT_PHASE_BEGIN')
            require(pending == dict(trial=len(rows),probed=(0,1,1,0)[len(rows)]),'ABBA identity')
            stats = None
            projection.append(line.replace('OUTPUT_PHASE_BEGIN','OUTPUT_GQA6_BEGIN',1).replace('probed=','candidate=',1))
        elif line.startswith('[QBS_PERF] '):
            require(pending is not None and stats is None,'Command outside execution window')
            projection.append(line)
        elif line.startswith('OUTPUT_PHASE_STATS '):
            require(pending is not None and stats is None,'Unexpected/duplicate statistics')
            stats = fields(line,'OUTPUT_PHASE_STATS')
            required = {'trial','probed','timer_reads'} | {p+s for p in PHASES for s in ('_calls','_cycles')}
            require(set(stats) == required and all(stats[k] == v for k,v in pending.items()),'Phase field identity')
            for name, calls in zip(PHASES,CALLS):
                require(stats[name+'_calls'] == (calls if pending['probed'] else 0),'Wrong phase multiplicity')
                require((stats[name+'_cycles'] > 0) if pending['probed'] else stats[name+'_cycles'] == 0,
                        'Missing or unexpected phase timing')
            require(stats['timer_reads'] == (46 if pending['probed'] else 0),'Wrong timestamp work')
        elif line.startswith('OUTPUT_PHASE_RESULT '):
            require(pending is not None and stats is not None,'Missing statistics or call')
            header, separator, hexdata = line.partition(' hex=')
            row = fields(header,'OUTPUT_PHASE_RESULT')
            require(separator and set(row) == {'trial','probed','cycles','commands','groups','values','panels',
                    'key_bytes','fcsr','vcsr','vstart','errors'} and all(row[k] == v for k,v in pending.items()),
                    'Call field identity')
            require((row['fcsr'],row['vcsr'],row['vstart']) == (9,5,0),'Final CSR state')
            exclusive = sum(stats[p+'_cycles'] for p in PHASES if p != 'binding')
            require(exclusive <= row['cycles'],'Disjoint phases exceed complete call')
            require(stats['binding_cycles'] <= stats['qk_cycles'],'Binding is nested, not additive')
            # Retain the accepted numerical, 32-command geometry, native-work,
            # captured-golden, ABBA, and output/FCSR exactness checks unchanged.
            projected_header = header.replace('OUTPUT_PHASE_RESULT','OUTPUT_GQA6_RESULT',1)
            projected_header = projected_header.replace('probed=','candidate=',1).replace(' vstart=0','',1)
            projection.append(projected_header+' hex='+hexdata)
            rows.append(dict(**row,phases=stats,exclusive_phase_cycles=exclusive,
                             unobserved_cycles=row['cycles']-exclusive))
            pending, stats = None, None
        elif line.startswith('OUTPUT_PHASE_') and line not in (SCOPE,'OUTPUT_PHASE_SUITE_PASS'):
            raise AssertionError('Unknown probe record')
    require(pending is None and len(rows) == 4,'Incomplete calls')
    # No payload may appear after the terminal. Simulator epilogue is allowed.
    terminal = lines.index('OUTPUT_PHASE_SUITE_PASS')
    require(not any(s.startswith(('OUTPUT_PHASE_','[QBS_PERF]')) for s in lines[terminal+1:]),'Work after terminal')
    projection.append('OUTPUT_GQA6_SUITE_PASS')
    verified = check_original('\n'.join(projection),golden)
    for row, actual in zip(rows,verified['trials']):
        if row['probed']:
            require(actual['qbs_busy'] <= row['phases']['binding_cycles'],'Busy exceeds enclosing binding')
        row['qbs_busy'] = actual['qbs_busy']
    original = sum(r['cycles'] for r in rows if not r['probed'])/2
    probed = sum(r['cycles'] for r in rows if r['probed'])/2
    paired_changes = [rows[1]['cycles']/rows[0]['cycles']-1,
                      rows[2]['cycles']/rows[3]['cycles']-1]
    change = probed/original-1
    interpretable = max(abs(change),*(abs(v) for v in paired_changes)) <= 0.05
    return dict(state='OUTPUT_PHASE_RAW_FUNCTIONAL_AND_OBSERVATION_CHECKED',trials=rows,
        uninstrumented_cycles=original,probed_cycles=probed,measured_perturbation=change,
        paired_perturbations=paired_changes,quantitative_phase_fractions_allowed=interpretable,
        perturbation_threshold=0.05,paired_bitexact=True,csr_bitexact=True,
        outputs_per_trial=768,commands_per_trial=8,internal_timestamps_per_probed_call=46,
        coefficient_scope='expf plus ordered maximum/sum recurrence and coefficient writes; not expf-only',
        pv_scope='value decoding plus output-resident PV accumulation',
        binding_scope='nested within QK; never add to the exclusive phase sum',
        independent_protocol_checked=False,whole_model=False,optimization_speedup_claim=False)
