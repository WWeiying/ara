"""Identity of the actual program and compiled design used by a simulation."""

import hashlib
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def simulation_image(simv: Path) -> dict[str, str]:
    # VCS partitions the compiled RTL into generated shared libraries. Hashing
    # only the launcher would miss changes to most of the executable design.
    libraries = Path(str(simv) + ".daidir")
    files = [simv, *sorted(libraries.rglob("*.so"))]
    return {str(path): sha256(path) for path in files}


def check_inputs(inputs: dict, expected_elf: Path) -> list[str]:
    issues = []
    try:
        binary = inputs["binary"]
        if binary["path"] != str(expected_elf) or sha256(expected_elf) != binary["sha256"]:
            issues.append("private ELF changed or has the wrong path")
    except (OSError, KeyError, TypeError, ValueError) as error:
        issues.append(f"private ELF identity unavailable: {error}")
    try:
        image = inputs["simv"]
        if simulation_image(Path(image["path"])) != image["image_sha256"]:
            issues.append("simulator executable or generated RTL libraries changed")
    except (OSError, KeyError, TypeError, ValueError) as error:
        issues.append(f"simulator image identity unavailable: {error}")
    if "spike" in inputs:
        try:
            reference = inputs["spike"]
            if sha256(Path(reference["path"])) != reference["sha256"]:
                issues.append("reference Spike executable changed")
        except (OSError, KeyError, TypeError, ValueError) as error:
            issues.append(f"reference Spike identity unavailable: {error}")
    return issues
