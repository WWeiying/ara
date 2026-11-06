"""Resolve only the two supported legacy payload-SRAM wrapper hierarchies."""


def resolve_payload_ram(root, row_path):
    candidates = (row_path + ".i_payload", row_path + ".gen_storage.i_payload")
    found = []
    for path in candidates:
        symbol = root.lookupName(path)
        if symbol is not None and not getattr(symbol, "isUninstantiated", False):
            found.append((path, symbol))
    if len(found) != 1:
        raise RuntimeError(f"Expected exactly one payload SRAM at {row_path}, found {len(found)}")
    path, symbol = found[0]
    if getattr(getattr(symbol, "definition", None), "name", None) != "qbs_payload_sram":
        raise RuntimeError(f"Unexpected payload SRAM wrapper type: {path}")
    return path
