"""QK layout/mask contract for a future shared controller, not RTL evidence."""


def require(ok, text):
    if not ok:
        raise ValueError(text)


def control(tokens, heads, dimension, query_base=0, query_rows=8):
    require(tokens in range(1, 65) and heads in (1, 2) and dimension in (64, 96, 128),
            'Unsupported QK shape')
    require(query_rows in range(1, 9) and query_base in range(query_rows) and
            query_base+heads <= query_rows, 'Q selection exceeds the resident context')
    return ((tokens-1) | (heads-1) << 6 | {64: 0, 128: 1, 96: 2}[dimension] << 7 |
            query_base << 9)


def private_mask(active, elements, fp_lanes):
    """Repeat semantic element masks across FPnew's maximum physical lane count."""
    require(elements in (2, 4) and fp_lanes in (4, 8), 'Unsupported SIMD geometry')
    require(active in range(1 << elements), 'Element mask exceeds its format')
    return sum(((active >> ((elements*b)//fp_lanes)) & 1) << b for b in range(fp_lanes))


def fpnew_sample(mask, elements, fp_lanes):
    require(elements in (2, 4) and fp_lanes in (4, 8) and mask in range(1 << fp_lanes),
            'Invalid FPnew mask')
    return sum(((mask >> ((fp_lanes//elements)*b)) & 1) << b for b in range(elements))


def layout(tokens, heads, vd=0):
    require(tokens in range(1, 65) and heads in (1, 2) and vd in range(0, 29, 4),
            'Invalid QK destination or shape')
    lanes = []
    for lane in range(4):
        n = max(0, (tokens+3-lane)//4)
        writes = []
        for head in range(heads):
            for word in range((n+1)//2):
                valid = min(2, n-2*word)
                writes.append(dict(head=head, word=word, slot=8*head+word,
                                   address=4*vd+8*head+word, elements=valid,
                                   element_mask=(1 << valid)-1,
                                   byte_enable=(1 << (4*valid))-1))
        lanes.append(dict(lane=lane, elements=n, active=bool(n), writes=writes))
    return lanes


def scalar_locations(tokens, heads, vd=0):
    """Resolve actual destination byte lanes back to active (head, token) pairs."""
    locations = {}
    for lane in layout(tokens, heads, vd):
        for w in lane['writes']:
            for half in range(w['elements']):
                token = 4*(2*w['word']+half)+lane['lane']
                require(token < tokens, 'Internal inactive output mapping')
                locations[lane['lane'], w['address'], 4*half] = (w['head'], token)
    return locations


def raw_packets(tokens):
    require(tokens in range(1, 65), 'Invalid token count')
    return [dict(packet=p, active=sum((16*p+l < tokens) << l for l in range(4)))
            for p in range((tokens+15)//16)]


def widening_halfwords(subword):
    require(subword in (0, 1), 'Invalid FP32 subword')
    return (subword, subword+2)
