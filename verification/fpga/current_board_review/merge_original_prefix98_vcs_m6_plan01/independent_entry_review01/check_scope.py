"""Independent synthetic scope controls only; no ELF execution or live queries."""
import csv
import hashlib
import json
from pathlib import Path
import sys
import tempfile

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
import test_host as host

plan = json.loads((ROOT / 'prepared01/plan.json').read_text())
assert hashlib.sha256((ROOT / 'prepared01/plan.json').read_bytes()).hexdigest() == (
    'f97d3e2a933bfde527b1dd06b54f0055cb1bc2fca103d97308b1d0d45104b079')
spec = plan['spec']
model = host.c.source.model()
image = json.loads((Path(plan['image']) / 'image.json').read_text())
snapshot = json.loads((Path(image['snapshot']) / 'snapshot.json').read_text())
sys.path.insert(0, str(Path(snapshot['root']) / 'verification'))
from ara_verify.trace import validate_trace, is_vector_instruction


def rows(extra):
    count = order = 0
    inserted = False
    for row in host.fixture(spec, model):
        if extra and row['event'] == 'retire' and int(row['pc'], 16) == spec['exit_store']['pc']:
            assert not inserted
            inserted = True
            events = ['cvx_req', 'cvx_resp', 'retire'] if is_vector_instruction(int(extra['insn'], 16)) else ['retire']
            for event in events:
                x = {key: '0' for key in row}
                x.update(event=event, cycle=str(count), order=str(order), pc=f"{extra['pc']:x}", insn=extra['insn'])
                yield x
                count += 1
                order += event == 'retire'
        yield dict(row, cycle=str(count), order=str(order))
        count += 1
        order += row['event'] == 'retire'
    assert not extra or inserted


def main():
    output = HERE / 'scope_evidence.json'
    if output.exists():
        raise RuntimeError('Preserve independent evidence')
    lo, hi = spec['unused_ranges'][0]
    unused = next(r for r in spec['instructions'].values()
                  if lo <= r['pc'] < hi and host.c.is_rvv(int(r['insn'], 16))
                  and not r['text'].startswith(('vset', 'vle', 'vlm', 'vse')))
    cases = [('positive', None, None),
             ('unused_interior_vector', unused, 'Unused helper complete PC range'),
             ('selected_target_after_last_oracle', spec['routine'][8], 'Original13 order/phase'),
             ('capacity_interior_after_last_oracle', spec['capacity'][1], 'Capacity phase/once'),
             ('vlenb_after_last_oracle', spec['prelude'][-1], 'CSR outside original phase/once')]
    evidence = []
    for label, extra, expected in cases:
        with tempfile.TemporaryDirectory(dir=HERE, prefix='host_scope_') as folder:
            path = Path(folder) / 'synthetic.csv'
            stream = rows(extra)
            first = next(stream)
            with path.open('x', newline='') as file:
                writer = csv.DictWriter(file, fieldnames=list(first))
                writer.writeheader()
                writer.writerow(first)
                writer.writerows(stream)
            generic = validate_trace(path)
            try:
                with path.open() as file:
                    result = host.c.retirement(csv.DictReader(file), spec, model)
            except ValueError as error:
                if expected is None or expected not in str(error):
                    raise
                verdict = {'strict': 'REJECTED', 'reason': str(error)}
            else:
                assert expected is None
                assert result['target_hits'] == 98 and result['actual_output_scalar_loads'] == 50372
                verdict = {'strict': 'ACCEPTED_SYNTHETIC_POSITIVE', 'target_hits': result['target_hits'],
                           'fullcap_checks': result['fullcap_checks'], 'guards': result['guards']}
            evidence.append(dict(case=label, extra=extra, generic='VALID',
                                 retired=generic['retire_count'], **verdict))
            print(label, verdict, flush=True)
    with output.open('x') as file:
        json.dump(dict(kind='SYNTHETIC_HOST_SCOPE_NOT_DUT', cases=evidence,
                       script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()), file, indent=2)


if __name__ == '__main__':
    main()
