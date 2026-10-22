"""Unadmitted source template only. No file access, imports of workers, or CLI.

Future closed-run adapters must supply their own exact sealed base and actual
specification after terminal provenance/entry review. Never patch a live module.
"""


def require(value, reason):
    if not value:
        raise ValueError(reason)


def validate_shape(spec):
    config = spec['config']
    allowed = {'rvv_matrix_e8_m8': (8, 1024), 'rvv_matrix_e16_m8': (16, 512)}
    require(config['id'] in allowed and config['lmul'] == 'm8' and config['calls'] == 4095,
            'Exact full M8 source shape required')
    require((config['sew'], config['cap']) == allowed[config['id']], 'No width/capacity alias')


def target_required(insn, row, spec):
    target = spec['backend']['helpers'][f'op_{row["op"]}'][8]
    require(insn == target['insn'], 'Actual target differs from original helper encoding')
    if row['op'] == 19:
        require(insn == 0x38813c57 and insn & 127 == 0x57 and
                (insn >> 12) & 7 == 3 and insn >> 26 == 14,
                'Additional elision is restricted to exact original VSLIDEUP.VI')
        offset = (insn >> 15) & 31
        require(offset == 2, 'Original unsigned immediate2')
        if offset >= row['vl']:
            return False
    return row['vstart'] < row['vl']


def owner_contract(rows, spec):
    validate_shape(spec)
    require(len(rows) == 4095, 'No prefix or partition substitute')
    necessary = [target_required(spec['backend']['helpers'][f'op_{row["op"]}'][8]['insn'], row, spec)
                 for row in rows]
    targets = sum(necessary)
    return dict(compulsory_memory_owners=len(rows) * 5, required_target_owners=targets,
                required_op24_memory_targets=sum(row['op'] == 24 and row['vstart'] < row['vl'] for row in rows),
                elidable_target_owners=len(rows) - targets, minimum_required_owners=len(rows) * 5 + targets)


def make_types(sealed_base, spec):
    """Define local subclasses; do not assign into sealed_base or its globals."""
    validate_shape(spec)

    class Strict(sealed_base.Strict):
        def __init__(self, actual_spec, gold=None):
            require(actual_spec == spec, 'The admitted source spec must remain exact')
            super().__init__(actual_spec, gold)

        def consume(self, row):
            before = len(self.offloads)
            super().consume(row)
            if len(self.offloads) != before:
                item = self.offloads[-1]
                if item['kind'] == 'target':
                    item['required'] = target_required(item['insn'], self.gold[item['call']], self.spec)

    class OwnerObserver(sealed_base.OwnerObserver):
        def owner_coverage(self, ledger, gold):
            require([r['insn'] for r in ledger] == self.retvec, 'Actual retired offload ledger differs')
            index = 0
            owners, replays = [], []
            for order, insn in enumerate(self.arch):
                if index < len(ledger) and insn == ledger[index]['insn']:
                    item = dict(ledger[index], arch_order=order,
                                alloc=self.owner_alloc[order], done=self.owner_done[order])
                    require(item['alloc'] == item['done'], 'Owner alloc/done mismatch')
                    if item['kind'] == 'target':
                        expected = target_required(insn, gold['rows'][item['call']], spec)
                        require(item['required'] == expected, 'Target required differs from actual opcode/VL')
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
            contract = owner_contract(gold['rows'], spec)
            require(len(memories) == contract['compulsory_memory_owners'] and
                    len(targets) == len(gold['rows']) and
                    sum(r['required'] for r in targets) == contract['required_target_owners'],
                    'Natural helper owner scope differs')
            for call in range(len(gold['rows'])):
                per_call = [r for r in memories if r['call'] == call]
                require([r['helper_index'] for r in per_call] == [1, 2, 3, 4, 11] and
                        all(r['required'] for r in per_call), 'Missing/duplicate compulsory memory owner')
            return dict(contract, status='EVERY_NECESSARY_RETIRED_OWNER_COMPLETED',
                        required_alloff_target_owners=sum(target_required(
                            spec['backend']['helpers'][f'op_{row["op"]}'][8]['insn'], row, spec) and
                            not any(gold['masks'][row['mode']]) for row in gold['rows']),
                        harmless_configuration_replay_arch_orders=replays, owner_ledger=owners)

    return Strict, OwnerObserver


def check_final_coverage(coverage, rows, spec):
    """Replace only the old vstart-only aggregate assertion in a future audit."""
    for key, expected in owner_contract(rows, spec).items():
        require(coverage[key] == expected, 'Actual-model owner contract: ' + key)
