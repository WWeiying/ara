"""Identical ordinary linker rules; report, rather than conceal, layout effects."""
import re


def require(value, message):
    if not value:
        raise ValueError(message)


def script(template):
    start = template.index('  .text : {')
    end = template.index('  .data :')
    # Remove predecessor review padding on BOTH arms; retain normal object order.
    return (template[:start] + '  .text : {\n    *(.text.init)\n    *(.text)\n'
            '    *(.text.*)\n  } > L2\n\n' + template[end:].split('\nASSERT(', 1)[0] + '\n')


def compare(a, b, original, old_layout):
    for elf in (a, b):
        sections = elf.allocated()
        require(min(s['address'] for s in sections) == 0x80000000 and
                max(s['address'] + s['bytes'] for s in sections) < 0x81000000 - 65536,
                'L2 extent exceeds stack reserve')
    data = {}
    for name, row in old_layout['objects_and_tensor_symbols'].items():
        if name not in a.symbols or name not in b.symbols:
            require(not name.startswith('attention_'), 'Missing real tensor: ' + name)
            data[name] = dict(baseline_present=name in a.symbols, candidate_present=name in b.symbols)
            continue
        aa, bb = a.symbols[name], b.symbols[name]
        proof = dict(baseline_address=aa['address'], candidate_address=bb['address'],
                     baseline_size=aa['size'], candidate_size=bb['size'])
        extent = row.get('payload_compared_bytes')
        if name.startswith('attention_'):
            require(aa['size'] == bb['size'] == original.symbols[name]['size'] and extent is not None and
                    a.payload(name, extent) == b.payload(name, extent) == original.payload(name, extent),
                    'Original tensor/gold payload: ' + name)
            proof.update(original_payload_bytes=extent, original_payload_equal=True)
        data[name] = proof
    functions = {}
    for name in sorted(a.symbols.keys() | b.symbols.keys()):
        aa, bb = a.symbols.get(name), b.symbols.get(name)
        if not ((aa and aa['type'] == 2) or (bb and bb['type'] == 2)):
            continue
        functions[name] = dict(baseline=aa, candidate=bb,
            bytes_equal=bool(aa and bb and a.payload(name) == b.payload(name)))
    return dict(baseline_sections=a.allocated(), candidate_sections=b.allocated(), data=data,
                functions=functions, matched_addresses_claim=False, historical_elf_layout_claim=False,
                interpretation='Compiled software change INCLUDING ordinary code/data placement effects')


def timed_cfg(instructions, cycles):
    """Intraprocedural main CFG. Calls are recorded and assumed to return."""
    require(len(cycles) == 2, 'Need two cycle boundaries')
    rows = {r['pc']: r for r in instructions}
    start, end = cycles[0]['pc'], cycles[1]['pc']
    pending, visited, edges, calls = [start], set(), [], []
    branch_ops = {'beq', 'bne', 'blt', 'bge', 'bltu', 'bgeu', 'beqz', 'bnez',
                  'blez', 'bgez', 'bltz', 'bgtz', 'ble', 'bgt', 'bleu', 'bgtu'}
    while pending:
        pc = pending.pop()
        if pc in visited:
            continue
        require(pc in rows, 'Timed CFG exits main before end timer')
        visited.add(pc)
        if pc == end:
            continue
        row = rows[pc]
        text, op = row['text'], row['text'].split()[0]
        nextpc = pc + len(row['encoding']) // 2
        target = re.search(r'\b([0-9a-f]+)\s+<[^>]+>', text)
        if op in branch_ops or op == 'j':
            require(target is not None, 'Unresolved direct branch')
            successors = [int(target[1], 16)] + ([nextpc] if op != 'j' else [])
        elif op in ('jal', 'jalr'):
            calls.append(row)
            successors = [nextpc]
        else:
            require(op not in ('jr', 'ret', 'ecall', 'ebreak'), 'Unresolved timed control transfer')
            successors = [nextpc]
        for successor in successors:
            edges.append([pc, successor])
            pending.append(successor)
    require(end in visited, 'End timer unreachable')
    return dict(start=start, end=end, instructions=len(visited), edges=sorted(edges), calls=calls,
                unknown_edges=[], scope='main intraprocedural; call bodies not expanded; no dynamic execution claim')
