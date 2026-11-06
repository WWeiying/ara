"""Strictly decode a complete first-layer Qwen3 activation capture."""
import math
import re
import struct

from audit import require


def check(text):
    text = text.replace('\r\n', '\n')
    require('PROJECTION_CAPTURE_FAIL' not in text, 'Guest capture failure')
    require(text.count('PROJECTION_CAPTURE_SHAPE source=attn_norm-0 k=2048 rows=4 tokens=40 type=f32\n') == 1,
            'Missing/duplicate shape')
    require(text.count('PROJECTION_CAPTURE_DONE bytes=32768 stop=before_first_projection performance=not_measured\n') == 1,
            'Missing/duplicate terminal')
    tokens = re.findall(r'^PROJECTION_CAPTURE_TOKENS count=40 ids=([0-9,]+)$', text, re.M)
    require(len(tokens) == 1, 'Token inventory')
    ids = list(map(int, tokens[0].split(',')))
    require(len(ids) == 40 and all(0 <= t < 151936 for t in ids), 'Invalid tokens')
    shape_pos = text.index('PROJECTION_CAPTURE_SHAPE ')
    end_pos = text.index('PROJECTION_CAPTURE_DONE ')
    require(text.index('PROJECTION_CAPTURE_TOKENS ') < shape_pos < end_pos, 'Capture order')
    rows = re.findall(r'^PROJECTION_CAPTURE_DATA row=(\d+) offset=(\d+) bits=([0-9a-f]{128})$', text, re.M)
    require(len(rows) == text.count('PROJECTION_CAPTURE_DATA ') == 512, 'Incomplete/malformed payload')
    expected = [(r, o) for r in range(4) for o in range(0, 2048, 16)]
    require([(int(r), int(o)) for r, o, _ in rows] == expected, 'Duplicate/reordered/escaping chunk')
    payload = b''.join(struct.pack('<I', int(bits[i:i+8], 16))
                       for _, _, bits in rows for i in range(0, 128, 8))
    require(len(payload) == 32768 and all(math.isfinite(v[0]) for v in struct.iter_unpack('<f', payload)),
            'Bad float payload')
    require(len({payload[r*8192:(r+1)*8192] for r in range(4)}) == 4, 'Repeated activation rows')
    require(text.index('PROJECTION_CAPTURE_DATA ') > shape_pos and
            text.rindex('PROJECTION_CAPTURE_DATA ') < end_pos, 'Payload outside capture')
    return payload, dict(k=2048, rows=4, prompt_tokens=40, token_ids=ids,
                         source='attn_norm-0', complete_model_executed=False,
                         performance_measured=False)
