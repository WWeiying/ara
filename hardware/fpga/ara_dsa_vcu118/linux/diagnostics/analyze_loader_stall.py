#!/usr/bin/env python3
"""Offline analysis of the preserved loader stall; not proof of RTL root cause."""
import argparse
import hashlib
import json
from pathlib import Path
import struct

IMAGE_SHA256 = "716aef49389b25a0a3f4deac47de0bb69467a10f1057041cecd0f0621fbbf285"
LOADER_SHA256 = "3b4c54b64962c449f277bea8904fe0d52251e7b2c2531de994c2657129f816fd"


def jal_target(pc, instruction):
    if instruction & 0x7f != 0x6f:
        raise ValueError("Last retired instruction is not JAL")
    imm = (((instruction >> 31) & 1) << 20 |
           ((instruction >> 12) & 255) << 12 |
           ((instruction >> 20) & 1) << 11 |
           ((instruction >> 21) & 1023) << 1)
    if imm & (1 << 20):
        imm -= 1 << 21
    return (pc + imm) & ((1 << 64) - 1)


def inspect_task_capture(directory, loader):
    """Validate one retained task capture; do not infer internal cache state."""
    if hashlib.sha256(loader).hexdigest() != LOADER_SHA256:
        raise ValueError('Wrong loader ELF')
    r = json.loads((directory / 'report.json').read_text())
    if (not r.get('evidence_verified') or r['memory_writes'] or r['reset'] or
            r['cpu_halt'] or r['counter_frozen_before'] or r['counter_frozen_after'] or
            r['image_sha256'] != IMAGE_SHA256 or not r['task_unchanged']):
        raise ValueError('Not a verified stable non-freezing task capture')
    # Earlier probe revisions put a post-collection cleanup failure in error.
    error = r.get('error', '')
    if error and not error.startswith('Owned Vivado tree cleanup failed:'):
        raise ValueError('Capture failed: ' + error)
    for s in ('second', 'after'):
        if r[s]['watchdog_snapshot']:
            raise ValueError('Watchdog-frozen counters')
        for field in ('retired', 'last_pc', 'head_pc', 'trap_count'):
            if r['before']['core'][field] != r[s]['core'][field]:
                raise ValueError('Execution changed: ' + field)
        if r[s]['core']['cycles'] <= r['before']['core']['cycles']:
            raise ValueError('Clock counter did not advance')
    task = (directory / 'task.bin').read_bytes()
    task_pa = int(r['task_va'], 16) - 0xffffffd600000000 + 0x80000000
    if not any(int(row['pa'], 16) == task_pa and bytes.fromhex(row['data']) == task
               for row in r['reads']):
        raise ValueError('Task not present in captured reads')
    if task[1696:1760].split(b'\0', 1)[0].decode('ascii') != r['task_comm']:
        raise ValueError('Task name mismatch')
    bases = []
    words = []
    pages = []
    for label in ('retired_page', 'target_page'):
        matches = [item for item in r['pages'] if item['label'] == label]
        if len(matches) != 1:
            raise ValueError('Missing or duplicated code page')
        item = matches[0]
        data = (directory / (label + '.bin')).read_bytes()
        if len(data) != 4096 or hashlib.sha256(data).hexdigest() != item['sha256']:
            raise ValueError('Corrupted code page')
        offsets = [i for i in range(0, len(loader), 4096) if loader[i:i+4096] == data]
        if len(offsets) != 1:
            raise ValueError('Code does not uniquely match original loader')
        va, pa = int(item['requested_va'], 16), int(item['pa'], 16)
        if not any(int(row['pa'], 16) == (pa & ~4095) and bytes.fromhex(row['data']) == data
                   for row in r['reads']):
            raise ValueError('Code page missing from reads')
        table = int(r['pgd_va'], 16) - 0xffffffd600000000 + 0x80000000
        if len(item['page_walk']) != 3:
            raise ValueError('Expected three-level page walk')
        for level, entry in zip((2, 1, 0), item['page_walk']):
            address = table + ((va >> (12 + 9 * level)) & 511) * 8
            pte = int(entry['pte'], 16)
            if entry['level'] != level or int(entry['pa'], 16) != address:
                raise ValueError('Page walk address mismatch')
            if not any(int(row['pa'], 16) == address and
                       bytes.fromhex(row['data']) == struct.pack('<Q', pte) for row in r['reads']):
                raise ValueError('PTE missing from captured reads')
            if (level and pte & 15 != 1) or (not level and pte & 0x59 != 0x59):
                raise ValueError('Not a valid user executable three-level mapping')
            table = ((pte >> 10) & ((1 << 44) - 1)) << 12
        if table != pa & ~4095 or va & 4095 != pa & 4095:
            raise ValueError('Translation differs from recorded physical address')
        bases.append((va & ~4095) - offsets[0])
        words.append(struct.unpack_from('<I', data, va & 4095)[0])
        pages.append(item)
    if bases[0] != bases[1]:
        raise ValueError('Loader bases differ')
    pc = r['before']['core']['last_pc']
    target = jal_target(pc, words[0])
    if (pc != int(pages[0]['requested_va'], 16) or target != int(pages[1]['requested_va'], 16)
            or target != int(r['jal_target'], 16)):
        raise ValueError('JAL target does not match captured pages')
    reads = sum(len(bytes.fromhex(row['data'])) // 8 for row in r['reads'])
    delta = r['after']['ddr1']['ar_count'] - r['before']['ddr1']['ar_count']
    return r, dict(state='capture_consistent_RTL_attribution_unproven',
                   task=r['task_comm'], retired_pc=hex(pc), loader_base=hex(bases[0]),
                   loader_pc_offset=hex(pc-bases[0]), jal_target=hex(target),
                   target_offset=hex(target-bases[0]), diagnostic_read_ops=reads,
                   ddr_ar_delta=delta, reads_explain_ar_delta=reads == delta,
                   last_ar_covers_root_pte=(r['before']['ddr1']['last_ar_addr'] ==
                                           int(pages[1]['page_walk'][0]['pa'], 16) & ~31),
                   cleanup_error=r.get('cleanup_error', error))


def inspect_page(directory, loader):
    report = json.loads((directory / "report.json").read_text())
    page = (directory / "code_page.bin").read_bytes()
    if len(page) != 4096 or hashlib.sha256(page).hexdigest() != report["code_sha256"]:
        raise ValueError("Code page length/hash mismatch")
    if report["memory_writes"] or report["reset"] or "error" in report:
        raise ValueError("Not a successful read-only capture")
    before, after = report["before"], report["after"]
    for field in ("retired", "last_pc", "head_pc", "trap_count"):
        if before["core"][field] != after["core"][field]:
            raise ValueError("Execution changed during capture: " + field)
    if after["core"]["cycles"] <= before["core"]["cycles"]:
        raise ValueError("Snapshot clock did not advance")
    offsets = [i for i in range(0, len(loader), 4096) if loader[i:i+4096] == page]
    if len(offsets) != 1:
        raise ValueError("Code page does not uniquely match loader")
    leaf = int(report["page_walk"][-1]["pte"], 16)
    # This case uses a 4 KiB U-mode executable page, already accessed.
    if report["page_walk"][-1]["level"] != 0 or leaf & 0x59 != 0x59:
        raise ValueError("Not an accessed user executable 4 KiB leaf")
    va = int(report["code_va"], 16)
    expected_pa = ((leaf >> 10) & ((1 << 44)-1)) << 12
    if int(report["pc_pa"], 16) & ~4095 != expected_pa:
        raise ValueError("Leaf physical address mismatch")
    read_ops = sum(len(bytes.fromhex(row["data"])) // 8 for row in report["reads"])
    ar_delta = after["ddr1"]["ar_count"] - before["ddr1"]["ar_count"]
    return report, page, {"va": hex(va), "pa": hex(expected_pa),
                         "loader_file_offset": hex(offsets[0]),
                         "loader_base": hex(va - offsets[0]),
                         "pte_flags": hex(leaf & 1023),
                         "diagnostic_read_ops": read_ops, "ddr_ar_delta": ar_delta,
                         "reads_account_for_ar_delta": read_ops == ar_delta}


def analyze(source, target, loader, image):
    # Reviewed RX PT_LOAD has p_offset == p_vaddr == 0 in this exact ELF.
    if hashlib.sha256(loader).hexdigest() != LOADER_SHA256:
        raise ValueError("Wrong loader ELF")
    if hashlib.sha256(image).hexdigest() != IMAGE_SHA256:
        raise ValueError("Wrong kernel Image")
    # proc_task_name: addi a1,a1,1696 before sized_strscpy.
    if struct.unpack_from("<I", image, 0x305b7e)[0] != 0x6a058593:
        raise ValueError("Task comm offset oracle mismatch")
    src, page, src_info = inspect_page(source, loader)
    dst, _, dst_info = inspect_page(target, loader)
    for field in ("task_va", "mm_va", "pgd_va"):
        if src[field] != dst[field]:
            raise ValueError("Capture task/mapping differs: " + field)
    for field in ("retired", "last_pc", "head_pc", "trap_count"):
        if src["after"]["core"][field] != dst["before"]["core"][field]:
            raise ValueError("Execution changed between captures")
    if src_info["loader_base"] != dst_info["loader_base"]:
        raise ValueError("Loader base mismatch")
    pc = src["after"]["core"]["last_pc"]
    offset = pc - int(src["code_va"], 16)
    if not 0 <= offset <= 4092:
        raise ValueError("Retired PC outside captured page")
    instruction = struct.unpack_from("<I", page, offset)[0]
    destination = jal_target(pc, instruction)
    if destination != int(dst["requested_va"], 16):
        raise ValueError("Captured target differs from decoded JAL")
    task = (target / "task.bin").read_bytes()
    task_pa = int(dst["task_va"], 16) - 0xffffffd600000000 + 0x80000000
    if not any(int(r["pa"], 16) == task_pa and bytes.fromhex(r["data"]) == task
               for r in dst["reads"]):
        raise ValueError("Task file differs from recorded read")
    comm = task[1696:1760].split(b"\0", 1)[0].decode("ascii")
    return {"state": "evidence_verified_root_cause_unproven", "task_comm": comm,
            "retired_pc": hex(pc), "instruction": hex(instruction),
            "jal_target": hex(destination), "source": src_info, "target": dst_info,
            "limitations": ["Memory page tables are not a readout of SATP or TLB",
                            "head_pc has no validity bit; scoreboard may be empty",
                            "No CPU pipeline ILA in current LTX",
                            "No reset, halt, programming, or RTL repair performed"]}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--capture', type=Path, help='Combined read_stalled_task capture')
    p.add_argument('--loader', type=Path, required=True)
    for name in ("source", "target", "image"):
        p.add_argument("--" + name, type=Path)
    args = p.parse_args()
    if args.capture:
        if args.source or args.target or args.image:
            p.error('--capture cannot be combined with --source/--target/--image')
        print(json.dumps(inspect_task_capture(args.capture, args.loader.read_bytes())[1], indent=2))
        return
    if not all((args.source, args.target, args.image)):
        p.error('Supply --capture or all of --source/--target/--image')
    print(json.dumps(analyze(args.source, args.target, args.loader.read_bytes(),
                             args.image.read_bytes()), indent=2))


if __name__ == "__main__":
    main()
