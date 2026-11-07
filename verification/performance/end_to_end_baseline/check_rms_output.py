"""Retain every fused-norm check and require guarded-output boundary evidence."""
import csv
import io

from audit import require
from check_projection_native import fields
import check_rms_norm as original


def check(text, prefill, decode):
    result = original.check(text, prefill, decode)
    records = [fields(line, 'RMS_OUTPUT_CHECK') for line in text.replace('\r','').splitlines()
               if line.startswith('RMS_OUTPUT_CHECK ')]
    require(len(records) == 1, 'Missing/duplicate output boundary summary')
    row = records[0]
    expected = dict(cases=155, vector_calls=110, empty_calls=5, scalar_fallbacks=40, errors=0)
    require(set(row) == set(expected) | {'digest'} and 0 <= row['digest'] < 1<<32 and
            all(row[k] == v for k,v in expected.items()), 'Output alias/IEEE/rounding/state checks failed')
    result.update(output_checks=row, candidate='Ordered sum plus guarded RVV fused output')
    return result


def signature(measured):
    # Exclude ISA/RTL time values, retaining geometry and observed final FCSR.
    return dict(cases=[{k:r[k] for k in ('phase','rows','width','outputs','fcsr')}
                       for r in measured['cases']], output_checks=measured['output_checks'],
                trials=measured['trials'], boundary_cases=measured['boundary_cases'],
                sum_cases=measured['sum_cases'], outputs_checked=measured['outputs_checked'])


def activity(text):
    result = original.check_activity(text)
    stores = [r for r in csv.DictReader(io.StringIO(text)) if r['event'] == 'alloc' and
              (int(r['insn'],16)&0x707f) == 0x6027]
    # 160 timed fused rows, 95 FRM/width, eight norm IEEE, 195 output-only strips.
    require(len(stores) == 458 and all(int(r['vstart']) == 0 and 1 <= int(r['vl']) <= 128 for r in stores),
            'Actual guarded-output vector stores/configuration differ')
    result['vector_output_store_allocations'] = len(stores)
    return result
