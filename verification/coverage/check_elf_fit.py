#!/usr/bin/env python3
"""Check that frozen RISC-V ELF load segments fit the coverage model RAM."""

import argparse
import hashlib
import json
from pathlib import Path

from elftools.elf.elffile import ELFFile


def sha256(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def check(paths: list[Path], base: int, size: int, word_bytes: int = 1) -> dict:
    if size <= 0 or base < 0 or word_bytes <= 0:
        raise ValueError("RAM base, size and word width must describe a positive address range")
    records = []
    errors = []
    for path in paths:
        path = path.resolve(strict=True)
        segments = []
        with path.open("rb") as stream:
            elf = ELFFile(stream)
            if elf.elfclass != 64 or elf["e_machine"] != "EM_RISCV" or elf["e_type"] != "ET_EXEC":
                errors.append(f"{path}: expected an executable RISC-V ELF64")
            for segment in elf.iter_segments():
                if segment["p_type"] != "PT_LOAD":
                    continue
                address = int(segment["p_paddr"])
                memory_size = int(segment["p_memsz"])
                file_size = int(segment["p_filesz"])
                segments.append({"address": address, "end": address + memory_size,
                                 "file_bytes": file_size, "memory_bytes": memory_size})
                if (file_size > memory_size or address < base or
                        address + memory_size > base + size):
                    errors.append(f"{path}: PT_LOAD 0x{address:x}..0x{address + memory_size:x} "
                                  f"does not fit RAM 0x{base:x}..0x{base + size:x}")
                if memory_size and (address - base) % word_bytes:
                    errors.append(f"{path}: PT_LOAD 0x{address:x} is not aligned "
                                  f"to the {word_bytes}-byte RAM word")
        if not segments:
            errors.append(f"{path}: no PT_LOAD segments")
        records.append({"path": str(path), "sha256": sha256(path), "segments": segments})
    return {"status": "PASS" if not errors else "FAIL", "ram_base": base,
            "ram_bytes": size, "ram_word_bytes": word_bytes,
            "inputs": records, "errors": errors}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--elf", type=Path, action="append", required=True)
    parser.add_argument("--ram-base", type=lambda value: int(value, 0), default=0x80000000)
    parser.add_argument("--ram-bytes", type=lambda value: int(value, 0), required=True)
    parser.add_argument("--ram-word-bytes", type=lambda value: int(value, 0), default=1)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = check(args.elf, args.ram_base, args.ram_bytes, args.ram_word_bytes)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(f"ELF RAM fit: {result['status']} ({len(result['inputs'])} inputs)")
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
