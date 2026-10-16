#!/usr/bin/env python3
"""Read current CPU0 task using the hash-pinned Image's task_curr instructions.

No memory writes, reset, halt, or launch. Debug snapshot commands are issued.
Kernel data is evidence only: it does not expose the scalar LSU head or TLB.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

IMAGE_HASH = "716aef49389b25a0a3f4deac47de0bb69467a10f1057041cecd0f0621fbbf285"
KERNEL_BASE = 0xffffffff80000000
DIRECT_BASE = 0xffffffd600000000
MASK = (1 << 64) - 1


def physical(va):
    if DIRECT_BASE <= va < DIRECT_BASE + 0x80000000:
        return 0x80000000 + va - DIRECT_BASE
    if KERNEL_BASE <= va < KERNEL_BASE + 0x2000000:
        return 0x80200000 + va - KERNEL_BASE
    raise ValueError("Address outside reviewed kernel mappings: " + hex(va))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--software", type=Path, required=True)
    p.add_argument("--image", type=Path, required=True)
    p.add_argument("--probes", type=Path, required=True)
    p.add_argument("--vivado", required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--site", choices=("user-return", "irq-return"), default="user-return")
    a = p.parse_args()
    image = a.image.read_bytes()
    if hashlib.sha256(image).hexdigest() != IMAGE_HASH:
        raise ValueError("Wrong kernel Image")
    # Actual task_curr code: per_cpu_offset[cpu] + runqueues + 0xa80.
    code = {0x5e5ca: 0x01a03797, 0x5e5ce: 0x05678793,
            0x5e5d2: 0x00dea717, 0x5e5d6: 0x36e70713,
            0x5e5ec: 0xa807b783, 0x15e9a: 0x02070c07,
            0x15ea2: 0xb8073683, 0x15ea6: 0xb9073603,
            0x15eaa: 0xb8873703, 0xc07fca: 0x00e2a797,
            0xc07fce: 0x03678793, 0xc0800c: 0x18079073}
    for offset, word in code.items():
        if struct.unpack_from("<I", image, offset)[0] != word:
            raise ValueError("Instruction oracle mismatch: " + hex(offset))
    a.out.mkdir(parents=True, exist_ok=False)
    sys.path.insert(0, str(a.software))
    from host_load import capture_snapshot
    from host_transport import Operation, VivadoTransport
    report = {"memory_writes": False, "reset": False, "image_sha256": IMAGE_HASH,
              "scope": "memory evidence; not a measurement of scalar LSU head or TLB",
              "site": a.site, "reads": []}
    try:
        with VivadoTransport(a.out / "transport", vivado=a.vivado, probes=a.probes) as t:
            def read(pa, length):
                if pa % 8 or length % 8 or not 0x80000000 <= pa < pa + length <= 0x100000000:
                    raise ValueError("Read outside DDR or unaligned")
                data = b"".join(t.exchange([Operation("M", "READ", pa+i)
                                            for i in range(0, length, 8)]))
                report["reads"].append({"pa": hex(pa), "data": data.hex()})
                return data

            report["before"] = capture_snapshot(t)
            head_offset = 0x15e9a if a.site == "user-return" else 0xb88582
            if struct.unpack_from("<I", image, head_offset)[0] != 0x02070c07:
                raise ValueError("Selected site is not vle8.v v24")
            if report["before"]["core"]["head_pc"] != KERNEL_BASE + head_offset:
                raise ValueError("Not at the expected fourth restore load")
            # Verify live instruction bytes before following image-derived pointers.
            for offset, size in ((0x5e5c8, 48), (head_offset & ~7, 32)):
                if read(0x80200000+offset, size) != image[offset:offset+size]:
                    raise ValueError("Live kernel instructions differ from Image")
            values = []

            def walk(va):
                # paging_init builds SATP from this kernel root. This reads the
                # shared kernel mapping, not the running hart's SATP or TLB.
                table = physical(0xffffffff81a32000)
                entries = []
                for level in (2, 1, 0):
                    address = table + ((va >> (12+9*level)) & 511)*8
                    pte = struct.unpack("<Q", read(address, 8))[0]
                    entries.append({"level": level, "address": hex(address), "pte": hex(pte)})
                    if not pte & 1 or (pte & 6) == 4:
                        raise ValueError("Invalid kernel PTE")
                    ppn = (pte >> 10) & ((1 << 44)-1)
                    if pte & 10:
                        low_mask = (1 << (9*level))-1
                        if ppn & low_mask:
                            raise ValueError("Misaligned superpage")
                        expected_ppn = ppn | ((va >> 12) & low_mask)
                        wrong_ppn = ppn
                        if level:
                            # Verbatim slice indices from the sealed SV39 MMU.
                            mask = ((1 << (9*level))-1) << 12
                            wrong_ppn = (ppn & ~mask) | (va & mask)
                        wrong_pa = wrong_ppn << 12
                        return {"entries": entries, "page_bytes": 1 << (12+9*level),
                                "physical": hex((expected_ppn << 12) | (va & 4095)),
                                "expected_ppn": hex(expected_ppn),
                                "predicted_buggy_ppn_if_page_q_matches": hex(wrong_ppn),
                                "predicted_ni": (wrong_pa < 0x10000000 or
                                                 0x40000000 <= wrong_pa < 0x80000000)}
                    table = ppn << 12
                raise ValueError("No leaf PTE")

            for repeat in range(2):
                offset = struct.unpack("<Q", read(physical(0xffffffff81a61620), 8))[0]
                curr_va = (offset + 0xffffffff80e48940 + 0xa80) & MASK
                task = struct.unpack("<Q", read(physical(curr_va), 8))[0]
                metadata = struct.unpack("<6Q", read(physical(task)+0xb80, 48))
                mapping = walk(task+0xb80)
                if int(mapping["physical"], 16) != physical(task)+0xb80:
                    raise ValueError("Kernel PTE disagrees with direct map")
                values.append({"per_cpu_offset": hex(offset), "curr_pointer_va": hex(curr_va),
                               "task_va": hex(task), "task_pa": hex(physical(task)),
                               "metadata": dict(zip(("vstart", "vl", "vtype", "vcsr", "vlenb", "datap"),
                                                    map(hex, metadata))),
                               "following_scalar_vaddrs": [hex(task+x) for x in (0xb80, 0xb90, 0xb88)],
                               "kernel_page_walk": mapping})
            report["samples"] = values
            report["after"] = capture_snapshot(t)
            report["stable_memory"] = values[0] == values[1]
            before, after = report["before"]["core"], report["after"]["core"]
            report["stable_execution"] = (before["retired"] == after["retired"] and
                                           before["head_pc"] == after["head_pc"] and
                                           after["cycles"] > before["cycles"])
            if not report["stable_memory"] or not report["stable_execution"]:
                raise ValueError("State changed during observation")
    except Exception as exc:
        report["error"] = str(exc)
        raise
    finally:
        (a.out / "report.json").write_text(json.dumps(report, indent=2)+"\n")
        print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
