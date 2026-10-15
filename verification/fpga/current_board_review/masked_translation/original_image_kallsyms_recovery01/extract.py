#!/usr/bin/env python3
"""Strict extraction for one SHA-bound Image, not a general kernel scanner."""
import bisect
import hashlib
import json
from pathlib import Path
import struct
import subprocess

HERE = Path(__file__).resolve().parent
IMAGE = Path('/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01/source/Image')
SHA = '716aef49389b25a0a3f4deac47de0bb69467a10f1057041cecd0f0621fbbf285'
LINUX = Path('/home/wangwy/openproject/cva6/cva6-sdk/buildroot/output/build/linux-6.19.6')
OBJDUMP = Path('/home/wangwy/openproject/cva6/cva6-sdk/buildroot/output/host/bin/riscv64-buildroot-linux-gnu-objdump')
BASE = 0xffffffff80000000


def require(ok, why):
    if not ok:
        raise ValueError(why)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, text):
    with path.open('x') as f:
        f.write(text)


def main():
    b = IMAGE.read_bytes()
    require(hashlib.sha256(b).hexdigest() == SHA, 'Original Image identity')
    require(b[48:56] == b'RISCV\0\0\0', 'RISC-V Image header')
    inputs = [IMAGE, Path(__file__), OBJDUMP, LINUX/'scripts/extract-ikconfig',
              LINUX/'scripts/kallsyms.c', LINUX/'kernel/kallsyms.c',
              LINUX/'kernel/kallsyms_internal.h']
    pins = {str(p): sha(p) for p in inputs}
    config_command = ['bash', str(LINUX/'scripts/extract-ikconfig'), str(IMAGE)]
    config = subprocess.run(config_command, check=True, capture_output=True,
                            text=True, timeout=30).stdout
    for line in ('CONFIG_KALLSYMS=y', '# CONFIG_KALLSYMS_ALL is not set',
                 'CONFIG_64BIT=y', '# CONFIG_RELOCATABLE is not set',
                 '# CONFIG_RANDOMIZE_BASE is not set'):
        require(line in config.splitlines(), 'Original embedded config: '+line)

    # Locations were discovered from token strings and their exact256-entry
    # u16 index. All variable-length names, markers and sequence indexes below
    # must validate; a matching string alone is never used as a symbol.
    num, names_start = 0x11832b0, 0x11832b8
    token, index, offsets, relative = 0x1227828, 0x1227ba0, 0x1227da0, 0x125ae00
    count = struct.unpack_from('<I', b, num)[0]
    require(count == 52248 and offsets + 4*count == relative, 'Count/table boundaries')
    token_offsets = struct.unpack_from('<256H', b, index)
    tokens, cursor = [], token
    for off in token_offsets:
        require(cursor == token+off, 'Token index exactly matches packed strings')
        end = b.index(0, cursor, index)
        tokens.append(b[cursor:end].decode('ascii'))
        cursor = end+1
    require((cursor+7)&~7 == index, 'Token alignment')
    names, markers, cursor = [], [], names_start
    for i in range(count):
        if i % 256 == 0:
            markers.append(cursor-names_start)
        length = b[cursor]
        cursor += 1
        if length & 128:
            length = (length & 127) | (b[cursor] << 7)
            cursor += 1
        require(0 < length <= 0x3fff and cursor+length < token, 'Compressed name bounds')
        expanded = ''.join(tokens[x] for x in b[cursor:cursor+length])
        cursor += length
        # scripts/kallsyms.c retains __start_/__stop_ section boundaries even
        # without KALLSYMS_ALL; these legitimately carry R/D types.
        require(len(expanded)>1 and (expanded[0] in 'tTwWaA' or
                (expanded[0] in 'RD' and expanded[1:].startswith(('__start_', '__stop_')))),
                'Text or explicit section-boundary symbol type')
        require(all(32 < ord(x) < 127 for x in expanded), 'Printable symbol')
        names.append(expanded)
    marker_at = (cursor+7)&~7
    require(list(struct.unpack_from('<%dI' % len(markers), b, marker_at)) == markers,
            'Every256-name marker')
    require((marker_at+4*len(markers)+7)&~7 == token, 'Marker table alignment')
    relative_base = struct.unpack_from('<Q', b, relative)[0]
    require(relative_base == BASE+0x2000, 'Fixed-link relative base')
    addresses = [relative_base+x for x in struct.unpack_from('<%dI' % count, b, offsets)]
    require(addresses == sorted(addresses), 'Address order')
    seq_at = relative+8
    seq = [int.from_bytes(b[seq_at+3*i:seq_at+3*i+3], 'big') for i in range(count)]
    require(sorted(seq) == list(range(count)), 'Name-order index permutation')
    require([names[i][1:] for i in seq] == sorted(s[1:] for s in names), 'Full lexical index')
    require(any(n=='T_text' and a==BASE+0x2000 for a,n in zip(addresses,names)), '_text anchor')
    pcs = [BASE+0x13a16, BASE+0x13a18, BASE+0xb8754e, BASE+0xb8759e]
    expected = [bytes.fromhex(s) for s in ('ba97','73258000','2338c503','2300f500')]
    matches = []
    for pc, encoding in zip(pcs, expected):
        require(b[pc-BASE:pc-BASE+len(encoding)] == encoding, 'Actual historical PC bytes')
        i = bisect.bisect_right(addresses, pc)-1
        j = bisect.bisect_right(addresses, addresses[i])
        aliases = [names[k] for k in range(bisect.bisect_left(addresses,addresses[i]),j)]
        matches.append(dict(pc=hex(pc), symbol=names[i][1:], type=names[i][0],
            start=hex(addresses[i]), offset=hex(pc-addresses[i]), aliases=aliases,
            next_symbol_start=hex(addresses[j]), instruction_bytes=encoding.hex(),
            interval_is='Next kallsyms address, not DWARF/ELF function-size proof'))
    windows = []
    for start, stop in [(0x13898,0x13b3c),(0xb874e8,0xb875b4)]:
        cmd = [str(OBJDUMP),'-D','-b','binary','-m','riscv:rv64',
               '--adjust-vma='+hex(BASE),'--start-address='+hex(BASE+start),
               '--stop-address='+hex(BASE+stop),str(IMAGE)]
        output = subprocess.run(cmd,check=True,capture_output=True,text=True,timeout=30)
        windows.append(dict(command=cmd,returncode=output.returncode,stdout=output.stdout))
    require(all(sha(p)==h for p,h in pins.items()), 'Inputs unchanged')
    out = HERE/'output01'
    out.mkdir()
    save(out/'accepted.config',config)
    save(out/'System.map.recovered',''.join('%016x %s %s\n'%(a,n[0],n[1:]) for a,n in zip(addresses,names)))
    save(out/'pc_windows.txt','\n'.join('COMMAND '+json.dumps(w['command'])+'\n'+w['stdout'] for w in windows))
    result = dict(status='ORIGINAL_IMAGE_KALLSYMS_RECOVERED_NOT_RUNTIME_PROOF',
        image=str(IMAGE),image_sha256=SHA,symbol_count=count,input_pins=pins,
        config_command=config_command,config_returncode=0,
        tables={k:hex(v) for k,v in dict(num_syms=num,names=names_start,markers=marker_at,
                 token_table=token,token_index=index,offsets=offsets,relative_base=relative,
                 seqs_of_names=seq_at).items()},relative_base_value=hex(relative_base),
        full_markers_validated=len(markers),full_name_index_permutation_and_sort=True,
        address_order_validated=True,pc_matches=matches,
        config_kallsyms_all=False,uses_mismatching_vmlinux_symbols=False,
        DWARF_recovered=False,runtime_dump_or_root_cause_proved=False,
        output_pins={str(p):sha(p) for p in out.iterdir() if p.is_file()})
    save(out/'result.json',json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(status=result['status'],count=count,pc_matches=matches)))


if __name__ == '__main__':
    main()
