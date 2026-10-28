"""Check whole-call Prefill evidence without accepting scheduler-only logs."""
from check_native import check_log

SCOPE = ('PREFILL_SCOPE whole_call=1 admission=1 scatter=1 '
         'baseline=per_query_qbs')


def check_full_log(text, golden, q4):
    lines = text.splitlines()
    scopes = [line for line in lines if line.startswith('PREFILL_SCOPE')]
    if scopes != [SCOPE]:
        raise ValueError('Missing or ambiguous whole-call scope')
    caps = [i for i, line in enumerate(lines) if line.startswith('PREFILL_CAP')]
    if len(caps) != 1 or lines.index(SCOPE) >= caps[0]:
        raise ValueError('Whole-call scope must precede capability/trials')
    result = check_log(text, golden, q4)
    result.update(whole_call=True, admission_included=True, scatter_included=True,
                  scope='QBS per-query versus grouped Prefill entry including '
                        'admission and output scatter; not RVV or whole model')
    return result
