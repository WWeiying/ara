#!/usr/bin/env python3
"""Host-only exact block representation study. No compiler or target execution."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import time

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
ARCH = Path('/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01/rvv_extended04')
KINDS = [0] * 19 + [1, 1, 1, 2, 3, 0]
U64 = (1 << 64) - 1


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_model(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MODEL = load_model(ROOT / 'full_e16_mf4_prepare01/model.py', 'integer_model')


def generate(sew, cap):
    assert (sew, cap) in ((8, 512), (8, 1024), (16, 512))
    mod = (1 << sew) - 1
    for seed in range(3):
        rng = 0x937ad68de41c725f ^ seed
        a, b = [], []
        for i in range(cap):
            rng ^= (rng << 13) & U64
            rng ^= rng >> 7
            rng ^= (rng << 17) & U64
            x, y = rng & mod, (rng >> 19) & mod
            if i % 8 == 0:
                x = y = 0
            elif i % 8 == 1:
                x, y = mod, 1
            elif i % 8 == 2:
                x, y = 1 << (sew - 1), mod
            elif i % 8 == 3:
                y = sew
            a.append(x)
            b.append(y)
        for op in range(25):
            for li, vl in enumerate((0, 1, 2, 3, cap // 2, cap - 1, cap)):
                for mode in range(3):
                    for si in range(3 if KINDS[op] == 0 else 1):
                        start = (0, vl // 2, vl if vl < cap else cap - 1)[si]
                        # Follow the recovered C's per-element oracle, including
                        # compress's advancing cursor and reduction's seed.
                        packed, reduced = 0, b[0]
                        if KINDS[op] == 2:
                            for i in range(vl):
                                if MODEL.selected(mode, i):
                                    reduced = (reduced + a[i]) & mod
                        out = []
                        for i in range(cap):
                            expected = 91
                            if KINDS[op] == 2:
                                if i == 0 and vl:
                                    expected = reduced
                            elif KINDS[op] == 3:
                                while packed < vl and not MODEL.selected(mode, packed):
                                    packed += 1
                                if packed < vl:
                                    expected = a[packed]
                                    packed += 1
                            elif start <= i < vl and MODEL.selected(mode, i):
                                if op < 19:
                                    expected = MODEL.integer(op, a[i], b[i], sew)
                                elif op == 19 and i >= 2:
                                    expected = a[i - 2]
                                elif op == 20:
                                    expected = a[i + 2] if i + 2 < cap else 0
                                elif op == 21:
                                    expected = a[b[i]] if b[i] < cap else 0
                                elif op == 24:
                                    expected = a[i]
                            out.append(expected)
                        raw = MODEL.words([91] + out + [91], sew)
                        yield (seed, op, li, vl, mode, si, start), raw


def representation(sew, cap):
    pool, ids_by_value, rows = [], {}, []
    order_digest, output_digest = hashlib.sha256(), hashlib.sha256()
    negative_checks = 0
    for ordinal, (context, raw) in enumerate(generate(sew, cap)):
        ids = []
        for offset in range(0, len(raw), 64):
            block = raw[offset:offset + 64].ljust(64, b'\0')
            if block not in ids_by_value:
                ids_by_value[block] = len(pool)
                pool.append(block)
            ids.append(ids_by_value[block])
        reconstructed = b''.join(pool[i] for i in ids)[:len(raw)]
        assert reconstructed == raw
        # Exact footprint slices: 128 full words plus one narrow tail on m8.
        spans = [(p, min(8, len(raw) - p)) for p in range(0, len(raw), 8)]
        assert sum(n for _, n in spans) == len(raw)
        assert max(p + n for p, n in spans) == len(raw)
        for pos in (0, sew // 8 - 1, sew // 8, 63, 64, 511, 512,
                    len(raw) - sew // 8 - 1, len(raw) - sew // 8, len(raw) - 1):
            changed = bytearray(raw)
            changed[pos] ^= 1
            assert bytes(changed) != reconstructed
            negative_checks += 1
        order_digest.update(json.dumps([ordinal, *context], separators=(',', ':')).encode())
        output_digest.update(raw)
        rows.append(ids)
    assert len(rows) == 4095 and len(pool) <= 65536
    footprint = (cap + 2) * sew // 8
    blocks = (footprint + 63) // 64
    assert all(len(r) == blocks for r in rows)
    table = b''.join(i.to_bytes(2, 'little') for row in rows for i in row)
    masks = [bytes(sum(1 << (i % 8) for i in range(j * 8, min(j * 8 + 8, cap))
                       if MODEL.selected(mode, i)) for j in range(128)) for mode in range(3)]
    rom = len(table) + len(pool) * 64 + sum(map(len, masks))
    return dict(sew=sew, cap=cap, calls=4095, results=4095 * cap, guards=8190,
                vstart_checks=4095, output_bytes_per_call=footprint,
                total_checked_output_bytes=4095 * footprint, blocks_per_call=blocks,
                pool_blocks=len(pool), pool_bytes=64 * len(pool), max_block_id=len(pool) - 1,
                index_bytes=len(table), mask_rom_bytes=384, expected_rom_bytes=rom,
                physical_arrays_bytes=(1024 + 1024 + 1026) * sew // 8 + 128,
                flat_word_id_bytes=4095 * ((footprint + 7) // 8) * 2,
                zero_pad_bytes_per_last_rom_block=blocks * 64 - footprint,
                exact_full_word_loads_per_call=footprint // 8, narrow_tail_bytes=footprint % 8,
                negative_byte_mutations=negative_checks,
                full_reconstruction_equal=True, order_sha256=order_digest.hexdigest(),
                oracle_bytes_sha256=output_digest.hexdigest(),
                pool_sha256=hashlib.sha256(b''.join(pool)).hexdigest(),
                index_sha256=hashlib.sha256(table).hexdigest(),
                remaining_after_rom_arrays_stack64k_code64k=1048576 - rom -
                    ((1024 + 1024 + 1026) * sew // 8 + 128) - 2 * 65536)


def main():
    started = time.monotonic()
    recovery = json.loads((ROOT / 'recovery22/report.json').read_text())
    manifest = json.loads((ARCH / 'manifest.json').read_text())
    paths = [Path(__file__).resolve(), ROOT / 'recovery22/reconstructed_oracle.c',
             ROOT / 'recovery22/report.json', ARCH / 'manifest.json',
             ROOT / 'full_e16_mf4_prepare01/model.py',
             ROOT / 'full_e8_m4_dict_prepare01/model.py',
             ROOT / 'full_e8_m4_dict_prepare01/packed.h',
             ROOT / 'full_e16_mf4_prepare01/runtime/replay.ld']
    identities = []
    for sew in (8, 16):
        name = f'rvv_matrix_e{sew}_m8'
        old = next(x for x in recovery['results'] if x['name'] == name)
        entry = next(x for x in manifest['cases'] if x['name'] == name)
        original = ARCH / 'overlay/opt/ara-tests' / name
        rebuilt = ROOT / 'recovery22' / name
        assembly = ARCH / (name + '.S')
        header = ARCH / f'e{sew}/operations.h'
        assert old['exact_elf_equal'] and old['disassembly_equal']
        assert original.read_bytes() == rebuilt.read_bytes()
        assert sha(original) == old['original_sha256'] == old['reconstructed_sha256'] == entry['sha256']
        assert f'e{sew}, m8, tu, mu' in assembly.read_text()
        paths.extend([original, rebuilt, assembly, header])
        identities.append(dict(name=name, recovery=old, manifest=entry,
                               original_elf=str(original), rebuilt_elf=str(rebuilt),
                               assembly=str(assembly), header=str(header)))
    pins = {str(p): sha(p) for p in paths}
    # Cross-check the generalized sequence/oracle against the mature e8/m4
    # word dictionary for all4095 calls; no target/reference execution.
    m4 = load_model(ROOT / 'full_e8_m4_dict_prepare01/model.py', 'old_m4')
    _, old_rows, old_words, _ = m4.generate()
    for ordinal, (context, raw) in enumerate(generate(8, 512)):
        row = old_rows[ordinal]
        assert context == tuple(row[k] for k in ('seed', 'op', 'li', 'vl', 'mode', 'si', 'start'))
        assert raw == b''.join(old_words[i].to_bytes(8, 'little') for i in row['indices'])[:514]
    shapes = {f'e{sew}_m8': representation(sew, 8192 // sew) for sew in (8, 16)}
    assert all(sha(Path(p)) == digest for p, digest in pins.items())
    result = dict(status='HOST_REPRESENTATION_FEASIBLE_NOT_COMPILED_OR_REFERENCE_OR_DUT',
                  pid=os.getpid(), elapsed_seconds=time.monotonic() - started,
                  original_C_bytes_recovered=False, source_binary_equivalent_reconstruction=True,
                  e8_m4_all4095_model_crosscheck=True, shapes=shapes, identities=identities,
                  pins=pins, pins_unchanged=True)
    with (HERE / 'host_result01.json').open('x') as f:
        json.dump(result, f, indent=2)
        f.write('\n')
    print(json.dumps({k: result[k] for k in ('status', 'pid', 'elapsed_seconds', 'shapes')}, indent=2))


if __name__ == '__main__':
    main()
