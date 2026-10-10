"""Generator input isolation tests; never invoke EDA or touch live dependencies."""

import hashlib
import json
from pathlib import Path
import subprocess

import pytest

from fpga import prepare_plic as prepare


def test_dts_migration_is_single_and_explicit():
    text = "riscv,ndev = <51>;\nkeep = <0x04000000>;\n"
    assert prepare.candidate_dts(text) == text.replace("<51>", "<57>")


@pytest.mark.parametrize("text", ["", "riscv,ndev = <57>;",
                                  "riscv,ndev = <51>;\nriscv,ndev = <51>;"])
def test_dts_unknown_input_is_not_silently_rewritten(text):
    with pytest.raises(ValueError, match="unexpected DTS"):
        prepare.candidate_dts(text)


def fixture_repo(tmp_path, monkeypatch):
    repo = tmp_path / "source"
    repo.mkdir()
    def git(*args):
        return subprocess.run(["git", "-C", str(repo), *args], check=True,
                              capture_output=True, text=True).stdout.strip()
    git("init", "-q")
    (repo / "input.cfg").write_text("pinned input\n")
    git("add", "input.cfg")
    git("-c", "user.name=fixture", "-c", "user.email=fixture@example.invalid",
        "commit", "-qm", "input")
    monkeypatch.setattr(prepare, "REVISIONS", {"fixture": git("rev-parse", "HEAD")})
    monkeypatch.setattr(prepare, "SUBSETS", {"fixture": ["input.cfg"]})
    return repo


def test_snapshot_matches_pin_and_detects_later_drift(tmp_path, monkeypatch):
    repo = fixture_repo(tmp_path, monkeypatch)
    frozen = tmp_path / "frozen"
    record = prepare.snapshot(repo, "fixture", frozen / "fixture")
    prepare.assert_unchanged({"fixture": record}, frozen)
    assert record["files"]["input.cfg"]["sha256"] == hashlib.sha256(b"pinned input\n").hexdigest()
    (frozen / "fixture/input.cfg").write_text("changed snapshot")
    with pytest.raises(ValueError, match="changed"):
        prepare.assert_unchanged({"fixture": record}, frozen)
    assert (repo / "input.cfg").read_text() == "pinned input\n"


def test_dirty_input_is_rejected_not_reset(tmp_path, monkeypatch):
    repo = fixture_repo(tmp_path, monkeypatch)
    (repo / "input.cfg").write_text("user change")
    with pytest.raises(ValueError, match="modified"):
        prepare.snapshot(repo, "fixture", tmp_path / "frozen")
    assert (repo / "input.cfg").read_text() == "user change"


def test_wrong_revision_is_rejected(tmp_path, monkeypatch):
    repo = fixture_repo(tmp_path, monkeypatch)
    monkeypatch.setattr(prepare, "REVISIONS", {"fixture": "0" * 40})
    with pytest.raises(ValueError, match="revision"):
        prepare.snapshot(repo, "fixture", tmp_path / "frozen")


def test_output_symlink_is_rejected(tmp_path):
    target = tmp_path / "target"
    target.mkdir()
    link = tmp_path / "link"
    link.symlink_to(target, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        prepare.plain_path(link / "new")


# Exact patch contexts, not an RTL model. Host tests exercise the real patch
# utility and Mako, but deliberately stub ipgen rather than claim simulation.
TEMPLATE_CONTEXTS = """  always_comb begin
    complete = '0;
    for (int i = 0 ; i < NumTarget ; i++) begin
      if (complete_we[i]) complete[complete_id[i]] = 1'b1;
    end
  end

  ////////////////////////
  // Register interface //
  ////////////////////////
  //  Limitation of register tool prevents the module from having flexibility to parameters
  //  So, signals are manually tied at the top.
  ${module_instance_name}_reg_top #(
    .reg_req_t (reg_req_t),
    .reg_rsp_t (reg_rsp_t)
  ) u_reg (
    .clk_i,
    .rst_ni,

    .reg_req_i,
    .reg_rsp_o,

    .reg2hw,
    .hw2reg,
    .devmode_i (1'b1)
  );
"""


@pytest.fixture
def generator_fixture(tmp_path, monkeypatch):
    pytest.importorskip("hjson")
    workspace = tmp_path / "workspace"
    monkeypatch.setattr(prepare, "ROOT", workspace)
    monkeypatch.setattr(prepare, "CONTRACT_TEMPLATE_SHA256",
                        hashlib.sha256(TEMPLATE_CONTEXTS.encode()).hexdigest())
    cfg = {"instance_name": "rv_plic", "param_values": prepare.CONFIG}
    inputs = {
        "cheshire": {"hw/rv_plic.cfg.hjson": json.dumps(cfg)},
        "opentitan_peripherals": {prepare.CONTRACT_TEMPLATE: TEMPLATE_CONTEXTS,
                                  "util/ipgen.py": "# host fixture, not executed\n"},
        "register_interface": {"vendor/lowrisc_opentitan/util/reggen/__init__.py": ""},
    }
    roots, revisions = {}, {}
    for name, files in inputs.items():
        repo = tmp_path / "sources" / name
        repo.mkdir(parents=True)
        for relative, content in files.items():
            path = repo / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
        prepare.git(repo, "init", "-q")
        prepare.git(repo, "add", ".")
        prepare.git(repo, "-c", "user.name=fixture", "-c", "user.email=fixture@example.invalid",
                    "commit", "-qm", "fixture")
        roots[name] = str(repo)
        revisions[name] = prepare.git(repo, "rev-parse", "HEAD").decode().strip()
    monkeypatch.setattr(prepare, "REVISIONS", revisions)
    monkeypatch.setattr(prepare, "SUBSETS", {name: list(files) for name, files in inputs.items()})
    roots_path = tmp_path / "roots.json"
    roots_path.write_text(json.dumps(roots))
    dts = tmp_path / "original.dts.in"
    dts.write_text("riscv,ndev = <51>;\n")
    output = workspace / "verification/out/candidate"

    class StubGenerator(prepare.NativeRunner):
        def run(self, argv, cwd, label, timeout=300):
            if label in ("patch-version", "contract-patch-check", "contract-patch-apply"):
                return super().run(argv, cwd, label, timeout=timeout)
            self.commands.append({"argv": argv, "cwd": str(cwd), "label": label, "stubbed": True})
            if label == "packages":
                return "host-test-fixture\n"
            if label == "reggen-origin":
                return str(Path(self.environment["PYTHONPATH"]) / "reggen/__init__.py")
            if label == "ipgen":
                destination = Path(argv[argv.index("-o") + 1])
                (destination / "rtl").mkdir(parents=True)
                template = Path(argv[argv.index("-C") + 1]) / "rtl/rv_plic.sv.tpl"
                for name in prepare.RTL:
                    (destination / "rtl" / name).write_text(
                        template.read_text() if name == "rv_plic.sv" else "// host fixture\n")
                (destination / "data").mkdir()
                (destination / "data/rv_plic.ipconfig.hjson").write_text(json.dumps(cfg))
                (destination / "data/rv_plic.hjson").write_text("{}\n")
                return ""
            assert label == "c-header"
            return "/* host fixture */\n"

    monkeypatch.setattr(prepare, "NativeRunner", StubGenerator)
    return output, roots_path, dts, StubGenerator


@pytest.mark.parametrize("enabled", [False, True])
def test_opt_in_isolated_generation_and_provenance(generator_fixture, enabled):
    output, roots, dts, _ = generator_fixture
    kwargs = {"fix_contract": True} if enabled else {}
    report = prepare.prepare(output, roots, dts, **kwargs)
    assert report == json.loads((output / "manifest.json").read_text())
    assert report["status"] == "GENERATED_NOT_VALIDATED"
    assert report["inputs_unchanged"] and not report["applied_to_export"]
    assert report["rtl_simulation"] == report["board_boot"] == "NOT_RUN"
    fix = report["contract_fix"]
    assert fix["requested"] is enabled and fix["applied"] is enabled
    assert fix["functional_validation"] == "NOT_RUN" and not fix["bridge_fix"]
    prepare.assert_unchanged(report["generator_inputs"], output / "inputs")
    frozen = output / "inputs/opentitan_peripherals" / prepare.CONTRACT_TEMPLATE
    assert frozen.read_text() == TEMPLATE_CONTEXTS
    ipgen = next(row for row in report["commands"] if row.get("label") == "ipgen")
    assert (output / "ara_vcu118.dts.in").read_text() == "riscv,ndev = <57>;\n"
    if not enabled:
        assert not (output / "work").exists()
        assert not (output / "inputs/patches").exists()
        assert str(output / "inputs/opentitan_peripherals/util/ipgen.py") in ipgen["argv"]
        assert (output / "rv_plic/rtl/rv_plic.sv").read_text() == TEMPLATE_CONTEXTS
        return
    assert str(output / "work/opentitan_peripherals/util/ipgen.py") in ipgen["argv"]
    assert fix["changed_files"] == [prepare.CONTRACT_TEMPLATE]
    assert fix["patch"]["sha256"] == fix["patch_source"]["sha256"] == prepare.CONTRACT_PATCH_SHA256
    assert fix["template_before"]["sha256"] == prepare.CONTRACT_TEMPLATE_SHA256
    assert fix["template_before"]["sha256"] != fix["template_after"]["sha256"]
    assert fix["generated_core"] == report["files"]["rv_plic/rtl/rv_plic.sv"]
    assert fix["generated_core"]["sha256"] == fix["template_after"]["sha256"]
    assert any("--dry-run" in row["argv"] for row in report["commands"])
    prepare.assert_contract_unchanged(fix)


@pytest.mark.parametrize("src", [2, 31, 32, 33, 58, 64])
@pytest.mark.parametrize("target", [1, 2])
def test_patch_rendering_word_boundary_and_completion_guards(generator_fixture, src, target):
    mako = pytest.importorskip("mako.template")
    output, roots, dts, _ = generator_fixture
    report = prepare.prepare(output, roots, dts, fix_contract=True)
    patched = Path(report["contract_fix"]["template_after"]["path"]).read_text()
    rendered = mako.Template(patched).render(module_instance_name="test_plic", src=src, target=target)
    suffix = "_0" if src > 32 else ""
    for context in range(target):
        assert f"TEST_PLIC_IE{context}{suffix}_OFFSET:" in rendered
    assert rendered.count("_OFFSET:") == target
    assert rendered.count("reg_req_sanitized.wdata[0] = 1'b0;") == target
    assert "case (reg_req_i.addr[BlockAw-1:0])" in rendered
    assert "reg_req_sanitized = reg_req_i;" in rendered
    assert "if (reg_req_i.valid && reg_req_i.write)" in rendered
    assert ".reg_req_i (reg_req_sanitized)" in rendered
    guard = """if (complete_we[i] && complete_id[i] != '0 &&
          complete_id[i] < NumSrc) begin
        if (ie[i][complete_id[i]]) complete[complete_id[i]] = 1'b1;
      end"""
    assert guard in rendered
    # A later disabled context must not clear an earlier context's completion.
    assert rendered.count("complete[complete_id[i]] =") == 1
    assert rendered.count("complete = '0;") == 1
    assert "claim_id" not in rendered and "claim_re" not in rendered


@pytest.mark.parametrize("constant,message", [
    ("CONTRACT_PATCH_SHA256", "patch hash"),
    ("CONTRACT_TEMPLATE_SHA256", "template preimage"),
])
def test_unreviewed_patch_or_preimage_fails_closed(generator_fixture, monkeypatch, constant, message):
    output, roots, dts, _ = generator_fixture
    monkeypatch.setattr(prepare, constant, "0" * 64)
    with pytest.raises(ValueError, match=message):
        prepare.prepare(output, roots, dts, fix_contract=True)
    failure = json.loads((output / "failure.json").read_text())
    assert failure["status"] == "FAILED" and not failure["contract_fix"]["applied"]
    assert not failure["commands"]
    assert not (output / "work").exists() and not (output / "rv_plic").exists()
    prepare.assert_unchanged(failure["generator_inputs"], output / "inputs")


@pytest.mark.parametrize("phase,location,message", [
    ("contract-patch-apply", "work", "unexpected files"),
    ("ipgen", "work", "working inputs changed"),
    ("ipgen", "inputs", "generator input changed"),
    ("ipgen", "patch", "input changed"),
    ("ipgen", "external", "generator input changed"),
])
def test_input_drift_cannot_produce_success(generator_fixture, monkeypatch, phase, location, message):
    output, roots, dts, runner = generator_fixture
    original = runner.run

    def drifting_run(self, argv, cwd, label, timeout=300):
        result = original(self, argv, cwd, label, timeout=timeout)
        if label == phase:
            if location == "patch":
                path = output / "inputs/patches/plic-contract.patch"
            elif location == "external":
                path = Path(json.loads(roots.read_text())["opentitan_peripherals"]) / "util/ipgen.py"
            else:
                path = output / location / "opentitan_peripherals/util/ipgen.py"
            path.write_text("unexpected input drift\n")
        return result

    monkeypatch.setattr(runner, "run", drifting_run)
    with pytest.raises(ValueError, match=message):
        prepare.prepare(output, roots, dts, fix_contract=True)
    assert not (output / "manifest.json").exists()
    assert json.loads((output / "failure.json").read_text())["status"] == "FAILED"


def test_patch_check_failure_stops_before_generation(generator_fixture, monkeypatch):
    output, roots, dts, runner = generator_fixture
    original = runner.run

    def failed_check(self, argv, cwd, label, timeout=300):
        if label == "contract-patch-check":
            raise ValueError("fixture patch check failed")
        return original(self, argv, cwd, label, timeout=timeout)

    monkeypatch.setattr(runner, "run", failed_check)
    with pytest.raises(ValueError, match="patch check failed"):
        prepare.prepare(output, roots, dts, fix_contract=True)
    assert not (output / "rv_plic").exists()
    assert (output / "work/opentitan_peripherals" / prepare.CONTRACT_TEMPLATE).read_text() == TEMPLATE_CONTEXTS


@pytest.mark.parametrize("flag", [[], ["--fix-contract"]])
def test_cli_contract_fix_is_opt_in(monkeypatch, capsys, flag):
    calls = []

    def stub_prepare(output, roots_path, template, *, fix_contract=False):
        calls.append(fix_contract)
        return {"status": "GENERATED_NOT_VALIDATED"}

    monkeypatch.setattr(prepare, "prepare", stub_prepare)
    assert prepare.main(["--output", "unused", "--roots", "unused", *flag]) == 0
    assert calls == [bool(flag)]
    assert json.loads(capsys.readouterr().out)["status"] == "GENERATED_NOT_VALIDATED"
