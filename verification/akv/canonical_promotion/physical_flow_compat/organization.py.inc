# Counts are physical instances, not area or measured timing evidence.
AKV_SRAM_ORGANIZATIONS = {
    "legacy_v1_v2_64x256": (20, 4, 16, 0, 327680),
    "split_v1_96x256_v2_128x256": (10, 2, 8, 0, 311296),
    "unified_q64x256_kv128x256": (9, 0, 8, 1, 278528),
}
LEGACY_AKV_SRAM_ORGANIZATIONS = {
    (20, 4, 16): "legacy_v1_v2_64x256",
    (10, 2, 8): "split_v1_96x256_v2_128x256",
}


def validate_sram_organization(values, capacity_key):
    def integer(key):
        value = values.get(key)
        if type(value) is int and value >= 0:
            return value
        if type(value) is str and re.fullmatch(r"0|[1-9][0-9]*", value):
            return int(value)
        raise CollectionError(f"invalid SRAM organization integer: {key}")

    counts = tuple(integer(key) for key in (
        "akv_sram_macro_count", "akv_v1_sram_macro_count", "akv_v2_sram_macro_count"))
    capacity = integer(capacity_key)
    label_present = "akv_sram_organization" in values
    q_present = "akv_q_sram_macro_count" in values
    if label_present != q_present:
        raise CollectionError("SRAM organization and independent Q count must appear together")
    if label_present:
        label = values["akv_sram_organization"]
        if type(label) is not str or label not in AKV_SRAM_ORGANIZATIONS:
            raise CollectionError("unknown SRAM organization discriminator")
        q_count = integer("akv_q_sram_macro_count")
    else:
        # Only the two exact historical organizations may omit new metadata.
        label = LEGACY_AKV_SRAM_ORGANIZATIONS.get(counts)
        if label is None:
            raise CollectionError("SRAM organization requires explicit discriminator and Q count")
        q_count = 0
    if (*counts, q_count, capacity) != AKV_SRAM_ORGANIZATIONS[label]:
        raise CollectionError("SRAM organization counts/capacity disagree with discriminator")
    return label, q_count
