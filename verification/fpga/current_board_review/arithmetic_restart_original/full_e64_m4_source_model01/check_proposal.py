"""Check source macro indices only; do not preprocess, compile or call C."""
import hashlib
import json
from pathlib import Path
import re
import struct

here = Path(__file__).resolve().parent
header = here / 'fp_period_proposal.h'
text = header.read_text()
output = here / 'proposal_static_check.json'
if output.exists():
    raise FileExistsError(output)
digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
pair = text.split('#define E64_M4_PAIR', 1)[1].split('#define E64_M4_PERIOD', 1)[0]
assert re.findall(r'e64_m4_store\((a|b) \+ \(base\) \+ \(index\), \((x|y)\)\);', pair) == [('a', 'x'), ('b', 'y')]
period = text.split('#define E64_M4_PERIOD', 1)[1].split('#define E64_M4_FULL', 1)[0]
mapping = [tuple(map(int, row)) for row in re.findall(r'E64_M4_PAIR\(base, (\d+), p(\d+), p(\d+)\)', period)]
assert mapping == [(j, j, (3 * j) % 8) for j in range(8)]
full = text.split('#define E64_M4_FULL', 1)[1].split('/* Requires', 1)[0]
bases = re.findall(r'E64_M4_PERIOD\((\d+), p0, p1, p2, p3, p4, p5, p6, p7\)', full)
assert list(map(int, bases)) == list(range(0, 64, 8))
loads = re.findall(r'const uint64_t t(\d) = input8\[(\d)\];', text)
assert loads == [(str(j), str(j)) for j in range(8)]
cases = re.findall(r'case (\d): E64_M4_FULL\((.*?)\); break;', text)
assert len(cases) == 3
inputs = struct.unpack('<8Q', (here / 'generated01/fp_inputs8_u64le.bin').read_bytes())
generated = bytearray()
for seed_text, permutation_text in cases:
    seed = int(seed_text)
    permutation = list(map(int, re.findall(r't(\d)', permutation_text)))
    assert permutation == [(j + seed) % 8 for j in range(8)]
    destinations = []
    for base_text in bases:
        for j, x, y in mapping:
            i = int(base_text) + j
            destinations.extend([('a', i), ('b', i)])
            actual = (inputs[permutation[x]], inputs[permutation[y]])
            assert actual == (inputs[(i + seed) % 8], inputs[(3 * i + seed) % 8])
            generated.extend(struct.pack('<2Q', *actual))
    assert destinations == [(array, i) for i in range(64) for array in ('a', 'b')]
assert bytes(generated) == (here / 'generated01/fp_ordered_periods3_u64le.bin').read_bytes()
result = dict(status='SOURCE_MACRO_MAPPING_AGREES_NOT_COMPILED_NOT_EXECUTED',
              seed_branches=3, ordered_destinations_checked=384, fp_calls_required=1890,
              header_sha256=digest(header), checker_sha256=digest(Path(__file__)),
              generated_model_result_sha256=digest(here / 'generated01/result.json'),
              note='Static text/permutation verification only. Actual SD/load/ABI lowering remains unverified.')
output.write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result))
