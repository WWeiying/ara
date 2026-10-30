"""Read-only GGML quantized-K layout admission; not a quantizer or native backend."""
import argparse
import hashlib
import json
from pathlib import Path
import struct

BLOCK_BYTES = {'q4_0': 18, 'q8_0': 34}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def prefix_length(mask):
    require(len(mask) > 0 and len(mask) % 2 == 0, 'Invalid F16 mask extent')
    prefix, hidden = 0, False
    for (bits,) in struct.iter_unpack('<H', mask):
        if bits == 0:
            require(not hidden, 'Mask holes require original runtime fallback')
            prefix += 1
        elif bits == 0xfc00:
            hidden = True
        else:
            raise ValueError('Only exact zero/-infinity prefix masks admitted')
    require(prefix > 0, 'Empty attention needs separate handling')
    return prefix


def inspect(meta, data, visible):
    require(meta.get('type') in BLOCK_BYTES, 'Not actual Q4_0/Q8_0 KV storage')
    shape, strides = meta.get('shape'), meta.get('strides')
    require(isinstance(shape,list) and isinstance(strides,list) and len(shape) == len(strides) == 4,
            'Expected four GGML axes/strides')
    require(all(type(x) is int and x > 0 for x in shape+strides), 'Invalid dimensions/strides')
    dim, capacity, heads, batches = shape
    require(type(visible) is int and dim % 32 == 0 and 0 < visible <= capacity,
            'Block alignment or visible prefix invalid')
    require(batches == 1 and dim <= 256 and capacity <= 65536 and heads <= 256 and
            capacity*heads <= 262144,
            'Outside bounded initial capture admission')
    block_bytes = BLOCK_BYTES[meta['type']]
    require(strides[0] == block_bytes, 'GGML nb0 is bytes per quant block, not element')
    require(type(meta.get('nbytes')) is int and meta['nbytes'] == len(data), 'Tensor size mismatch')
    row_bytes = dim//32*block_bytes
    require(strides[1] >= row_bytes and strides[2] >= row_bytes, 'Overlapping row stride')
    # Check every stored row for disjointness, but inspect scale payload only in
    # visible rows. Masked cache rows may not have been initialized by the model.
    rows = [(h*strides[2]+t*strides[1],h,t) for h in range(heads) for t in range(capacity)]
    rows.sort()
    previous_end = 0
    for start,head,token in rows:
        require(start >= previous_end and start+row_bytes <= len(data), 'Overlapping/out-of-bounds KV rows')
        previous_end = start+row_bytes
        if token >= visible:
            continue
        for block in range(dim//32):
            scale = struct.unpack_from('<H', data, start+block*block_bytes)[0]
            require(scale & 0x7c00 != 0x7c00, 'Nonfinite quant scale requires separate numerical policy')
    logical = row_bytes*visible*heads
    return dict(state='LAYOUT_ADMITTED_NOT_NUMERICALLY_VALIDATED',type=meta['type'],
        head_dim=dim,capacity=capacity,visible_tokens=visible,kv_heads=heads,
        block_elements=32,block_bytes=block_bytes,row_bytes=row_bytes,
        token_stride_bytes=strides[1],head_stride_bytes=strides[2],
        tight_rows_per_head=strides[1] == row_bytes,
        visible_payload_bytes=logical,
        full_visible_gather_read_plus_write_bytes=2*logical,
        candidate_read_ranges=[[h*strides[2]+t*strides[1],row_bytes]
                               for h in range(heads) for t in range(visible)],
        numerical_accepted=False,native_execution=False,
        limits='Layout only; no Query quantization, score, PV, performance or model correctness proof')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--tensor',type=Path,required=True)
    p.add_argument('--mask',type=Path,required=True,help='F16 mask binary for this exact query')
    args = p.parse_args()
    binary = args.tensor.with_suffix('.bin')
    paths = [args.tensor,binary,args.mask]
    before = {str(x.resolve()):hashlib.sha256(x.read_bytes()).hexdigest() for x in paths}
    meta = json.loads(args.tensor.read_text())
    mask = args.mask.read_bytes()
    require(isinstance(meta.get('shape'),list) and len(meta['shape']) == 4 and
            len(mask) == meta['shape'][1]*2, 'Mask length must match actual KV capacity')
    result = inspect(meta,binary.read_bytes(),prefix_length(mask))
    result['source_sha256'] = before
    require(before == {str(x.resolve()):hashlib.sha256(x.read_bytes()).hexdigest() for x in paths},
            'Capture changed while inspecting')
    print(json.dumps(result,indent=2,sort_keys=True))


if __name__ == '__main__':
    main()
