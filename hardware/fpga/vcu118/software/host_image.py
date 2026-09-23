#!/usr/bin/env python3
"""Validated, streaming physical images for the FPGA host loader."""
from dataclasses import asdict, dataclass
import hashlib
from pathlib import Path
import sys

DDR1 = (0x80000000, 0x100000000)
DDR2 = (0x100000000, 0x180000000)
CAP_HOST = 1
CAP_DDR2 = 2
MAX_BEATS = 256
BEAT_BYTES = 8


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def check_range(address, size, caps):
    if not caps & CAP_HOST:
        raise ValueError("Host-loader capability is absent")
    windows = [DDR1] + ([DDR2] if caps & CAP_DDR2 else [])
    if size <= 0 or not any(lo <= address < address + size <= hi for lo, hi in windows):
        raise ValueError(f"Not in one enabled DDR window: 0x{address:x}+0x{size:x}")


def burst_slices(address, size):
    """Yield payload slices; enclosing full beats never cross 4 KiB/256 beats."""
    if address < 0 or size <= 0:
        raise ValueError("Invalid image extent")
    offset = 0
    while offset < size:
        current = address + offset
        aligned = current & ~7
        end = min(aligned + MAX_BEATS * BEAT_BYTES, (aligned | 4095) + 1)
        length = min(size - offset, end - current)
        yield current, offset, length
        offset += length


def to_axi_hex(data, word_bytes=8):
    """Pack lowest-address word on the right, per UG936 v2020.1 p.144.

    Primary manuals conflict; this is NOT assumed portable across tool versions.
    The loader must pass preflight_axi_mapping on the connected hardware first.
    UG936 v2020.1 (June 24, 2020):
    https://docs.amd.com/api/khub/documents/jrKQyKSbiw0TlWQefSZPIQ/content
    UG908 v2021.2 instead describes lowest address on the left:
    https://docs.amd.com/r/2021.2-English/ug908-vivado-programming-debugging/Creating-and-Running-a-Write-Transaction?contentId=e56FURlxVgkrVIRqZfwq0Q
    """
    if not data or len(data) % word_bytes:
        raise ValueError("AXI data must contain complete words")
    return "".join(f"{int.from_bytes(data[i:i + word_bytes], 'little'):0{2 * word_bytes}x}"
                   for i in reversed(range(0, len(data), word_bytes)))


def from_axi_hex(value, size):
    value = "".join(value.strip().removeprefix("0x").split()).replace("_", "")
    if len(value) != size * 2 or any(c not in "0123456789abcdefABCDEF" for c in value):
        raise ValueError(f"Malformed AXI DATA: expected {size * 2} hex digits")
    return int(value, 16).to_bytes(size, "little")


@dataclass
class Segment:
    address: int
    size: int
    file_size: int
    source: str
    source_offset: int
    flags: int
    kind: str
    sha256: str = ""

    def chunks(self):
        with Path(self.source).open("rb") as stream:
            stream.seek(self.source_offset)
            for address, offset, length in burst_slices(self.address, self.size):
                initialized = max(0, min(length, self.file_size - offset))
                data = stream.read(initialized)
                if len(data) != initialized:
                    raise ValueError(f"Source truncated: {self.source}")
                yield address, data + bytes(length - initialized)


@dataclass
class Image:
    entry: int
    caps: int
    segments: list
    sources: list

    def manifest(self):
        return {"format": "ara-host-image-v1", "entry": self.entry, "caps": self.caps,
                "ddr_windows": [DDR1] + ([DDR2] if self.caps & CAP_DDR2 else []),
                "sources": self.sources, "segments": [asdict(s) for s in self.segments]}


def elf_class():
    # The exported package already ships this wheel for the baseline UART loader.
    here = Path(__file__).resolve().parent
    for directory in (here / "vendor", here.parents[1] / "ara_dsa_vcu118/software/vendor"):
        for wheel in sorted(directory.glob("pyelftools-*.whl")):
            sys.path.insert(0, str(wheel))
    try:
        from elftools.elf.elffile import ELFFile
    except ImportError as exc:
        raise RuntimeError("Install pyelftools or use the exported software/vendor wheels") from exc
    return ELFFile


def prepare_image(elf_path, raw_loads=(), caps=CAP_HOST):
    path = Path(elf_path).resolve()
    ELFFile = elf_class()
    segments = []
    with path.open("rb") as stream:
        elf = ELFFile(stream)
        if (elf.elfclass != 64 or not elf.little_endian or
                elf["e_machine"] != "EM_RISCV" or elf["e_type"] != "ET_EXEC"):
            raise ValueError("Expected a little-endian RV64 ET_EXEC ELF (no PIE)")
        entry = int(elf["e_entry"])
        file_length = path.stat().st_size
        for segment in elf.iter_segments():
            if segment["p_type"] in ("PT_INTERP", "PT_DYNAMIC"):
                raise ValueError("Dynamic ELF requires a runtime loader")
            if segment["p_type"] != "PT_LOAD":
                continue
            address, size, initialized, offset = (int(segment[k]) for k in
                                                  ("p_paddr", "p_memsz", "p_filesz", "p_offset"))
            if initialized > size or offset + initialized > file_length:
                raise ValueError("Invalid or truncated ELF segment")
            if not size:
                continue
            check_range(address, size, caps)
            if int(segment["p_vaddr"]) != address:
                raise ValueError("Bare-metal ELF must have identical virtual/physical addresses")
            alignment = int(segment["p_align"])
            if alignment > 1 and (alignment & (alignment - 1) or
                                  address % alignment != offset % alignment):
                raise ValueError("Invalid ELF segment alignment")
            segments.append(Segment(address, size, initialized, str(path), offset,
                                    int(segment["p_flags"]), "elf"))
    if entry & 1 or not any(s.flags & 1 and s.address <= entry and
                            entry + 2 <= s.address + s.file_size for s in segments):
        raise ValueError("Entry must be aligned and in file-backed executable ELF bytes")
    for address, raw_path in raw_loads:
        raw_path = Path(raw_path).resolve()
        size = raw_path.stat().st_size
        check_range(address, size, caps)
        segments.append(Segment(address, size, size, str(raw_path), 0, 0, "raw"))
    segments.sort(key=lambda s: s.address)
    for left, right in zip(segments, segments[1:]):
        if left.address + left.size > right.address:
            raise ValueError("ELF/raw load ranges overlap (including BSS)")
    sources = [{"path": name, "bytes": Path(name).stat().st_size,
                "sha256": sha256_file(name)} for name in sorted({s.source for s in segments})]
    for segment in segments:
        digest = hashlib.sha256()
        for _, data in segment.chunks():
            digest.update(data)
        segment.sha256 = digest.hexdigest()
    return Image(entry, caps, segments, sources)
