"""Compose test-only legacy ports without reading any canonical engine header."""
import hashlib
import json
from pathlib import Path

import compose_standalone as original

HERE = Path(__file__).resolve().parent
CONTRACTS = HERE / "standalone_port_contracts"


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def contract(kind, directory=CONTRACTS):
    if kind not in ("qbs", "akv"):
        raise ValueError("Known engine required")
    manifest = json.loads((directory / "manifest.json").read_text())
    if manifest.get("schema_version") != 1 or set(manifest.get("headers", {})) != {"qbs", "akv"}:
        raise ValueError("Unknown archived port contract")
    entry = manifest["headers"][kind]
    if entry["file"] != kind + "_engine_legacy_header.svh":
        raise ValueError("Unexpected archived header path")
    path = directory / entry["file"]
    if digest(path) != entry["sha256"] or digest(Path(original.__file__)) != manifest["composer_sha256"]:
        raise ValueError("Frozen header/composer identity changed")
    header = path.read_text()
    if not header.endswith("\n  );\n") or "endmodule" in header or "reader_req_t" in header:
        raise ValueError("Need header-only original interface")
    return entry, header


def compose(kind, directory=CONTRACTS):
    _, header = contract(kind, directory)
    return original.compose(header, kind)


def adapt_tb(text, kind):
    entry, _ = contract(kind)
    if hashlib.sha256(text.encode()).hexdigest() != entry["tb_sha256"]:
        raise ValueError("TB changed from the reviewed original suite")
    return original.adapt_tb(text, kind)
