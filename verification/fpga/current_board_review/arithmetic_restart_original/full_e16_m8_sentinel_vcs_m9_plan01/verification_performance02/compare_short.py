"""One interpreter: old/new differential and unprofiled constructed timings."""
import hashlib
import json
import os
from pathlib import Path
import statistics
import sys
import time

import sidecar as fast
d = fast.original
HERE = Path(__file__).resolve().parent
OUT = HERE / sys.argv[1]
OUT.mkdir()


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(name, value):
    with (OUT / name).open('x') as f:
        json.dump(value, f, indent=2)
        f.write('\n')
        f.flush()
        os.fsync(f.fileno())


def fixture_digest(rows):
    return hashlib.sha256(json.dumps(rows, separators=(',', ':')).encode()).hexdigest()


class Reader:
    fieldnames = d.FIELDS

    def __init__(self, rows):
        self.data = rows

    def __iter__(self):
        return iter(self.data)


started = time.monotonic()
entry = d.read(d.HERE / 'ENTRY.json')
pins = dict(entry['pins'])
pins.update({str(p): sha(p) for p in HERE.glob('*.py')})
for p, digest in pins.items():
    assert sha(p) == digest, 'Pre-pin drift ' + p
spec = d.base.specification()
d.base.model()
sys.modules['checker'] = d.base
records = d.load('differential_original_builder', d.OLD / 'host_records.py')
builder = records.Builder(spec)
rows = []
entries = 0
pc = spec['backend']['helpers']['op_0'][0]['pc']
for row in builder.protocol_rows(builder.records()):
    rows.append(row)
    if row['event'] == 'retire' and int(row['pc'], 16) == pc:
        entries += 1
        if entries == 5:
            break
assert entries == 5 and len(rows) == 10994
fixture_hash = fixture_digest(rows)
setup_s = time.monotonic() - started


def run(cls, data):
    state = cls(spec)
    t = time.monotonic()
    for row in state.observer.rows(Reader(data)):
        state.consume(row)
    result = state.partial()
    return state, result, time.monotonic() - t


samples = []
first = {}
for name in ('old', 'new', 'new', 'old', 'old', 'new'):
    p, r, elapsed = run(d.Prefix if name == 'old' else fast.Prefix, rows)
    samples.append(dict(mode=name, elapsed_s=elapsed, rows=p.state.rows))
    first.setdefault(name, (p, r))
old, new = first['old'][0], first['new'][0]
assert first['old'][1] == first['new'][1], 'Full diagnostic result differs'
assert vars(old.state) == vars(new.state), 'Complete Strict state differs'
assert {k: v for k, v in vars(old).items() if k not in ('state', 'observer')} == {
    k: v for k, v in vars(new).items() if k not in ('state', 'observer')}, 'Prefix state differs'
assert {k: v for k, v in vars(old.observer).items() if k not in ('before', 'after')} == {
    k: v for k, v in vars(new.observer).items() if k not in ('before', 'after')}, 'Owner/protocol state differs'
digests = [p.observer.before.hexdigest() for p in (old, new)] + [
    p.observer.after.hexdigest() for p in (old, new)]
assert len(set(digests)) == 1
tests = ['full_result_equal', 'full_mutable_Strict_equal', 'full_owner_protocol_equal',
         'full_prefix_equal', 'all_before_after_digests_equal']


def rejects_both(name, data):
    exceptions = []
    for cls in (d.Prefix, fast.Prefix):
        try:
            run(cls, data)
        except (ValueError, AssertionError, KeyError) as error:
            exceptions.append(type(error).__name__)
        else:
            raise AssertionError(name + ' accepted')
    assert exceptions[0] == exceptions[1], name + ' rejection class changed'
    tests.append(name)


def renumber(data):
    count = 0
    result = []
    for row in data:
        row = dict(row)
        if row['event'] == 'retire':
            row['order'] = str(count)
            count += 1
        result.append(row)
    return result


out = spec['backend']['symbols']['out']
for name, offset, bit in [('front_guard', 0, 0), ('tail4_result', 1024, 0), ('rear_guard', 1024, 16)]:
    data = [dict(row) for row in rows]
    row = next(r for r in data if r['event'] == 'retire' and int(r['mem_rmask'], 16)
               and int(r['mem_addr'], 16) == out + offset)
    row['rd_wdata'] = f'{int(row["rd_wdata"], 16) ^ (1 << bit):016x}'
    rejects_both(name, data)
init_pc = spec['init_stores'][0][0]
rejects_both('missing_fresh_store', renumber([r for r in rows if not (
    r['event'] == 'retire' and int(r['pc'], 16) == init_pc and int(r['mem_wmask'], 16))]))
alloc = next(r['order'] for r in rows if r['event'] == 'uop_alloc')
rejects_both('deleted_required_owner_pair', [r for r in rows if not (
    r['event'] in ('uop_alloc', 'uop_done') and r['order'] == alloc)])
rejects_both('missing_prior_output_read', renumber([r for r in rows if not (
    r['event'] == 'retire' and int(r['mem_rmask'], 16) and int(r['mem_addr'], 16) == out)]))
rejects_both('first_record_dropped', rows[1:])
rejects_both('first_record_duplicated', [rows[0]] + rows)
rejects_both('first_records_reordered', [rows[1], rows[0]] + rows[2:])

# Every field is protected across delivery, including transport-only fields.
for field in d.FIELDS:
    for observer_cls in (d.base.OwnerObserver, fast.OwnerObserver):
        row = dict(rows[0])
        observer = observer_cls(d.protocol)
        iterator = observer.rows(Reader([row]))
        next(iterator)
        row[field] += 'x'
        try:
            next(iterator)
        except AssertionError:
            pass
        else:
            raise AssertionError('Undetected delivery mutation ' + field)
    tests.append('delivery_field_mutation_' + field)
for change in ('missing', 'extra', 'reordered', 'nonstring'):
    for observer_cls in (d.base.OwnerObserver, fast.OwnerObserver):
        row = dict(rows[0])
        observer = observer_cls(d.protocol)
        iterator = observer.rows(Reader([row]))
        if change == 'nonstring':
            row['cycle'] = 0
        else:
            next(iterator)
            if change == 'missing':
                del row['pc']
            elif change == 'extra':
                row['unexpected'] = '0'
            else:
                row['cycle'] = row.pop('cycle')
        try:
            next(iterator)
        except AssertionError:
            pass
        else:
            raise AssertionError('Undetected row structure mutation ' + change)
    tests.append('delivery_structure_' + change)
for cls in (d.base.Strict, fast.Strict):
    state = cls.__new__(cls)
    state.memory = {100: 0, 101: 91, 102: 255}
    assert [state.value(i, 1) for i in (100, 101, 102)] == [0, 91, 255]
    for addr, size in ((99, 1), (100, 8)):
        try:
            state.value(addr, size)
        except ValueError as error:
            assert str(error) == 'Missing actual initialized byte'
        else:
            raise AssertionError('Missing initialized byte was defaulted')
tests.append('size1_values_and_missing_size1_size8_rejected')
bins = fast.Prefix.__new__(fast.Prefix)
bins.bins = {}
first_bin = bins.event_bin(0)
first_bin['retire'] += 1
assert bins.event_bin(0) is first_bin and first_bin['retire'] == 1
assert bins.event_bin(1) is not first_bin and set(bins.bins) == {0, 1}
tests.append('existing_counter_reused_new_bin_independent')
assert fixture_digest(rows) == fixture_hash
for p, digest in pins.items():
    assert sha(p) == digest, 'Post-pin drift ' + p
timings = {name: [s['elapsed_s'] for s in samples if s['mode'] == name] for name in ('old', 'new')}
medians = {name: statistics.median(values) for name, values in timings.items()}
save('result.json', dict(status='SHORT_CONSTRUCTED_DIFFERENTIAL_PASS_NOT_RAW_ACCEPTANCE',
    interpreter=sys.executable, version=sys.version, actual_csv_reads=0, actual_reference_reads=0,
    cProfile=False, full4095_stream=False, fixture_rows=len(rows), fixture_sha256=fixture_hash,
    calls_entered=5, completed_calls=4, setup_s=setup_s, samples=samples,
    median_consumer_s=medians, local_old_over_new=medians['old']/medians['new'],
    all_four_delivery_digests=digests, strict_rows=old.state.rows,
    observer_rows=old.observer.count['rows'], delivered_rows=old.observer.count['unmodified_delivered_rows'],
    owner_summary=first['old'][1]['generic'], tests=tests, tests_count=len(tests),
    pins_unchanged=True, pins=pins, total_s=time.monotonic()-started))
print('SHORT_DIFFERENTIAL_PASS', sys.version.split()[0], medians, flush=True)
