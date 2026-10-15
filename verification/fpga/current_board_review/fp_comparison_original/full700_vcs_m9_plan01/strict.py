"""Immutable full oracle plus first-cause context, no new acceptance alternatives."""
import importlib.util
import json
from newscope import PREVIOUS, BOUND
from model import model, require

_spec = importlib.util.spec_from_file_location('immutable_strict700_worker', PREVIOUS/'strict.py')
_source = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_source)
specification, spike_rows, VETO = _source.specification, _source.spike_rows, _source.VETO
setup, memop, packed, rvv, offload = _source.setup, _source.memop, _source.packed, _source.rvv, _source.offload


class AuditError(ValueError):
    def __init__(self, diagnostic):
        self.diagnostic = diagnostic
        super().__init__(json.dumps(diagnostic, sort_keys=True))


def audit(rows, spec, spike_vectors=False, abort=None):
    context = dict(call_ordinal=0, classification='bootstrap_or_protocol', cycle=None)
    golds = model()['rows']
    lookup = {r['pc']:(op,i) for op,rr in enumerate(spec['routines']) for i,r in enumerate(rr)}
    ordinal = 0
    def observed():
        nonlocal ordinal
        for row in rows:
            if row.get('event','retire') == 'retire':
                pc = row.get('pc',0)
                pair = lookup.get(pc)
                if pair is not None and pair[1] == 0:
                    ordinal += 1
                context.clear()
                context.update(call_ordinal=ordinal,cycle=row.get('cycle'),pc=hex(pc),
                               insn=hex(row.get('insn',0)),actual_value=row.get('value'),
                               address=hex(row.get('address',0)),classification='source_setup_or_helper')
                if 1 <= ordinal <= BOUND:
                    g = golds[ordinal-1]
                    context['source_tuple'] = {k:g[k] for k in ('seed','op','vl','mode','sticky','vstart')}
                    context['expected_flags'] = g['flags']
                    if pair is not None:
                        op,i = pair
                        delta = 5 if op >= 4 else 0
                        if i == 9+delta:
                            context.update(classification='fflags',actual_flags=row.get('value'))
                        elif i == 8+delta:
                            context.update(classification='vstart',expected_vstart=0,actual_vstart=row.get('value'))
                    if pc in (spec['sites']['guard0'],spec['sites']['guard1']):
                        context.update(classification='guard',expected_guard=91,actual_guard=row.get('value'))
                    elif pc == spec['sites']['bits']:
                        k = row.get('address',0)-spec['symbols']['output']-1
                        if 0 <= k < 64:
                            actual = row.get('value',0)
                            bad = [dict(bit=8*k+b,expected_allowed=g['allowed'][8*k+b],actual=(actual>>b)&1)
                                   for b in range(8) if (actual>>b)&1 not in g['allowed'][8*k+b]]
                            context.update(classification='result_bits',result_byte=k,violations=bad)
            yield row
    try:
        result = _source.audit(observed(), spec, spike_vectors, abort)
    except BaseException as error:
        context['original_firstcause'] = repr(error)
        raise AuditError(dict(context)) from error
    require(result['target_calls']==BOUND and result['full_result_bit_checks']==358400
            and result['guard_checks']==1400,'Exact700 full oracle')
    result['status'] = 'FULL_ORIGINAL700_STRICT_ACCEPTED_NOT_FULL_PARENT'
    return result
