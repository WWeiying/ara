"""Compare measured prefix/single mask symptoms, not internal RTL causality."""
from reduce_masks import fields, stimulus


def compare(prefix, single):
    p, detail = stimulus(prefix)
    s, other = stimulus(single)
    pb, _ = fields(prefix['output'], 'RVV_MASK_BIT')
    sb, _ = fields(single['output'], 'RVV_MASK_BIT')
    keys = {'seed', 'op', 'vl', 'mask', 'vstart', 'returned_vstart',
            'errors', 'guard_before', 'guard_after'}
    if not keys <= p.keys() or not keys <= s.keys():
        raise ValueError('Missing completion or guard evidence')
    bits = {'seed', 'op', 'vl', 'mask', 'vstart', 'element', 'active', 'old', 'expected', 'actual'}
    if not bits <= pb.keys() or not bits <= sb.keys():
        raise ValueError('Missing first-wrong-bit evidence')
    same = all(p[k] == s[k] for k in keys) and all(pb[k] == sb[k] for k in bits)
    return dict(confirmed=same, prefix_detail=detail, single_detail=other,
                scope='First wrong bit, trigger, returned vstart, guards and failing-trial error count')
