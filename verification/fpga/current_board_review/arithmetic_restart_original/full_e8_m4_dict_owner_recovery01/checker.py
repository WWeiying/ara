"""Closed-trace successor: only exact slide-up VI owner eligibility changes."""
import csv
import importlib.util
from pathlib import Path
import sys
sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
OLD = HERE.parent / 'full_e8_m4_dict_vcs_m9_plan01'
module = importlib.util.spec_from_file_location('e8m4_sealed_checker', OLD / 'checker.py')
base = importlib.util.module_from_spec(module)
sys.modules[module.name] = base
module.loader.exec_module(base)
require = base.require


def target_required(insn, row, spec):
    target = spec['backend']['helpers'][f'op_{row["op"]}'][8]
    require(insn == target['insn'], 'Actual target encoding differs from original helper')
    if row['op'] == 19:
        require(insn == 0x38813c57 and insn & 127 == 0x57 and
                (insn >> 12) & 7 == 3 and insn >> 26 == 14,
                'Only original VSLIDEUP.VI may use the additional elision')
        offset = (insn >> 15) & 31
        require(offset == 2, 'Original unsigned immediate2')
        if offset >= row['vl']:
            return False
    return row['vstart'] < row['vl']


class Strict(base.Strict):
    def consume(self, row):
        before = len(self.offloads)
        super().consume(row)
        if len(self.offloads) != before:
            item = self.offloads[-1]
            if item['kind'] == 'target':
                item['required'] = target_required(item['insn'], self.gold[item['call']], self.spec)


class OwnerObserver(base.OwnerObserver):
    def __init__(self, protocol, spec):
        super().__init__(protocol)
        self.source_spec = spec

    def owner_coverage(self, ledger, gold):
        # Preserve the sealed one-to-one architecture/retirement pairing and replay rule.
        require([r['insn'] for r in ledger] == self.retvec, 'Actual retired offload ledger differs')
        index = 0
        owners, replays = [], []
        for order, insn in enumerate(self.arch):
            if index < len(ledger) and insn == ledger[index]['insn']:
                item = dict(ledger[index], arch_order=order,
                            alloc=self.owner_alloc[order], done=self.owner_done[order])
                require(item['alloc'] == item['done'], 'Owner alloc/done mismatch')
                if item['kind'] == 'target':
                    expected = target_required(insn, gold['rows'][item['call']], self.source_spec)
                    require(item['required'] == expected, 'Target required flag differs from actual opcode/VL')
                if item['required']:
                    require(item['alloc'] > 0, 'Missing necessary architectural owner ' + str(item))
                if item['kind'] == 'configuration':
                    require(item['alloc'] == 0, 'Configuration cannot own backend data uop')
                owners.append(item)
                index += 1
            else:
                csr, funct3, rs1, rd = insn >> 20, (insn >> 12) & 7, (insn >> 15) & 31, (insn >> 7) & 31
                replay = (insn & 127 == 0x73 and funct3 in (2, 3) and rs1 == 0 and
                          csr in (8, 9, 10, 15, 0xc20, 0xc21, 0xc22) and
                          (rd == 0 or order > 0 and insn == self.arch[order - 1]))
                require(replay and self.owner_alloc[order] == self.owner_done[order] == 0,
                        'Non-configuration replay or replay backend owner')
                replays.append(order)
        require(index == len(ledger), 'Missing architectural offload owner')
        memories = [r for r in owners if r['kind'] == 'memory']
        targets = [r for r in owners if r['kind'] == 'target']
        required = [target_required(self.source_spec['backend']['helpers'][f'op_{r["op"]}'][8]['insn'],
                                   r, self.source_spec) for r in gold['rows']]
        expected_targets = sum(required)
        require(len(memories) == len(gold['rows']) * 5 and len(targets) == len(gold['rows']) and
                sum(r['required'] for r in targets) == expected_targets, 'Natural helper owner scope differs')
        for call in range(len(gold['rows'])):
            per_call = [r for r in memories if r['call'] == call]
            require([r['helper_index'] for r in per_call] == [1, 2, 3, 4, 11] and
                    all(r['required'] for r in per_call), 'Missing/duplicate per-call compulsory memory owner')
        return dict(status='EVERY_NECESSARY_RETIRED_OWNER_COMPLETED',
            compulsory_memory_owners=len(memories), required_target_owners=expected_targets,
            required_alloff_target_owners=sum(needed and not any(gold['masks'][r['mode']])
                for needed, r in zip(required, gold['rows'])),
            elidable_target_owners=len(targets) - expected_targets,
            minimum_required_owners=len(memories) + expected_targets,
            harmless_configuration_replay_arch_orders=replays, owner_ledger=owners)


def audit(path, spec, abort):
    base.common.image_context(Path(base.read(OLD / 'reset_profile.json')['image']).parent)
    protocol = sys.modules['ara_verify.trace']
    state = Strict(spec)
    observer = OwnerObserver(protocol, spec)
    with Path(path).open(newline='') as stream:
        for row in observer.rows(csv.DictReader(stream)):
            if state.rows % 4096 == 0:
                require(not abort.is_set(), 'Late abort during full4095 checks')
            try:
                state.consume(row)
            except Exception as error:
                raise ValueError(f'CSV firstcause row={state.rows} call={state.active["original_ordinal"] if state.active else None} '
                                 f'cycle={row.get("cycle")} event={row.get("event")} pc={row.get("pc")}: {error}') from error
    generic = observer.finish()
    base.mature.protocol_presence(generic)
    strict = state.finish()
    coverage = observer.owner_coverage(state.offloads, dict(rows=state.gold, masks=[state.gold[i]['mask'] for i in (0, 3, 6)]))
    require((strict['rows'], strict['retired'], strict['last_cycle']) ==
            (generic['rows'], generic['retire_count'], generic['last_cycle']), 'Generic/strict full trace counts differ')
    op24 = sum(x['op'] == 24 and x['vstart'] < x['vl'] for x in state.gold)
    require(op24 == 117 and coverage['compulsory_memory_owners'] == 20475 and
            coverage['required_target_owners'] == 2592 and coverage['minimum_required_owners'] == 23067,
            'Exact corrected original owner scope')
    coverage['required_op24_memory_targets'] = op24
    require(not abort.is_set(), 'Abort before strict result')
    return dict(strict=strict, generic=generic, owner_coverage=coverage,
                actual_csv_sha256=base.sha(path), strict_csv_parses=1)
