"""POSTPROCESS_ONLY: one closed CSV, fast3.9, hard1800s, no DUT acceptance."""
import csv
import json
import os
from pathlib import Path
import signal
import sys
import time

sys.dont_write_bytecode = True
assert sys.version_info[:2] == (3, 9), 'Reviewed fastCPython3.9 only'
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'verification_performance02'))
import sidecar as fast
old = fast.original
EXPECTED_BYTES = 296607084
HARD_SECONDS = 1800
INTERNAL_SECONDS = 1790
PREDICTED_FINISH_LIMIT = 1650
ROW_INTERVAL = 65536
WARMUP_BYTES = 32 * 1024 * 1024
aborted = False


class BudgetStop(ValueError):
    pass


class Forecast:
    def __init__(self, total):
        self.total = total
        self.baseline = None
        self.consecutive_over = 0

    def update(self, byte_count, elapsed):
        old.need(0 <= byte_count <= self.total and elapsed >= 0, 'Forecast input range')
        result = dict(warmup_excluded=True, baseline=self.baseline,
                      predicted_finish_s=None, remaining_s=None,
                      consecutive_over=self.consecutive_over, stop=False)
        if byte_count < WARMUP_BYTES:
            return result
        if self.baseline is None:
            self.baseline = dict(bytes=byte_count, elapsed_s=elapsed)
            result['baseline'] = dict(self.baseline)
            return result
        delta_bytes = byte_count - self.baseline['bytes']
        delta_time = elapsed - self.baseline['elapsed_s']
        old.need(delta_bytes > 0 and delta_time > 0, 'Forecast nonpositive progress')
        remaining = (self.total - byte_count) * delta_time / delta_bytes
        predicted = elapsed + remaining
        if byte_count < self.total and predicted > PREDICTED_FINISH_LIMIT:
            self.consecutive_over += 1
        else:
            self.consecutive_over = 0
        result.update(bytes_per_s=delta_bytes/delta_time, remaining_s=remaining,
                      predicted_finish_s=predicted, consecutive_over=self.consecutive_over,
                      stop=self.consecutive_over >= 2)
        return result


def compact(prefix):
    if prefix is None:
        return None
    s, o = prefix.state, prefix.observer
    active = None
    if s.active:
        active = {k: v for k, v in s.active.items() if k != 'reads'}
        active['oracle_reads_seen'] = len(s.active['reads'])
    return dict(rows=s.rows, retired=s.retired, closed_calls=prefix.closed_calls,
        calls_entered=len(s.calls), active_call=active, last_cycle=s.cycle,
        active_phase=dict(helper=s.helper, next_helper_index=s.index,
            output_initializer_index=s.init_index, mask_store_index=s.mask_index,
            seed_store_index=s.seed_index, body_entered=s.body_entered, source_exited=s.exited),
        fresh_bytes={k: len(v) for k, v in s.fresh.items()},
        lastvalidrecord=prefix.last, last_watchdog_progress=prefix.last_progress,
        pending_cvx=dict(o.pending), pending_uop=dict(o.uops),
        generic_counts=dict(o.count), before_sha256=o.before.hexdigest(),
        after_sha256=o.after.hexdigest(), max_event_gap=prefix.max_event,
        max_watchdog_progress_gap=prefix.max_progress,
        whole4095_accepted=False, architectural_acceptance=False,
        state_scope='CHECKED_PROGRESS_ONLY_NOT_PREFIX_ACCEPTANCE')


class Checkpoints:
    def __init__(self, path, prefix, streamstate, started):
        self.file = path.open('x')
        self.prefix = prefix
        self.streamstate = streamstate
        self.started = started
        self.forecast = Forecast(EXPECTED_BYTES)
        self.last_checkpoint_rows = 0

    def boundary(self):
        s, o = self.prefix.state, self.prefix.observer
        elapsed = time.monotonic() - self.started
        if s.rows % 4096 == 0:
            if aborted or elapsed >= INTERNAL_SECONDS:
                raise BudgetStop('Abort/internal1790s postprocessing deadline')
        if s.rows - self.last_checkpoint_rows < ROW_INTERVAL:
            return
        old.need(o.count['unmodified_delivered_rows'] == s.rows
                 and o.before.digest() == o.after.digest(), 'Checkpoint not losslessly delivered')
        estimate = self.forecast.update(self.streamstate.bytes, elapsed)
        snapshot = compact(self.prefix)
        record = dict(scope='POSTPROCESS_ONLY', rows=s.rows,
            processed_bytes=self.streamstate.bytes, elapsed_s=elapsed,
            closed_calls=self.prefix.closed_calls, last_cycle=s.cycle,
            active_phase=snapshot['active_phase'], active_original_call=(
                s.active['original_ordinal'] if s.active else None), forecast=estimate,
            lossless_rows_delivered=o.count['unmodified_delivered_rows'])
        self.file.write(json.dumps(record, separators=(',', ':')) + '\n')
        self.file.flush()
        os.fsync(self.file.fileno())
        self.last_checkpoint_rows = s.rows
        if estimate['stop']:
            raise BudgetStop('Two post-warmup checkpoints predict finish beyond1650s')

    def close(self):
        self.file.close()


class BoundaryReader:
    """Called after fast transport's after-digest, before fetching another row."""
    def __init__(self, reader, checkpoints):
        self.reader = reader
        self.fieldnames = reader.fieldnames
        self.checkpoints = checkpoints

    def __iter__(self):
        iterator = iter(self.reader)
        while True:
            self.checkpoints.boundary()
            try:
                row = next(iterator)
            except StopIteration:
                return
            yield row


def execute():
    out = HERE / 'run01'
    out.mkdir()
    started = time.monotonic()
    prefix = checkpoint = None
    state = old.StreamState()
    before = None
    try:
        entry = old.read(HERE / 'ENTRY.json')
        for path, digest in entry['pins'].items():
            old.need(old.sha(path) == digest, 'Entry pin drift ' + path)
        spec, _ = old.inputs()
        before = old.stat(old.TRACE)
        old.need(before['size'] == EXPECTED_BYTES, 'Exact original closed CSV bytes')
        old.save(out / 'inputs.json', dict(scope='POSTPROCESS_ONLY', pins=entry['pins'],
            entry_sha256=old.sha(HERE / 'ENTRY.json'), csv_before=before,
            hard_seconds=HARD_SECONDS, internal_seconds=INTERNAL_SECONDS,
            interpreter=sys.executable, version=sys.version, max_scans=1))
        prefix = fast.Prefix(spec)
        checkpoint = Checkpoints(out / 'progress.jsonl', prefix, state, started)
        with old.TRACE.open('rb') as stream:
            decoded = old.ContextReader(csv.DictReader(state.lines(stream), strict=True), state)
            reader = BoundaryReader(decoded, checkpoint)
            for row in prefix.observer.rows(reader):
                prefix.consume(row)
        result = prefix.partial()
        after = old.stat(old.TRACE)
        old.need(state.bytes == before['size'] and before == after, 'Closed CSV stat/byte drift')
        for path, digest in entry['pins'].items():
            old.need(old.sha(path) == digest, 'Post-pin drift ' + path)
        old.need(not aborted and time.monotonic()-started < HARD_SECONDS, 'Late abort/hard1800s deadline')
        result.update(scope='POSTPROCESS_ONLY', budget_s=1800,
            csv_before=before, csv_after=after, csv_bytes=state.bytes,
            csv_sha256=state.hash.hexdigest(), raw_hash_computed_in_same_pass=True,
            semantic_passes=1, EOF_reached=True, pins_unchanged=True,
            elapsed_s=time.monotonic()-started, original_timeout_preserved=True,
            old_diagnostic_failure_preserved=True, compact_checked_state=compact(prefix))
        old.save(out / 'result.json', result)
        return 0
    except BaseException as error:
        old.save(out / 'firstcause.json', dict(status='DIAGNOSTIC_STOPPED_NOT_ACCEPTED',
            scope='POSTPROCESS_ONLY', budget_s=1800, cause=type(error).__name__+': '+str(error),
            row=state.attempted or (prefix.current_row if prefix else None),
            physical_line=state.line, raw_record_preview=state.raw_preview,
            compact_checked_state=compact(prefix), bytes_hashed=state.bytes,
            sha256_of_only_bytes_read=state.hash.hexdigest(), full_file_hash=False,
            csv_before=before, csv_after=old.stat(old.TRACE) if before else None,
            elapsed_s=time.monotonic()-started, original_timeout_preserved=True,
            old_diagnostic_failure_preserved=True, no_retry=True))
        return 1
    finally:
        if checkpoint:
            checkpoint.close()


if __name__ == '__main__':
    def stop(signum, frame):
        global aborted
        aborted = True
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    raise SystemExit(execute())
