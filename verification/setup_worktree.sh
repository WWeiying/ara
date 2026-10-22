#!/usr/bin/env bash
set -euo pipefail

# Clone locked dependency commits and apply only the reviewed, hash-pinned
# patch bundles in verification/patches. Never import arbitrary source edits
# or share writable dependency RTL with another worktree.
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
SOURCE_ROOT=${SOURCE_ROOT:-"$ROOT/../ara_dsa"}
SOURCE_ROOT=$(cd "$SOURCE_ROOT" && pwd)
ALLOW_DOWNLOAD=${ALLOW_DOWNLOAD:-1}

link_path() {
    local destination=$1
    local source=$2
    if [[ -e "$destination" || -L "$destination" ]]; then
        if [[ -L "$destination" && "$(readlink -f "$destination")" == "$(readlink -f "$source")" ]]; then
            return
        fi
        printf 'error: destination exists and is not the requested link: %s\n' "$destination" >&2
        exit 1
    fi
    [[ -e "$source" || -L "$source" ]] || {
        printf 'error: missing source: %s\n' "$source" >&2
        exit 1
    }
    mkdir -p "$(dirname "$destination")"
    ln -s "$source" "$destination"
}

snapshot_git_repo() {
    local destination=$1
    local source=$2
    local revision=$3
    if [[ -L "$destination" ]]; then
        printf 'error: refusing to replace linked tool checkout: %s\n' "$destination" >&2
        exit 1
    elif [[ -e "$destination" ]]; then
        [[ -d "$destination/.git" ]] || {
            printf 'error: dependency destination is not a Git checkout: %s\n' "$destination" >&2
            exit 1
        }
        local actual
        actual=$(git -C "$destination" rev-parse HEAD)
        local status
        status=$(git -C "$destination" status --porcelain=v1 --ignore-submodules=none)
        if [[ "$actual" == "$revision" && -z "$status" ]]; then
            return
        fi
        printf 'error: refusing to replace non-clean dependency checkout: %s\n' "$destination" >&2
        exit 1
    fi
    mkdir -p "$(dirname "$destination")"
    git clone --no-local --no-hardlinks --no-checkout "$source" "$destination" >/dev/null
    git -C "$destination" checkout --detach "$revision" >/dev/null
}

install_locked_bender() {
    local destination=$1
    local expected=$2
    if [[ -x "$destination" ]]; then
        local actual
        actual=$("$destination" --version 2>/dev/null | awk '{print $NF}')
        [[ "$actual" == "$expected" ]] && return
    elif [[ -e "$destination" && ! -f "$destination" && ! -L "$destination" ]]; then
        printf 'error: Bender destination is not a regular file: %s\n' "$destination" >&2
        exit 1
    fi
    [[ "$ALLOW_DOWNLOAD" == 1 ]] || {
        printf 'error: Bender %s is required and ALLOW_DOWNLOAD=0\n' "$expected" >&2
        exit 1
    }
    local temp
    temp=$(mktemp -d)
    python3 - "$expected" "$temp/bender" <<'PY'
import io
import sys
import tarfile
import urllib.request

version, destination = sys.argv[1:]
url = (
    "https://github.com/pulp-platform/bender/releases/download/v"
    f"{version}/bender-{version}-x86_64-linux-gnu.tar.gz"
)
with urllib.request.urlopen(url, timeout=60) as response:
    archive = tarfile.open(fileobj=io.BytesIO(response.read()), mode="r:gz")
    member = archive.getmember("bender")
    with archive.extractfile(member) as source, open(destination, "wb") as target:
        target.write(source.read())
PY
    [[ -x "$temp/bender" || -f "$temp/bender" ]] || {
        printf 'error: failed to install Bender %s\n' "$expected" >&2
        exit 1
    }
    chmod 0755 "$temp/bender"
    [[ "$("$temp/bender" --version | awk '{print $NF}')" == "$expected" ]] || {
        printf 'error: installed Bender version does not match %s\n' "$expected" >&2
        exit 1
    }
    mkdir -p "$(dirname "$destination")"
    mv -f "$temp/bender" "$destination"
    rmdir "$temp"
}

printf 'worktree: %s\nsource:   %s\n' "$ROOT" "$SOURCE_ROOT"
link_path "$ROOT/install" "$SOURCE_ROOT/install"
link_path "$ROOT/apps/third-party" "$SOURCE_ROOT/apps/third-party"
install_locked_bender "$ROOT/hardware/bender" "$(sed -n 's/^BENDER_VERSION := //p' "$ROOT/hardware/Makefile")"
TOOL_REVISION=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["tools"]["riscv-dv-rvv1"]["revision"])' "$ROOT/verification/toolchain.lock.json")
snapshot_git_repo "$ROOT/verification/tools/riscv-dv-rvv1" "$SOURCE_ROOT/verification/tools/riscv-dv-rvv1" "$TOOL_REVISION"

for dependency in apb axi common_cells common_verification cva6 fpnew \
                  fpu_div_sqrt_mvp tech_cells_generic; do
    PYTHONPATH="$ROOT/verification" python3 -m ara_verify.dependency_patches \
        --root "$ROOT" --package "$dependency" --source "$SOURCE_ROOT/hardware/deps/$dependency"
done

PYTHONPATH="$ROOT/verification" python3 - "$ROOT" "$SOURCE_ROOT" <<'PY'
import json
import subprocess
import sys
from pathlib import Path
from ara_verify.dependency_patches import load_registry

root, source = map(Path, sys.argv[1:])

def command(cwd, *args):
    result = subprocess.run(["git", *args], cwd=cwd, text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                            check=False)
    return result.stdout.strip()

def target(path):
    return str(path.resolve()) if path.exists() else None

payload = {
    "worktree": str(root),
    "source_worktree": str(source),
    "source_commit": command(source, "rev-parse", "HEAD"),
    "worktree_commit": command(root, "rev-parse", "HEAD"),
    "links": {
        "install": target(root / "install"),
        "apps_third_party": target(root / "apps/third-party"),
        "bender": target(root / "hardware/bender"),
    },
    "snapshots": {
        "riscv_dv_rvv1": {
            "source": str(source / "verification/tools/riscv-dv-rvv1"),
            "commit": command(root / "verification/tools/riscv-dv-rvv1", "rev-parse", "HEAD"),
        },
        "hardware_deps": {
            name: {
                "source": str(source / "hardware/deps" / name),
                "commit": command(root / "hardware/deps" / name, "rev-parse", "HEAD"),
            }
            for name in ("apb", "axi", "common_cells", "common_verification",
                         "cva6", "fpnew", "fpu_div_sqrt_mvp", "tech_cells_generic")
        },
    },
    "local_patches": load_registry(root),
    "required_cva6_submodules": {
        relative: command(root / "hardware/deps/cva6" / relative, "rev-parse", "HEAD")
        for relative in ("core/cache_subsystem/hpdcache", "core/cvfpu")
    },
}
out = root / "verification/worktree_inputs.json"
out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
print(f"wrote {out}")
PY

printf 'environment links ready; run:\n'
printf '  PYTHONPATH=verification python3 verification/verify.py doctor\n'
