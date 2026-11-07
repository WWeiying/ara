#!/usr/bin/env python3
"""Strict flat ELF64 PT_LOAD images for opt-in 8192x128 bank/column preload.

Each hex line is one 128-bit word, most-significant hex digit first; target
address byte zero occupies bits 7:0. Output directories are always fresh.
"""
import argparse
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import struct

DEPTH = 8192
MACRO_BYTES = 16
DEFAULT_BASE = 0x80000000
DEFAULT_CAPACITY = 1 << 20


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha256(data):
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class Geometry:
    width: int
    capacity: int = DEFAULT_CAPACITY
    base: int = DEFAULT_BASE

    def __post_init__(self):
        require(all(type(x) is int for x in (self.width, self.capacity, self.base)), 'Integer geometry required')
        require(self.width >= 8 and self.width & (self.width - 1) == 0, 'Power-of-two byte data width required')
        require(self.capacity > 0 and self.capacity <= 1 << 30 and
                self.capacity % (self.word_bytes * DEPTH) == 0, 'Capacity must contain complete 8192-word banks')
        require(self.banks & (self.banks - 1) == 0, 'Power-of-two bank count required')
        require(0 <= self.base < 1 << 64 and self.base % self.capacity == 0 and
                self.base + self.capacity <= 1 << 64, 'Invalid/overflowing physical memory interval')

    @property
    def word_bytes(self): return self.width // 8

    @property
    def banks(self): return self.capacity // (self.word_bytes * DEPTH)

    @property
    def columns(self): return max(1, self.width // 128)

    def record(self):
        return dict(**asdict(self), word_bytes=self.word_bytes, banks=self.banks, columns=self.columns,
                    macro_words=DEPTH, macro_bits=128)


def elf_image(data, *, base=DEFAULT_BASE, capacity=DEFAULT_CAPACITY):
    """Return flat bytes and load metadata; identical overlaps alone are legal."""
    require(isinstance(data, (bytes, bytearray)), 'ELF bytes required')
    require(type(base) is int and type(capacity) is int and 0 <= base < 1 << 64 and
            0 < capacity <= 1 << 30 and base + capacity <= 1 << 64, 'Invalid memory interval')
    require(len(data) >= 64 and data[:7] == b'\x7fELF\x02\x01\x01' and
            data[7] in (0, 3) and data[8:16] == bytes(8), 'Little-endian ELF64 version 1 required')
    h = struct.unpack_from('<16sHHIQQQIHHHHHH', data)
    _, kind, machine, version, entry, phoff, shoff, flags, ehsize, phsize, phnum, shsize, shnum, shstr = h
    require((kind, machine, version, ehsize, phsize) == (2, 243, 1, 64, 56) and
            0 < phnum <= 1024 and phoff >= 64 and phoff + phnum * phsize <= len(data),
            'Malformed RISC-V executable/program header table')
    require((shnum == 0 and shoff == shstr == 0) or
            (0 < shnum < 0xff00 and shsize == 64 and shoff >= 64 and
             shoff + shnum * shsize <= len(data) and shstr < shnum), 'Malformed/extended section table')
    segments = []
    for index in range(phnum):
        ptype, permissions, offset, va, pa, filesz, memsz, align = struct.unpack_from('<IIQQQQQQ', data, phoff + index * 56)
        if ptype != 1: continue
        require(permissions & ~7 == 0 and filesz <= memsz and offset <= len(data) and
                filesz <= len(data) - offset, 'Malformed PT_LOAD flags/file bounds')
        require(va == pa and pa + memsz <= 1 << 64 and
                base <= pa <= pa + memsz <= base + capacity, 'Translated/out-of-range PT_LOAD')
        require(align in (0, 1) or (align & (align - 1) == 0 and va % align == offset % align),
                'Invalid PT_LOAD alignment/congruence')
        if memsz:
            segments.append(dict(index=index, address=pa, offset=offset, file_bytes=filesz,
                                 memory_bytes=memsz, flags=permissions, alignment=align))
    require(segments and any(s['flags'] & 1 and s['address'] <= entry < s['address'] + s['file_bytes']
                             for s in segments), 'Entry must be in file-backed executable PT_LOAD bytes')
    image, defined = bytearray(capacity), bytearray(capacity)
    overlaps = 0
    for segment in segments:
        start = segment['address'] - base
        offset, filesz, memsz = segment['offset'], segment['file_bytes'], segment['memory_bytes']
        payload = data[offset:offset + filesz] + bytes(memsz - filesz)
        for i, value in enumerate(payload):
            address = start + i
            if defined[address]:
                require(image[address] == value, 'Conflicting PT_LOAD byte overlap, including BSS')
                overlaps += 1
            image[address] = value
            defined[address] = 1
    return bytes(image), dict(entry=entry, elf_flags=flags, segments=segments,
                              defined_bytes=sum(defined), identical_overlap_bytes=overlaps,
                              source_elf_sha256=sha256(data))


def column_images(image, geometry):
    require(isinstance(image, bytes) and len(image) == geometry.capacity, 'Exact flat image capacity required')
    for bank in range(geometry.banks):
        for column in range(geometry.columns):
            lines = []
            for row in range(DEPTH):
                word = (bank * DEPTH + row) * geometry.word_bytes
                first = word + column * MACRO_BYTES
                last = min(first + MACRO_BYTES, word + geometry.word_bytes)
                payload = image[first:last].ljust(MACRO_BYTES, b'\x00')
                lines.append(payload[::-1].hex() + '\n')
            yield bank, column, ''.join(lines).encode('ascii')


def prepare(elf, output, *, width, capacity=DEFAULT_CAPACITY, base=DEFAULT_BASE):
    geometry = Geometry(width, capacity, base)
    elf = Path(elf).resolve(strict=True)
    output = Path(output).absolute()
    require(output == output.resolve(), 'Canonical fresh output directory required')
    require(all(33 <= ord(char) <= 126 for char in str(output)), 'Printable non-whitespace ASCII output path required')
    raw = elf.read_bytes()
    image, metadata = elf_image(raw, base=base, capacity=capacity)
    require(all(len(str(output / f'bank_{bank}_col_{column}.hex').encode('utf-8')) <= 256
                for bank in range(geometry.banks) for column in range(geometry.columns)),
            'Original preloadData filename limit is 256 bytes')
    output.mkdir(parents=True, exist_ok=False)
    artifacts, files = {}, []
    state = dict(state='SRAM_MC_PRELOAD_IMAGE_FAIL', geometry=geometry.record(), source_elf=str(elf), **metadata)
    try:
        for bank, column, payload in column_images(image, geometry):
            target = output / f'bank_{bank}_col_{column}.hex'
            target.write_bytes(payload)
            artifacts[str(target)] = sha256(payload)
            files.append(dict(bank=bank, column=column, path=str(target), sha256=sha256(payload),
                              bytes=len(payload), words=DEPTH))
        flat = output / 'image.bin'; flat.write_bytes(image); artifacts[str(flat)] = sha256(image)
        source_pins = {str(elf): sha256(raw), str(Path(__file__).resolve()): sha256(Path(__file__).read_bytes())}
        pins = output / 'source-pins.json'; pins.write_text(json.dumps(source_pins, indent=2) + '\n')
        artifacts[str(pins)] = sha256(pins.read_bytes())
        require(elf.read_bytes() == raw, 'Source ELF changed during image generation')
        require(all(sha256(Path(path).read_bytes()) == sha for path, sha in artifacts.items()), 'Generated artifact drift')
        state.update(state='SRAM_MC_PRELOAD_IMAGE_PREPARED_NOT_EXECUTED', files=files,
                     image_sha256=sha256(image), source_pins_sha256=artifacts[str(pins)],
                     limits=['PT_LOAD byte preparation only, not CPU execution, timing, PMP or full-SoC acceptance'])
    except BaseException as exc:
        state['error'] = repr(exc)
        raise
    finally:
        state['artifacts'] = artifacts
        (output / 'manifest.json').write_text(json.dumps(state, indent=2) + '\n')
    return state


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--elf', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True, help='Fresh w128/w256 directory below the adapter root')
    parser.add_argument('--width', type=int, required=True)
    parser.add_argument('--capacity', type=lambda s: int(s, 0), default=DEFAULT_CAPACITY)
    parser.add_argument('--base', type=lambda s: int(s, 0), default=DEFAULT_BASE)
    args = parser.parse_args()
    print(json.dumps(prepare(args.elf, args.output, width=args.width, capacity=args.capacity, base=args.base), indent=2))
