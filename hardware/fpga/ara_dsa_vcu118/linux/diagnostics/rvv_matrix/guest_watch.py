"""Transport-independent batch observer with preserved no-retirement evidence.

The serial adapter supplies bytes, monotonic time and a two-snapshot callback.
This module never sends interrupts, resets, or commands to the guest.
"""
import codecs
from guest_batch import Parser


def no_retirement(samples):
    if len(samples) != 2:
        raise ValueError('Expected two live snapshots')
    first, last = samples
    if first['identity'] != last['identity']:
        raise ValueError('Snapshot identities differ')
    return (last['core']['cycles'] - first['core']['cycles'] >
            first['identity']['frequency_hz'] * 2 and
            all(first['core'][key] == last['core'][key]
                for key in ('retired', 'trap_count', 'last_pc', 'head_pc')) and
            all(not s['watchdog_snapshot'] and s['live']['flags'] == 0
                for s in samples))


class Watch:
    def __init__(self, manifest, run_id, now, snapshots,
                 diagnostic_seconds=120, preparation_seconds=60, drain=None):
        self.parser = Parser(manifest, run_id)
        self.decoder = codecs.getincrementaldecoder('utf-8')('replace')
        self.buffer = ''
        self.started = now
        self.snapshots = snapshots
        self.drain = drain
        self.diagnostic_seconds = diagnostic_seconds
        self.preparation_seconds = preparation_seconds
        self.checked = False
        self.terminal = False

    @property
    def report(self):
        return self.parser.report

    def fail(self, reason, stalled=False):
        if self.parser.phase == 'running':
            self.report['results'][-1].update(
                status='stalled' if stalled else 'incomplete', error=reason)
        self.report.update(state='scene_preserved_incomplete', error=reason)
        self.terminal = True

    def feed(self, chunk, now):
        if self.terminal:
            raise ValueError('Observer is terminal')
        self.buffer += self.decoder.decode(chunk)
        while '\n' in self.buffer:
            line, self.buffer = self.buffer.split('\n', 1)
            before = self.parser.phase
            try:
                self.parser.feed(line + '\n')
            except ValueError as exc:
                self.fail('Protocol error: ' + str(exc))
                return
            if 'Kernel panic' in line or 'Oops:' in line:
                self.fail('Kernel scene preserved')
                return
            after = self.parser.phase
            if after != before:
                if before == 'running' and after == 'idle':
                    self.report['results'][-1]['seconds'] = now - self.started
                self.started = now
                self.checked = False
            if after in ('done', 'aborted'):
                self.terminal = True
                if self.buffer.strip():
                    # UART prompts after terminal protocol are not case results.
                    self.report['terminal_uart_suffix'] = self.buffer
                return

    def tick(self, now):
        if self.terminal:
            return
        elapsed = now - self.started
        if self.parser.phase == 'running':
            case = self.parser.manifest['cases'][self.parser.index]
            timeout = case.get('timeout_seconds', 180)
            # Short cases must collect progress evidence before expiring too.
            if elapsed >= min(self.diagnostic_seconds, timeout) and not self.checked:
                self.checked = True
                index = self.parser.index
                try:
                    samples = self.snapshots()
                    # A synchronous diagnostic can outlive the case being observed.
                    if self.drain is not None:
                        self.drain(self)
                    if self.terminal or self.parser.index != index or self.parser.phase != 'running':
                        self.report.setdefault('diagnostic_history', []).append(dict(
                            name=case['name'], snapshots=samples, stale_case=True))
                        return
                    stalled = no_retirement(samples)
                    self.report['progress_diagnosis'] = dict(
                        stalled=stalled, snapshots=samples,
                        name=case['name'])
                except Exception as exc:
                    self.fail('Progress telemetry failed: ' + str(exc))
                    return
                if stalled:
                    self.fail('Confirmed no retirement; scene preserved', stalled=True)
                    return
            if elapsed >= timeout:
                self.fail('Observation expired; no interrupt or reset sent')
        elif elapsed >= self.preparation_seconds:
            self.fail('Guest preparation or protocol observation expired; no case assumed')
