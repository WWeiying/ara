"""Byte-coordinate permutation only; never dequantize or regenerate inputs."""


def token_major(raw, row_bytes, heads=8, tokens=256):
    if any(type(x) is not int or x<=0 for x in (row_bytes,heads,tokens)):
        raise ValueError('Invalid physical shape')
    if len(raw)!=row_bytes*heads*tokens:
        raise ValueError('Capture extent mismatch')
    return b''.join(raw[(h*tokens+t)*row_bytes:(h*tokens+t+1)*row_bytes]
                    for t in range(tokens) for h in range(heads))
