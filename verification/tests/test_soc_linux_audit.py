"""Host-only negative controls for the independent SoC Linux result audit."""

import hashlib
import json

from fpga.check_soc_linux import PASS_LINE, audit, console_evidence
from fpga.check_soc_milestone import audit as audit_milestone


def sha(data):
    return hashlib.sha256(data).hexdigest()


def valid_log(quiet_opensbi=False):
    uart = (
        *(("Linux version 6.0", "SBI specification v3.0 detected",
           "SBI implementation ID=0x1 Version=0x10007") if quiet_opensbi else
          ("OpenSBI v1.0", "Linux version 6.0")),
        "Ara verification Linux init reached",
        "[LINUX_RVV] PASS arithmetic_load_store elements=101",
        "[LINUX_RVV] PASS vfredmax_boundary",
        "[LINUX_RVV] PASS preempt_child bytes=4096",
        "[LINUX_RVV] PASS preempt_parent bytes=4096",
        "[LINUX_RVV] PASS signal_return bytes=4096",
        "[LINUX_RVV] PASS scalar_fault_return bytes=4096",
        "[LINUX_RVV] PASS illegal_instruction_return bytes=4096",
        "RVV fallback userspace PASS", "RVV context switch and fault return PASS",
        "ARA_LINUX_USERSPACE PASS",
    )
    return "\n".join(
        [*("[CANDIDATE_UART] " + line for line in uart),
         "[CANDIDATE_COUNTS] cycles=100 commits=40 rom=5 payload=35 traps=4 last_pc=0",
         "[CANDIDATE_COUNTS] mmio_read=3 mmio_write=2 mailbox_write=0 rtc_ticks=10",
         "[CANDIDATE_COUNTS] ddr_ar=3 ddr_r=4 ddr_aw=2 ddr_w=2 ddr_b=2",
         "[CANDIDATE_COUNTS] uart_rx=10 uart_tx=10 handshake=1 exec_ack=1 entry_retired=1 uart_pass=0",
         PASS_LINE]) + "\n"


def test_valid_linux_console():
    assert console_evidence(valid_log())["passed"]


def test_quiet_boot_requires_linux_sbi_identity_and_rejects_banner():
    log = valid_log(quiet_opensbi=True)
    assert console_evidence(log, quiet_opensbi=True)["passed"]
    assert not console_evidence(log)["passed"]
    assert not console_evidence(log.replace("[CANDIDATE_UART] SBI implementation ID=0x1 Version=0x10007\n", ""),
                                quiet_opensbi=True)["passed"]
    assert not console_evidence(log.replace("[CANDIDATE_UART] Linux version 6.0\n",
                                             "[CANDIDATE_UART] OpenSBI v1.7\n"
                                             "[CANDIDATE_UART] Linux version 6.0\n"),
                                quiet_opensbi=True)["passed"]


def test_rejects_early_pass_and_missing_user_test():
    log = valid_log()
    assert not console_evidence(log.replace("[CANDIDATE_UART] [LINUX_RVV] PASS vfredmax_boundary\n", ""))["passed"]
    assert not console_evidence(log.replace(PASS_LINE, "") + PASS_LINE + "\n" + PASS_LINE)["passed"]
    assert not console_evidence(log.replace("[CANDIDATE_UART] ARA_LINUX_USERSPACE PASS\n", "")
                                .replace(PASS_LINE, PASS_LINE + "\n[CANDIDATE_UART] ARA_LINUX_USERSPACE PASS"))["passed"]


def test_rejects_wrong_order_failures_and_zero_activity():
    log = valid_log()
    assert not console_evidence(log.replace("[CANDIDATE_UART] Linux version 6.0\n", "")
                                .replace("[CANDIDATE_UART] OpenSBI v1.0",
                                         "[CANDIDATE_UART] Linux version 6.0\n[CANDIDATE_UART] OpenSBI v1.0"))["passed"]
    assert not console_evidence(log + "[LINUX_RVV] FAIL test\n")["passed"]
    assert not console_evidence(log.replace("traps=4", "traps=0"))["passed"]
    assert not console_evidence(log.replace("ddr_aw=2", "ddr_aw=0"))["passed"]
    assert not console_evidence(log + "a_invalid_read_data: started at 10 failed at 10\n")["passed"]


def test_cache_probe_distinguishes_unused_bytes_from_selected_unknowns():
    log = valid_log() + "[CACHE_PROBE_ACTIVE] selected-byte and response-ID checks enabled\n"
    assert console_evidence(log, cache_probe=True)["passed"]
    assert console_evidence(log + "a_invalid_read_data: started at 10 failed at 10\n",
                            cache_probe=True)["passed"]
    assert not console_evidence(valid_log(), cache_probe=True)["passed"]
    for marker in ("[CACHE_SELECTED_X]", "[CACHE_UNMATCHED_RESPONSE]", "a_invalid_write_data"):
        assert not console_evidence(log + marker + " cycle=10\n", cache_probe=True)["passed"]


def test_milestone_audit_checks_frozen_inputs_and_does_not_claim_boot(tmp_path):
    output = tmp_path / "milestone"
    sim = output / "sim"
    sim.mkdir(parents=True)
    records = {}
    for name in ("fw_jump.elf", "ara_vcu118.dtb", "Image", "initramfs.cpio"):
        relative = "package/linux/artifacts/" + name
        path = output / "inputs" / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(name.encode())
        records[relative] = {"sha256": sha(path.read_bytes()),
                             "size_bytes": path.stat().st_size}
    inputs = {"mode": "linux", "entry": 0x80000000,
              "quiet_opensbi": False, "inputs": records}
    (output / "inputs.json").write_text(json.dumps(inputs))
    simv = output / "compile/simv"
    simv.parent.mkdir()
    simv.write_bytes(b"launcher")
    library = output / "compile/simv.daidir/library.so"
    library.parent.mkdir()
    library.write_bytes(b"design")
    driver = output / "run_driver.py"
    driver.write_bytes(b"driver")
    argv = [str(simv), "+LINUX_MODE", "+BOOT_ENTRY=80000000",
            "+MEM_HEX=" + str(output / "inputs/generated/memory.hex")]
    command = {"argv": argv, "cwd": str(sim), "returncode": -1,
               "last_progress_cycle": 100, "uart_milestone_reached": "Linux version"}
    (sim / "command.json").write_text(json.dumps(command))
    (sim / "console.log").write_text("[CANDIDATE_UART] Linux version 6.19.6\n")
    summary = {"status": "LINUX_UART_MILESTONE_REACHED",
               "inputs_manifest_sha256": sha((output / "inputs.json").read_bytes()),
               "technology": {"passed": True}, "simulation": command,
               "simv_sha256": sha(simv.read_bytes()),
               "simv_image_sha256": {"simv": sha(simv.read_bytes()),
                                        "simv.daidir/library.so": sha(library.read_bytes())},
               "run_driver_sha256": sha(driver.read_bytes())}
    (output / "summary.json").write_text(json.dumps(summary))
    result = audit_milestone(output, "Linux version")
    assert result["status"] == "PASS"
    assert "not Linux boot" in result["scope"]
    command["returncode"] = 0
    (sim / "command.json").write_text(json.dumps(command))
    assert audit_milestone(output, "Linux version")["status"] == "FAIL"
    command["returncode"] = -1
    (sim / "command.json").write_text(json.dumps(command))
    library.write_bytes(b"changed")
    assert any("VCS image differs" in error for error in
               audit_milestone(output, "Linux version")["errors"])
    library.write_bytes(b"design")
    (sim / "console.log").write_text("[CANDIDATE_UART] Kernel panic\n")
    assert audit_milestone(output, "Linux version")["status"] == "FAIL"


def test_result_audit_checks_frozen_inputs_and_vcs_image(tmp_path):
    output = tmp_path / "linux-run"
    sim = output / "sim"
    sim.mkdir(parents=True)
    records = {}
    for name in ("fw_jump.elf", "ara_vcu118.dtb", "Image", "initramfs.cpio"):
        relative = "package/linux/artifacts/" + name
        path = output / "inputs" / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        data = name.encode()
        path.write_bytes(data)
        records[relative] = {"sha256": sha(data), "size_bytes": len(data)}
    manifest = {"mode": "linux", "entry": 0x80000000, "inputs": records}
    package_manifest = output / "inputs/package/manifest.json"
    package_manifest.parent.mkdir(parents=True, exist_ok=True)
    package_manifest.write_text(json.dumps({"simulation_only_linux_override": {"quiet_opensbi": False}}))
    records["package/manifest.json"] = {"sha256": sha(package_manifest.read_bytes()),
                                        "size_bytes": package_manifest.stat().st_size}
    (output / "inputs.json").write_text(json.dumps(manifest))
    simv = output / "compile/simv"
    simv.parent.mkdir()
    simv.write_bytes(b"launcher")
    library = output / "compile/simv.daidir/library.so"
    library.parent.mkdir()
    library.write_bytes(b"design")
    argv = [str(simv), "+LINUX_MODE",
            "+MEM_HEX=" + str(output / "inputs/generated/memory.hex"),
            "+BOOT_ENTRY=80000000"]
    command = {"argv": argv, "returncode": 0, "cwd": str(sim)}
    (sim / "command.json").write_text(json.dumps(command))
    (sim / "console.log").write_text(valid_log())
    summary = {
        "status": "LINUX_BOOT_PASS", "inputs_manifest_sha256": sha((output / "inputs.json").read_bytes()),
        "technology": {"passed": True}, "compile": {"returncode": 0},
        "simulation": command, "simv_sha256": sha(simv.read_bytes()),
        "simv_image_sha256": {"simv": sha(simv.read_bytes()),
                               "simv.daidir/library.so": sha(library.read_bytes())},
    }
    (output / "summary.json").write_text(json.dumps(summary))
    assert audit(output)["status"] == "PASS"
    library.write_bytes(b"mutated")
    assert any("VCS image differs" in error for error in audit(output)["errors"])
    library.write_bytes(b"design")
    extra_library = output / "compile/simv.daidir/unrecorded.so"
    extra_library.write_bytes(b"extra")
    assert any("image hashes are missing" in error for error in audit(output)["errors"])
    extra_library.unlink()
    firmware = output / "inputs/package/linux/artifacts/fw_jump.elf"
    firmware.write_bytes(b"mutated")
    assert any("frozen input differs" in error for error in audit(output)["errors"])
    firmware.write_bytes(b"fw_jump.elf")
    manifest["quiet_opensbi"] = True
    package_manifest.write_text(json.dumps({"simulation_only_linux_override": {"quiet_opensbi": True}}))
    records["package/manifest.json"] = {"sha256": sha(package_manifest.read_bytes()),
                                        "size_bytes": package_manifest.stat().st_size}
    (output / "inputs.json").write_text(json.dumps(manifest))
    command["argv"].append("+QUIET_OPENSBI")
    (sim / "command.json").write_text(json.dumps(command))
    (sim / "console.log").write_text(valid_log(quiet_opensbi=True))
    summary["inputs_manifest_sha256"] = sha((output / "inputs.json").read_bytes())
    (output / "summary.json").write_text(json.dumps(summary))
    assert audit(output)["status"] == "PASS"
    package_manifest.write_text(json.dumps({"simulation_only_linux_override": {"quiet_opensbi": False}}))
    assert any("quiet OpenSBI setting differs" in error for error in audit(output)["errors"])
    package_manifest.write_text(json.dumps({"simulation_only_linux_override": {"quiet_opensbi": True}}))
    command["argv"].remove("+QUIET_OPENSBI")
    (sim / "command.json").write_text(json.dumps(command))
    assert any("simulation command differs" in error for error in audit(output)["errors"])
