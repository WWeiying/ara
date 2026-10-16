"""Source identity gate for the imported signoff RTL, not simulation signoff."""
from pathlib import Path
import subprocess

from ara_verify.dependency_patches import load_registry, patch_state


ROOT = Path(__file__).resolve().parents[2]
REVISION = "5ee02215edd65967040c837e786b7e1f668fcc36"


def frozen(path):
    return subprocess.check_output(["git", "show", REVISION + ":" + path], cwd=ROOT)


def test_main_rtl_exactly_matches_frozen_signoff():
    files = subprocess.check_output(
        ["git", "ls-tree", "-r", "--name-only", REVISION,
         "hardware/src", "hardware/include"], cwd=ROOT, text=True).splitlines()
    expected = {name for name in files if Path(name).suffix in (".sv", ".svh")}
    actual = {str(path.relative_to(ROOT))
              for folder in ("hardware/src", "hardware/include")
              for path in (ROOT / folder).rglob("*")
              if path.is_file() and path.suffix in (".sv", ".svh")}
    assert actual == expected
    for name in sorted(expected):
        assert (ROOT / name).read_bytes() == frozen(name), name


def test_build_lists_and_lock_match_frozen_signoff():
    for name in ("Bender.yml", "Bender.lock"):
        assert (ROOT / name).read_bytes() == frozen(name), name


def test_reviewed_dependency_patches_match_and_are_applied():
    registry = "verification/patches/dependencies.json"
    assert (ROOT / registry).read_bytes() == frozen(registry)
    for package, spec in load_registry(ROOT).items():
        name = "verification/patches/" + spec["patch"]
        assert (ROOT / name).read_bytes() == frozen(name), name
        assert patch_state(ROOT, package, ROOT / "hardware/deps" / package,
                           spec["revision"]) == "applied"
