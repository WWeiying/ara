"""Offline bulk ITLB successor: independent CSR requests are not consumers."""
import argparse
from pathlib import Path
from types import FunctionType, SimpleNamespace
import collect_itlb_asid_exec_bulk as core

life, require = core.life, core.require
ROOT = life.OUT.parent.parent
WORDS = (0x00802773, 0x00f027f3)
WINDOW = ((0x800024d4, 0x00f027f3), (0x800024d8, 0x00302873),
          (0x800024dc, 0x95ca), (0x800024de, 0xeda8),
          (0x800024e0, 0xf1b0), (0x800024e2, 0xf5b4),
          (0x800024e4, 0xf9b8), (0x800024e6, 0xfdbc))


def reads(word):
    if word & 3 == 3:
        require(word in (0x00f027f3, 0x00302873), 'Foreign CSR consumer-window encoding')
        return {word >> 15 & 31}
    if word == 0x95ca:  # C.ADD a1,s2
        return {word >> 7 & 31, word >> 2 & 31}
    require(word in (0xeda8, 0xf1b0, 0xf5b4, 0xf9b8, 0xfdbc),
            'Foreign compressed consumer-window encoding')
    return {(word >> 7 & 7) + 8, (word >> 2 & 7) + 8}  # C.SD


def csr_lifecycle(rows, symbols):
    retired = [r for r in rows if r['event'] == 'retire']
    csr = [r for r in retired if int(r['insn'], 16) in WORDS]
    require(len(csr) == 6 and [int(r['insn'], 16) for r in csr] == list(WORDS) * 3,
            'Exact six readonly CSR reads required')
    starts, pending = [], {}
    requests = responses = 0
    for row in rows:
        event = row['event']
        if event == 'retire':
            continue
        require(event in ('arch_start', 'cvx_req', 'cvx_resp'), 'Foreign backend activity')
        require(int(row['trap']) == 0 and int(row['mem_rmask'], 16) ==
                int(row['mem_wmask'], 16) == 0, 'CSR exception/memory effect')
        tid, time = int(row['trans_id']), int(row['cycle'])
        if event == 'arch_start':
            word = int(row['insn'], 16)
            require(word in WORDS and tid not in pending and int(row['order']) == len(starts),
                    'Duplicate/live/foreign CSR start')
            record = dict(arch_seq=len(starts), trans_id=tid, word=word, start=time)
            starts.append(record)
            pending[tid] = record
        elif event == 'cvx_req':
            require(tid in pending and 'request' not in pending[tid] and
                    int(row['insn'], 16) == pending[tid]['word'] and time >= pending[tid]['start'],
                    'Missing/replayed/changed CSR request')
            pending[tid]['request'] = time
            requests += 1
        else:
            require(tid in pending and 'request' in pending[tid] and
                    time >= pending[tid]['request'], 'Orphan/duplicate/early CSR response')
            pending.pop(tid)['response'] = time
            responses += 1
    require(len(starts) == requests == responses == 6 and not pending, 'Incomplete CSR conservation')
    positions = {id(r): i for i, r in enumerate(retired)}
    for i, (start, retire) in enumerate(zip(starts, csr)):
        rd = 14 + i % 2
        require(start['word'] == int(retire['insn'], 16) and
                start['response'] <= int(retire['cycle']) and
                int(retire['pc'], 16) == 0x800024d0 + 4 * (i % 2) and
                int(retire['rd']) == rd and int(retire['rd_wdata'], 16) == 0 and
                not int(retire['trap']), 'CSR retire identity/value/window differs')
        begin = positions[id(retire)] + 1
        window = WINDOW[i % 2:]
        actual = retired[begin:begin + len(window)]
        require([(int(r['pc'], 16), int(r['insn'], 16)) for r in actual] == list(window),
                'Exact frozen consumer sequence differs')
        consumed = False
        for r in actual:
            require(not int(r['trap']), 'Trapped CSR consumer')
            if rd in reads(int(r['insn'], 16)):
                require(int(r['insn'], 16) == (0xf9b8 if rd == 14 else 0xfdbc) and
                        int(r['mem_wmask'], 16) == 0xff and int(r['mem_rmask'], 16) == 0 and
                        int(r['mem_addr'], 16) == symbols['itm_csr'] + 8 * ((i // 2) * 6 + 3 + i % 2) and
                        int(r['mem_wdata'], 16) == 0 and
                        int(r['cycle']) >= int(retire['cycle']), 'Real CSR consumer differs')
                start['consumer_cycle'] = int(r['cycle'])
                consumed = True
                break
            require(int(r['rd']) != rd, 'CSR result overwritten before consumer')
        require(consumed, 'Missing real CSR consumer')
        start.update(retire_cycle=int(retire['cycle']), retire_pc=retire['pc'], rd=rd)
    return dict(status='SIX_READONLY_CSR_TAGGED_RESPONSE_RETIRE_AND_REAL_CONSUMERS_EXACT',
                requests=6, responses=6, records=starts, vector_modifications=0,
                independent_next_start_is_not_retirement_deadline=True,
                consumer_issue_time_observed=False,
                architectural_consumer_values_checked=True)


def source_pins():
    book_path = core.bulk.old.shared.SOURCE
    book_sha = core.bulk.old.shared.SOURCE_SHA
    book = life.read_bound(book_path, book_sha)
    # Historical manifest keys are original relative source pathnames.
    pins = {str(book_path): book_sha}
    for rel in ('hardware/deps/cva6/core/cvxif_fu.sv',
                'hardware/deps/cva6/core/scoreboard.sv',
                'hardware/deps/cva6/core/commit_stage.sv', 'hardware/src/ara_dispatcher.sv'):
        path = ROOT / rel
        if rel == 'hardware/src/ara_dispatcher.sv':
            path = life.OUT / 'old-image-source-evidence-20261006-01/ara_dispatcher.sv'
        pins[str(path)] = book[str(ROOT / rel)]
    life.check(pins)
    return pins


def collect(prepared, seal, output):
    record = life.read_bound(prepared, seal)
    q = life.read_bound(Path(record['preflight']), record['preflight_seal'])
    extra = source_pins()
    for path in (Path(__file__).absolute(), Path(__file__).with_name('test_collect_itlb_asid_exec_bulk_csr.py').absolute(),
                 Path(record['output']).with_name(Path(record['output']).name + '-qualified') / 'failure.json'):
        extra = life.merge_pins(extra, {str(path): life.digest(path)})
    def save(path, value):
        if path.name == 'evidence-pins.json':
            value = life.merge_pins(value, extra)
            life.check(value)
        elif path.name == 'qualification.json':
            value = dict(value, input_pins=life.merge_pins(value['input_pins'], extra),
                         offline_successor='CSR independent requests; real consumers retained',
                         original_failure_preserved=True)
            life.check(value['input_pins'])
        return life.save(path, value)
    private_life = SimpleNamespace(**dict(life.__dict__, save=save))
    implementation = FunctionType(core.collect.__code__, dict(core.collect.__globals__,
        life=private_life, csr_lifecycle=lambda rows: csr_lifecycle(rows, q['symbols'])))
    implementation(prepared, seal, output)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepared', type=Path, required=True)
    parser.add_argument('--seal', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    collect(args.prepared.absolute(), args.seal, args.output.absolute())
