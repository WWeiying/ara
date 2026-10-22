"""Offline identity utilities; imports never inspect running batch artifacts."""
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
G = HERE.parent
TRANSPORT = G/'ordered_reduction/original_remaining9_terminal_audit01/observer.py'
TRANSPORT_SHA = '7d15ce50da9918fa9b1d3bb1cea59871b4312385576da1fd6c8d5940dbad650f'


def read(path): return json.loads(Path(path).read_text())


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1048576), b''): h.update(block)
    return h.hexdigest()


def save(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2); stream.write('\n')


def add(pins, mapping):
    for p, h in mapping.items():
        assert p not in pins or pins[p] == h, ('conflicting pin', p)
        pins[p] = h


def verify(pins):
    for p, h in pins.items(): assert sha(p) == h, ('pin drift', p)


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def elf(path):
    data = Path(path).read_bytes()
    assert data[:6] == b'\x7fELF\x02\x01'
    phoff, shoff = struct.unpack_from('<QQ', data, 32)
    phsize, phnum, shsize, shnum = struct.unpack_from('<HHHH', data, 54)
    segments = []
    for j in range(phnum):
        kind, _, off, va, _, size, _, _ = struct.unpack_from('<IIQQQQQQ', data, phoff+j*phsize)
        if kind == 1: segments.append((va, va+size, off))
    sections = [struct.unpack_from('<IIQQQQIIQQ', data, shoff+j*shsize) for j in range(shnum)]
    symbols = {}
    for section in sections:
        if section[1] != 2: continue
        strings = sections[section[6]]
        table = data[strings[4]:strings[4]+strings[5]]
        for at in range(section[4], section[4]+section[5], section[9]):
            name, _, _, _, value, size = struct.unpack_from('<IBBHQQ', data, at)
            name = table[name:].split(b'\0', 1)[0].decode()
            if name: symbols[name] = (value, size)
    def get(address, size):
        for lo, hi, off in segments:
            if lo <= address and address+size <= hi: return data[off+address-lo:off+address-lo+size]
        raise AssertionError(('unmapped ELF', hex(address)))
    return get, symbols
