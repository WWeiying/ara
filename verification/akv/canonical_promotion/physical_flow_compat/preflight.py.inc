UNIFIED_AKV_ORGANIZATION = "unified_q64x256_kv128x256"
SPLIT_AKV_ORGANIZATION = "split_v1_96x256_v2_128x256"
UNIFIED_AKV_SOURCES = (
    "hardware/src/vlsu/qbs_akv_shared_reader.sv",
    "hardware/src/vlsu/akv/akv_legacy_repacker.sv",
    "hardware/src/vlsu/akv/akv_q_store.sv",
    "hardware/src/vlsu/akv/akv_unified_context.sv",
)
AKV_Q_SRAM_BLACKBOX = "backend/blackbox/ts1n28hpcpuhdsvtb64x256m1swbso_170a_tt0p9v25c.v"
DEFAULT_AKV_Q_SRAM_DB = Path(
    "/home/wangwy/ara/backend/library/mem/ts1n28hpcpuhdsvtb64x256m1swbso_170a/DB/"
    "ts1n28hpcpuhdsvtb64x256m1swbso_170a_tt0p9v25c.db"
)


def check_storage_selection(options, sources):
    selected = options.akv_storage_organization
    if selected not in (SPLIT_AKV_ORGANIZATION, UNIFIED_AKV_ORGANIZATION):
        raise PreflightError("unknown AKV storage organization")
    unified = selected == UNIFIED_AKV_ORGANIZATION
    if not (options.require_akv or options.require_akv_v2) and not unified:
        # Bender may list unused AKV modules during a QBS-only preflight.
        return False
    has_unified = _has_source(sources, UNIFIED_AKV_SOURCES[-1])
    if unified != has_unified:
        raise PreflightError("AKV storage organization does not match source graph; select explicitly")
    if unified:
        if not options.require_akv_v2:
            raise PreflightError("unified storage requires --require-akv-v2")
        _require_sources(sources, UNIFIED_AKV_SOURCES)
        for before in (*UNIFIED_AKV_SOURCES[1:3], AKV_V2_SOURCES[0]):
            _check_order(sources, before, UNIFIED_AKV_SOURCES[-1])
        _check_order(sources, UNIFIED_AKV_SOURCES[-1], "hardware/src/vlsu/akv/akv_engine.sv")
        _check_order(sources, "hardware/src/vlsu/qbs/qbs_read_engine.sv", UNIFIED_AKV_SOURCES[0])
        _check_order(sources, UNIFIED_AKV_SOURCES[0], "hardware/src/vlsu/vlsu.sv")
    return unified
