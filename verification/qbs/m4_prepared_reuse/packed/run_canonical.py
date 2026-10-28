#!/usr/bin/env python3
"""Qualify the shared packed header without changing the sealed runtime/benchmark."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT / "verification/qbs"))
from run_half_scale_soc import atomic_json, digest, hashes
from run_tile_context_engine import run_command


def opcodes(text):
    return [m.group(1) for line in text.splitlines()
            if (m := re.match(r"^\s*[0-9a-f]+:\s+([0-9a-f]{4,8})\s", line))]


def compare_codegen(texts, relocations, headers):
    code = [opcodes(text) for text in texts]
    if not code[0] or len(code[0]) != len(code[1]):
        raise ValueError("Producer instruction count changed")
    changed = [i for i, (a,b) in enumerate(zip(*code)) if a != b]
    if not changed:
        return dict(object_instructions_equal=True, assertion_line_only_difference=False,
                    object_instruction_count=len(code[0]))
    if len(changed) != 1:
        raise ValueError("Non-diagnostic producer opcode changes")
    details = []
    for text, relocs, header in zip(texts, relocations, headers):
        rows = [m.groups() for line in text.splitlines()
                if (m := re.match(r"^\s*([0-9a-f]+):\s+([0-9a-f]{4,8})\s+(.*)$", line))]
        assertion_lines = [i for i,line in enumerate(header.splitlines(),1) if line.strip().startswith("assert(")]
        if len(assertion_lines) != 1:
            raise ValueError("Assertion source identity")
        index = changed[0]
        address, opcode, assembly = rows[index]
        if re.sub(r"\s+", "", assembly) != "lia2,"+str(assertion_lines[0]):
            raise ValueError("Changed opcode is not the exact assertion line argument")
        # GCC emits the assertion-only block last. Its sole outgoing call must
        # be __assert_fail, with only argument setup/register saves in between.
        block = text[text.index("\n"+next(line for line in text.splitlines()
                    if line.startswith("000") and "<.L2>:" in line)):]
        if not re.search(r"^\s*"+address+r":",block,re.M):
            raise ValueError("Line argument outside assertion-only block")
        calls = re.findall(r"^([0-9a-f]+)\s+R_RISCV_CALL_PLT\s+__assert_fail\s*$",relocs,re.M)
        if len(calls) != 1 or int(calls[0],16) <= int(address,16):
            raise ValueError("Assertion call relocation")
        tail = rows[index+1:]
        if not tail or tail[-1][2].split()[0] != "jalr":
            raise ValueError("Assertion block is not terminal")
        for addr, _, asm in tail:
            mnemonic = asm.split()[0]
            if mnemonic not in ("auipc","mv","sd","jalr") or (mnemonic != "sd" and
                    re.match(r"\w+\s+a2(?:,|\s|$)",asm)):
                raise ValueError("Assertion line escapes into functional work")
        details.append(dict(address=address,opcode=opcode,line=assertion_lines[0],assert_call=calls[0]))
    return dict(object_instructions_equal=False,assertion_line_only_difference=True,
                object_instruction_count=len(code[0]),diagnostic_difference=details)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    out = parser.parse_args().output.resolve()
    if not out.is_relative_to(ROOT / "verification/out") or out.exists():
        raise ValueError("Fresh independent output required")
    accepted = ROOT / "verification/out/m4-packed-extent-20261027-01"
    prototype = ROOT / "verification/out/m4-packed-reference-20261027-01"
    pins = json.loads((accepted / "manifest.json").read_text())
    if json.loads((accepted / "result.json").read_text())["state"] != "PASS" or hashes(map(Path,pins)) != pins:
        raise ValueError("Accepted extent/prototype identity changed")
    source = HERE / "canonical_producer.cpp"
    header = ROOT / "software/qbs/ggml/q8_K-m4-packed.h"
    compile_cmd = json.loads((prototype / "compile-1.command.json").read_text())
    link_cmd = json.loads((accepted / "link.command.json").read_text())
    qemu_cmd = json.loads((accepted / "qemu-1024.command.json").read_text())
    pins.update(hashes([Path(__file__), source, header, accepted / "result.json",
                       accepted / "link.command.json", accepted / "qemu-1024.command.json",
                       prototype / "compile-1.command.json"]))
    out.mkdir(parents=True)
    state = dict(state="PREPARING", pid=os.getpid(), child_pid=None, performance_measured=False,
                 runtime_installed=False)

    def save():
        atomic_json(out / "status.json", state)

    def started(pid):
        state["child_pid"] = pid
        save()

    def run(command, name, limit):
        command = list(map(str,command))
        atomic_json(out / (name + ".command.json"), command)
        state.update(state=name.upper(), child_pid=None)
        save()
        if run_command(command, out / (name + ".log"), limit, os.environ.copy(), started):
            raise RuntimeError(name + " failed")

    try:
        obj = out / "canonical.o"
        compile_cmd[compile_cmd.index("-c")+1] = str(source)
        compile_cmd[compile_cmd.index("-o")+1] = str(obj)
        run(compile_cmd,"compile",180)
        objdump = Path(compile_cmd[0]).with_name("riscv64-linux-objdump")
        listings = []
        relocations = []
        for name, path in (("prototype", prototype/"1.o"),("canonical",obj)):
            text = subprocess.check_output([str(objdump),"-d",str(path)],text=True)
            (out / (name + ".asm")).write_text(text)
            relocs = subprocess.check_output([str(objdump),"-r",str(path)],text=True)
            (out/(name+".relocations")).write_text(relocs)
            listings.append(text)
            relocations.append(relocs)
        codegen = compare_codegen(listings,relocations,
                                  [(HERE.parent/"packed_candidate.h").read_text(),header.read_text()])
        atomic_json(out/"codegen.json",codegen)
        old_obj = str(prototype/"1.o")
        if link_cmd.count(old_obj) != 1:
            raise ValueError("Unreviewed link shape")
        link_cmd[link_cmd.index(old_obj)] = str(obj)
        link_cmd[link_cmd.index("-o")+1] = str(out/"test")
        run(link_cmd,"link",180)
        init = ROOT / "verification/out/q8k-decode-layout-full-20261026-01/init"
        cpio = Path("/home/wangwy/llama/platforms/cva6-qemu/sdk/buildroot/output/build/linux-6.19.6/usr/gen_init_cpio")
        recipe = out / "initramfs.list"
        recipe.write_text("dir /dev 755 0 0\nnod /dev/console 600 0 0 c 5 1\n" +
                          f"file /init {init} 755 0 0\nfile /test {out/'test'} 755 0 0\n")
        with (out/"initramfs.cpio").open("xb") as stream:
            subprocess.run([str(cpio),str(recipe)],stdout=stream,check=True,timeout=60)
        pins.update(hashes([obj,out/"test",recipe,out/"initramfs.cpio",init,cpio,objdump,
                           out/"canonical.asm",out/"prototype.asm",out/"canonical.relocations",
                           out/"prototype.relocations",out/"codegen.json"]))
        atomic_json(out/"manifest.json",pins)
        qemu_cmd[qemu_cmd.index("-initrd")+1] = str(out/"initramfs.cpio")
        results = []
        for vlen in (128,256,512,1024):
            command = list(qemu_cmd)
            command[command.index("-cpu")+1] = f"rv64,v=true,vlen={vlen},elen=64,zfh=true,zvfh=true,xaraqbs=false"
            name = "qemu-" + str(vlen)
            run(command,name,600)
            log = out / (name+".log")
            lines = log.read_text().splitlines()
            if lines.count("PACKED_EXTENT_PASS checks=576 domain_checks=28 shapes=8 patterns=12 max_k=8192") != 1 or \
                    lines.count("GUEST_TEST_EXIT=0") != 1:
                raise ValueError("Incomplete shared-header extent acceptance")
            results.append(dict(vlen=vlen,checks=576,domain_checks=28,log_sha256=digest(log)))
        if hashes(map(Path,pins)) != pins:
            raise ValueError("Execution source drift")
        state.update(state="PASS",configurations=results,codegen=codegen,
                     scope="Shared kernel equivalence and numerical gate; no runtime dispatch or whole-model acceptance")
    except BaseException as exc:
        state.update(state="FAIL",error=repr(exc))
        raise
    finally:
        state["child_pid"] = None
        save()
        atomic_json(out/"result.json",state)


if __name__ == "__main__":
    main()
