"""One constructed-prefix profile; never open captured CSV or change helpers."""
import cProfile
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import pstats
import sys
import time

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
D = HERE.parent / 'diagnostic01'
sys.path.insert(0, str(D))
import diagnostic as d


def save(name, value):
    with (HERE / name).open('x') as f:
        json.dump(value, f, indent=2)
        f.write('\n')
        f.flush()
        os.fsync(f.fileno())


started = time.monotonic()
spec = d.base.specification()
sys.modules['checker'] = d.base
records = d.load('short_profile_real_fixture', d.OLD / 'host_records.py')
d.base.model()
model_ready = time.monotonic()
builder = records.Builder(spec)
rows = []
entries = 0
entry_pc = spec['backend']['helpers']['op_0'][0]['pc']
for row in builder.protocol_rows(builder.records()):
    rows.append(row)
    if row['event'] == 'retire' and int(row['pc'], 16) == entry_pc:
        entries += 1
        if entries == 5:
            break
assert entries == 5
fixture_ready = time.monotonic()


class Reader:
    fieldnames = d.FIELDS

    def __iter__(self):
        return iter(rows)


prefix = d.Prefix(spec)
consumer_ready = time.monotonic()
profile = cProfile.Profile()
profile.enable()
for row in prefix.observer.rows(Reader()):
    prefix.consume(row)
result = prefix.partial()
profile.disable()
ended = time.monotonic()
assert result['completed_calls_with_data_and_owners'] == 4
profile.dump_stats(str(HERE / 'consumer.pstats'))
stats = pstats.Stats(profile)
functions = []
for (filename, line, function), (primitive, calls, own, cumulative, callers) in stats.stats.items():
    functions.append(dict(file=filename, line=line, function=function,
                          primitive_calls=primitive, calls=calls,
                          self_s=own, cumulative_s=cumulative))
functions.sort(key=lambda x: x['cumulative_s'], reverse=True)
with (HERE / 'consumer_top.txt').open('x') as f:
    stats.stream = f
    stats.strip_dirs().sort_stats('cumulative').print_stats(45)
pins = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in
        (Path(__file__), D / 'diagnostic.py', d.OLD / 'checker.py', d.OLD / 'host_records.py')}
save('result.json', dict(status='CONSTRUCTED_SHORT_PROFILE_ONLY_NOT_RAW_DIAGNOSIS',
    actual_csv_reads=0, reference_reads=0, full4095_stream_test=False,
    rows=len(rows), completed_calls=4, calls_entered=entries,
    original_model_initialization_s=model_ready-started,
    fixture_construction_s=fixture_ready-model_ready,
    strict_initialization_s=consumer_ready-fixture_ready,
    profiled_consumer_s=ended-consumer_ready,
    total_s=ended-started, functions=functions, source_pins=pins))
print('CONSTRUCTED_SHORT_PROFILE', len(rows), ended-started, flush=True)
