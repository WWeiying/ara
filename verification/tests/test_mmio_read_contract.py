"""Host tests only; synthetic evidence exercises the checker, not RTL coverage."""

from pathlib import Path
import re
from unittest.mock import Mock

import pytest

import run_mmio_read_contract as runner


@pytest.mark.parametrize("offset,size,mask", [
    (0, 0, 0x01), (7, 0, 0x80), (0, 1, 0x03), (1, 1, 0x02),
    (2, 1, 0x0c), (3, 1, 0x08), (6, 1, 0xc0), (7, 1, 0x80),
    (0, 2, 0x0f), (3, 2, 0x08), (4, 2, 0xf0), (5, 2, 0xe0),
    (0, 3, 0xff), (3, 3, 0xf8), (6, 3, 0xc0), (7, 3, 0x80),
])
def test_read_byte_interval(offset, size, mask):
    beat, = runner.read_beats(runner.BASE + offset, size, 0)
    assert beat["lanes"] == mask
    assert beat["banks"] == [(runner.BASE + b*4, mask >> (b*4) & 15)
                              for b in range(2) if mask & (15 << (b*4))]


def test_unaligned_first_burst_beat():
    beats = runner.read_beats(runner.BASE + 0x163, 2, 2)
    assert [b["address"]-runner.BASE for b in beats] == [0x163, 0x164, 0x168]
    assert [b["lanes"] for b in beats] == [8, 0xf0, 15]
    assert [b["last"] for b in beats] == [0, 0, 1]


@pytest.mark.parametrize("offset,profile,error", [(0, 1, False), (4, 1, True),
                                                  (8, 1, False), (12, 1, True),
                                                  (8, 2, True), (12, 2, False),
                                                  (0x38, 1, True), (0x3c, 1, False)])
def test_selected_bank_error_not_neighbor(offset, profile, error):
    beat, = runner.read_beats(runner.BASE + offset, 2, 0)
    assert (not all(runner.mapped(a, profile) for a, _ in beat["banks"])) == error


def kv(values):
    return " ".join(f"{key}={value}" for key, value in values.items())


def evidence():
    console = ["MMIO_CONFIG axi_data=64 axi_addr=48 axi_id=4 axi_user=2 reg_data=32 cut=1"]
    rows, counts = [], dict.fromkeys(runner.TOTALS, 0)
    case = runner.CASES[0]
    profile = 0

    def row(**values):
        value = dict.fromkeys(sorted(runner.FIELDS), "0")
        value.update(rst="1", case=case, cycle=str(len(rows)), bresp="00", rresp="00", error_profile=str(profile))
        value.update({k: str(v) for k, v in values.items()})
        rows.append(value)

    def reg(address, be, write=False):
        for ready in (0, 1):
            row(regv=1, regr=ready, regaddr=f"{address:x}", regbe=f"{be:x}", regw=int(write),
                regerr=int(not runner.mapped(address, profile)))
        counts["regs"] += 1

    def read(offset, size, length=0):
        id_ = counts["ar"] % 16
        console.append(f"MMIO_AR seq={counts['ar']} cycle={len(rows)} case={case} addr={runner.BASE+offset:x} id={id_:x} size={size} len={length}")
        row(arv=1, arr=1, araddr=f"{runner.BASE+offset:x}", arid=f"{id_:x}", arsize=f"{size:x}",
            arlen=f"{length:x}", wv=int(case == "mixed_channels"))
        counts["ar"] += 1
        for beat in runner.read_beats(runner.BASE+offset, size, length):
            response = 0 if all(runner.mapped(a, profile) for a, _ in beat["banks"]) else 2
            banks = sum(1 << ((a % 8)//4) for a, _ in beat["banks"])
            console.append(f"MMIO_EXPECT_R beat={counts['r']} id={id_:x} addr={beat['address']:x} lanes={beat['lanes']:x} banks={banks:x} last={beat['last']} resp={response:02b}")
            for address, be in beat["banks"]:
                reg(address, be)
            for ready in (0, 0, 1):
                row(rv=1, rr=ready, rid=f"{id_:x}", rl=beat["last"], rresp=f"{response:02b}", arv=int(not ready))
            console.append(f"MMIO_R beat={counts['r']} cycle={len(rows)-1} id={id_:x} last={beat['last']} resp={response:02b} data=0")
            counts["r"] += 1

    def write(offset, strobes):
        id_ = counts["aw"] % 16
        address = runner.BASE + offset
        console.append(f"MMIO_AW seq={counts['aw']} cycle={len(rows)} case={case} addr={address:x} id={id_:x} size=3")
        row(awv=1, awr=1, awaddr=f"{address:x}", awid=f"{id_:x}", awsize=3)
        counts["aw"] += 1
        console.append(f"MMIO_W seq={counts['w']} cycle={len(rows)} data=0 strb={strobes:x}")
        row(wv=1, wr=1, ws=f"{strobes:x}", wl=1)
        counts["w"] += 1
        banks = [(address-address % 8 + b*4, strobes >> (b*4) & 15)
                 for b in range(2) if strobes & (15 << (b*4))]
        response = 0 if all(runner.mapped(a, profile) for a, _ in banks) else 2
        console.append(f"MMIO_EXPECT_B beat={counts['b']} id={id_:x} addr={address:x} strb={strobes:x} banks=0 resp={response:02b}")
        for a, be in banks:
            reg(a, be, True)
        for ready in (0, 1):
            row(bv=1, br=ready, bid=f"{id_:x}", bresp=f"{response:02b}")
        console.append(f"MMIO_B beat={counts['b']} cycle={len(rows)-1} id={id_:x} resp={response:02b}")
        counts["b"] += 1

    def finish():
        console.append(f"MMIO_CASE name={case} status=PASS failures=0 " + kv({k: counts[k] for k in ('ar', 'r', 'aw', 'b', 'regs')}))
        console.append(f"MMIO_RESET case={case} cycle={len(rows)}")
        row(rst=0)

    for size in range(4):
        for lane in range(8):
            read(lane, size)
    finish()
    case = "queued_reads"
    for k in range(8):
        read(0x80+8*k+(k % 2)*4, k % 3)
    finish()
    case = "mixed_channels"
    for offset, be in ((0x180, 15), (0x184, 0xf0), (0x188, 0x81), (0x18c, 0)):
        write(offset, be)
    for offset, size in ((0x94, 2), (0x99, 0), (0xa0, 2), (0xa6, 1),
                         (0xa8, 3), (0xb4, 2), (0x180, 3), (0x188, 3)):
        read(offset, size)
    finish()
    case = "incr_bursts"
    for offset, size, length in ((0x100, 2, 3), (0x124, 1, 3), (0x140, 3, 1), (0x163, 2, 2)):
        read(offset, size, length)
    finish()
    case = "error_mapping"; profile = 1
    for offset in (0, 4, 8, 12, 0x30, 0x34, 0x38, 0x3c):
        read(offset, 2)
    read(0x30, 3); read(0x38, 3); read(0x200, 2)
    profile = 2
    read(8, 2); read(12, 2)
    write(0x34, 0xf0); write(0x38, 15)
    finish()
    assert counts == runner.TOTALS
    stalls = dict(r_stalls=2*counts["r"], b_stalls=counts["b"], reg_stalls=counts["regs"],
                  queued_ar=2*counts["r"], held_w_reads=8, bursts=4, unaligned=18)
    console.append("MMIO_RESULT status=PASS failures=0 cases=5 " + kv(counts) +
                   f" checks=1234 cycles={len(rows)} " + kv(stalls))
    probe = [f"# MMIO_PROBE schema=1 sample=pre_edge max_cycles={runner.MAX_CYCLES}",
             *[kv(r) for r in rows], f"# END rows={len(rows)} completed=1 " + kv(counts) + " checks=1234"]
    return "\n".join(console), "\n".join(probe)


def test_synthetic_positive():
    assert runner.analyze(*evidence())["errors"] == []


@pytest.mark.parametrize("suffix", ["Fatal: late", "Error-[BAD] late", "Assertion failed",
                                   "MMIO_MISMATCH code=extra_register case=size_lanes cycle=9 r=0 b=0 reg=2"])
def test_late_fail_not_pass(suffix):
    console, probe = evidence()
    assert runner.analyze(console+"\n"+suffix, probe)["errors"]


@pytest.mark.parametrize("marker", ["MMIO_CASE name=size_lanes", "MMIO_RESET case=queued_reads",
                                    "MMIO_AR seq=0 ", "MMIO_EXPECT_R beat=0 ", "MMIO_RESULT"])
def test_missing_or_duplicate_marker(marker):
    console, probe = evidence()
    line = next(line for line in console.splitlines() if line.startswith(marker))
    for bad in (console.replace(line, ""), console+"\n"+line):
        assert runner.analyze(bad, probe)["errors"]


@pytest.mark.parametrize("old,new", [("cycle=1 ", "cycle=0 "), ("completed=1", "completed=0"),
                                    ("regbe=1", "regbe=0"), ("rresp=00", "rresp=10"),
                                    ("araddr=4000000", "araddr=4"), ("rst=1", "rst=x")])
def test_corrupted_raw_evidence(old, new):
    console, probe = evidence()
    assert old in probe
    assert runner.analyze(console, probe.replace(old, new))["errors"]


def test_missing_probe():
    console, probe = evidence()
    for bad in ("", "\n".join(probe.splitlines()[:-1])):
        assert runner.analyze(console, bad)["errors"]


def test_prepare_only_exact_override(tmp_path, monkeypatch):
    mmio = runner.ROOT / "verification/out/mmio-fixed-candidate-20260922-03/rtl"
    if not mmio.is_dir():
        pytest.skip("isolated candidate unavailable")
    command = Mock(side_effect=AssertionError("no EDA in prepare-only"))
    monkeypatch.setattr(runner, "command_run", command)
    report = runner.run(mmio, tmp_path / "out", prepare_only=True)
    assert report["status"] == "NOT_RUN", report["errors"]
    command.assert_not_called()
    for name in runner.SOURCES:
        record = report["sources"][f"rtl/{name}"]
        root = mmio if name in runner.OVERRIDES else runner.EXPORT
        assert Path(record["path"]) == (root / name).resolve()
        assert runner.sha256(record["frozen"]) == runner.sha256(root / name)
    for argument in runner.compile_command(tmp_path / "out", "vcs"):
        if argument.endswith(".sv") or argument.startswith("+incdir+"):
            assert str(tmp_path / "out/inputs") in argument


def test_baseline_prepare_does_not_claim_pass(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "command_run", Mock(side_effect=AssertionError("no EDA")))
    report = runner.run(runner.EXPORT, tmp_path / "baseline", prepare_only=True)
    assert report["status"] == "NOT_RUN"


def test_missing_override_and_stale_output(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "command_run", Mock(side_effect=AssertionError("no EDA")))
    report = runner.run(tmp_path / "absent", tmp_path / "out", prepare_only=True)
    assert report["status"] == "FAIL"
    with pytest.raises(ValueError):
        runner.run(tmp_path / "absent", tmp_path / "out", prepare_only=True)


def test_input_output_overlap_rejected(tmp_path):
    with pytest.raises(ValueError, match="input source"):
        runner.run(tmp_path, tmp_path / "child", prepare_only=True)


def test_closure_files_and_headers():
    assert set(runner.OVERRIDES) <= set(runner.SOURCES)
    for name in runner.SOURCES + runner.HEADERS:
        path = runner.EXPORT / name
        assert path.is_file(), path
        text = re.sub(r"//[^\n]*|/\*.*?\*/", "", path.read_text(), flags=re.S)
        for include in re.findall(r'`include\s+"([^"]+)"', text):
            if include != "uvm_macros.svh":
                assert any(str(Path(d) / include) in runner.HEADERS for d in runner.INCLUDES)


def test_tb_w_marker_and_finite_matrix_constants():
    text = runner.TB.read_text()
    assert '"MMIO_W seq=%0d cycle=%0d data=%h strb=%h", w_count-1,' in text
    assert "for (int lane = 0; lane < 8; lane++)" in text
    assert "unaligned_requests == 18" in text
    assert runner.TOTALS == dict(ar=65, r=74, aw=6, w=6, b=6, regs=91)
