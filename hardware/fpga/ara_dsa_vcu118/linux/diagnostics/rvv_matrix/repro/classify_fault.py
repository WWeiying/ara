"""Classify recorded replay diagnostics without inferring unprinted data or RTL state."""
import re


FIELDS = {
    'BEGIN': {'unmapped', 'store', 'boundary', 'mode', 'split'},
    'CONTEXT': {'sig', 'code', 'address', 'expected_address', 'pc', 'expected_pc',
                'vstart', 'expected_start', 'vl', 'vtype'},
    'RETURN': {'status', 'faults', 'expected_faults', 'handler_errors'},
    'CHECK': {'errors'},
}


def parse_fields(line, kind):
    pairs = []
    for token in line.split()[1:]:
        if not re.fullmatch(r'\w+=\d+', token):
            raise ValueError('Malformed replay field')
        pairs.append(token.split('='))
    fields = {key: int(value) for key, value in pairs}
    if len(fields) != len(pairs) or not FIELDS[kind] <= fields.keys():
        raise ValueError('Duplicate or missing replay field')
    return fields


def classify(output):
    trials = []
    active = None
    for line in output.splitlines():
        match = re.match(r'^RVV_FAULT_(BEGIN|CONTEXT|RETURN|CHECK) ', line)
        if not match:
            continue
        kind = match[1]
        fields = parse_fields(line, kind)
        if kind == 'BEGIN':
            if active is not None:
                raise ValueError('New replay trial before prior CHECK')
            active = dict(trigger=fields, contexts=[], completed=False)
            trials.append(active)
        elif active is None:
            raise ValueError('Replay record without BEGIN')
        elif kind == 'CONTEXT':
            if 'returned' in active:
                raise ValueError('Signal context after RETURN')
            active['contexts'].append(fields)
        elif kind == 'RETURN':
            if 'returned' in active:
                raise ValueError('Duplicate RETURN')
            active['returned'] = fields
        else:
            if 'returned' not in active:
                raise ValueError('CHECK without RETURN')
            returned = active['returned']
            active.update(completed=True, errors=fields['errors'],
                          fault_count_mismatch=returned['faults'] != returned['expected_faults'],
                          unexpected_fault=returned['expected_faults'] == 0 and returned['faults'] > 0,
                          returned_vstart_nonzero=returned['status'] != 0,
                          handler_errors=returned['handler_errors'])
            mismatches = []
            for context in active['contexts']:
                mismatches.append({key: dict(actual=context[key], expected=context[expected])
                                   for key, expected in (('address', 'expected_address'),
                                                         ('pc', 'expected_pc'), ('vstart', 'expected_start'))
                                   if context[key] != context[expected]})
            active['context_mismatches'] = mismatches
            # A segmented fault address may legally differ by a field offset;
            # report raw differences here, not a general architectural verdict.
            active['raw_context_differences_only'] = True
            active = None
    return dict(trials=trials, completed=sum(t['completed'] for t in trials),
                incomplete=sum(not t['completed'] for t in trials),
                original_failure_equivalence_proven=False, internal_rtl_root_cause_proven=False)
