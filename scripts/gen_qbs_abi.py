#!/usr/bin/env python3
"""Generate software and RTL QBS ABI definitions from one JSON source."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SPEC_PATH = ROOT / "config/qbs_abi.json"
C_PATHS = [
    ROOT / "apps/common/qbs_abi.h",
    ROOT / "software/qbs/include/qbs/qbs_abi.h",
]
SV_PATH = ROOT / "hardware/include/qbs_pkg.sv"

SCALE_FORMATS = {"FP16": 1, "FP32": 2}
CORRECTION_MODES = {"NONE": 0, "AFFINE_MIN": 1}
ROUNDING_MODES = {"RNE": 0}


def load_spec() -> dict:
    with SPEC_PATH.open("r", encoding="utf-8") as source:
        return json.load(source)


def sv_token(name: str) -> str:
    parts = name.split("_")
    token = parts[0][:1].upper() + parts[0][1:].lower()
    for part in parts[1:]:
        if part.isdigit():
            token += "_" + part
        else:
            token += part[:1].upper() + part[1:].lower()
    return token


def profile_const(domain: str, name: str) -> str:
    return f"QBS_{domain}_PROFILE_{name}"


def validate_spec(spec: dict) -> None:
    limits = spec["limits"]
    numerical_contract = spec["numerical_contract"]
    if numerical_contract.get("rounding_mode") not in ROUNDING_MODES:
        raise ValueError("numerical_contract.rounding_mode must be RNE")
    if numerical_contract.get("uses_dynamic_frm") is not False:
        raise ValueError(
            "QBS numerical-contract v1 must not depend on dynamic frm")
    if not 1 <= limits["max_m"] <= 4:
        raise ValueError("limits.max_m must fit the 2-bit M-minus-one field")
    if not 1 <= limits["max_n"] <= 32:
        raise ValueError("limits.max_n must fit the 5-bit N-minus-one field")
    if not 1 <= limits["max_k_blocks"] <= 256:
        raise ValueError(
            "limits.max_k_blocks must fit the 8-bit K-block-minus-one field")

    for domain in ("weight", "activation"):
        profiles = spec[f"{domain}_profiles"]
        ids = set()
        for name, profile in profiles.items():
            if name != name.upper():
                raise ValueError(f"{domain} profile name must be uppercase: {name}")
            profile_id = profile["id"]
            if not 1 <= profile_id <= 15:
                raise ValueError(
                    f"{domain} profile {name} id must fit the 4-bit field")
            if profile_id in ids:
                raise ValueError(f"duplicate {domain} profile id {profile_id}")
            ids.add(profile_id)
            if not 1 <= profile["block_bytes"] <= 0xffff:
                raise ValueError(f"invalid block_bytes for {domain} profile {name}")
            if not 1 <= profile["block_elements"] <= 0xffff:
                raise ValueError(
                    f"invalid block_elements for {domain} profile {name}")

    for name, profile in spec["weight_profiles"].items():
        if profile.get("scale_format") not in SCALE_FORMATS:
            raise ValueError(f"invalid scale_format for weight profile {name}")
        if profile.get("correction_mode") not in CORRECTION_MODES:
            raise ValueError(
                f"invalid correction_mode for weight profile {name}")
        subgroup_count = profile.get("subgroup_count", 0)
        subgroup_elements = profile.get("subgroup_elements", 0)
        if subgroup_count < 1 or subgroup_elements < 1 or (
                subgroup_count * subgroup_elements !=
                profile["block_elements"]):
            raise ValueError(
                f"weight profile {name} subgroups do not cover its block")

    for name, profile in spec["activation_profiles"].items():
        if profile.get("scale_format") not in SCALE_FORMATS:
            raise ValueError(
                f"invalid scale_format for activation profile {name}")
        scale_bytes = profile.get("scale_bytes", 0)
        quant_bytes = profile.get("quant_bytes", 0)
        aux_count = profile.get("aux_count", 0)
        aux_element_bytes = profile.get("aux_element_bytes", 0)
        if scale_bytes < 1 or quant_bytes < 1:
            raise ValueError(
                f"activation profile {name} has invalid payload geometry")
        if aux_count == 0 and aux_element_bytes != 0:
            raise ValueError(
                f"activation profile {name} has bytes for an empty aux array")
        if aux_count != 0 and aux_element_bytes < 1:
            raise ValueError(
                f"activation profile {name} has an invalid aux element size")
        if scale_bytes + quant_bytes + aux_count * aux_element_bytes != (
                profile["block_bytes"]):
            raise ValueError(
                f"activation profile {name} payload does not match block_bytes")

    activation_profiles = spec["activation_profiles"]
    for name, profile in spec["weight_profiles"].items():
        compatible = profile.get("activation_profiles", [])
        if not compatible:
            raise ValueError(f"weight profile {name} has no activation profile")
        for activation_name in compatible:
            if activation_name not in activation_profiles:
                raise ValueError(
                    f"weight profile {name} references unknown activation "
                    f"profile {activation_name}")
            if (profile["block_elements"] !=
                    activation_profiles[activation_name]["block_elements"]):
                raise ValueError(
                    f"weight profile {name} and activation profile "
                    f"{activation_name} cover different element counts")

    for layout_domain in ("weight_layouts", "activation_layouts"):
        ids = list(spec[layout_domain].values())
        if len(ids) != len(set(ids)) or any(not 1 <= value <= 15
                                           for value in ids):
            raise ValueError(f"{layout_domain} ids must be unique and in [1,15]")


def c_profile_defines(spec: dict) -> str:
    lines = [
        f"#define QBS_MAX_WEIGHT_BLOCK_BYTES "
        f"{max(p['block_bytes'] for p in spec['weight_profiles'].values())}u",
        f"#define QBS_MAX_ACTIVATION_BLOCK_BYTES "
        f"{max(p['block_bytes'] for p in spec['activation_profiles'].values())}u",
    ]
    for name, profile in spec["weight_profiles"].items():
        prefix = f"QBS_{name}"
        lines.extend([
            f"#define {prefix}_BLOCK_BYTES {profile['block_bytes']}u",
            f"#define {prefix}_BLOCK_ELEMENTS {profile['block_elements']}u",
            f"#define {prefix}_SUBGROUP_COUNT "
            f"{profile.get('subgroup_count', 0)}u",
            f"#define {prefix}_SUBGROUP_ELEMENTS "
            f"{profile.get('subgroup_elements', 0)}u",
            f"#define {prefix}_SCALE_FORMAT "
            f"QBS_SCALE_{profile['scale_format']}",
            f"#define {prefix}_CORRECTION_MODE "
            f"QBS_CORRECTION_{profile['correction_mode']}",
        ])
    for name, profile in spec["activation_profiles"].items():
        prefix = f"QBS_{name}"
        lines.extend([
            f"#define {prefix}_BLOCK_BYTES {profile['block_bytes']}u",
            f"#define {prefix}_BLOCK_ELEMENTS {profile['block_elements']}u",
            f"#define {prefix}_SCALE_FORMAT "
            f"QBS_SCALE_{profile['scale_format']}",
            f"#define {prefix}_SCALE_BYTES {profile['scale_bytes']}u",
            f"#define {prefix}_QUANT_BYTES {profile['quant_bytes']}u",
            f"#define {prefix}_AUX_COUNT {profile['aux_count']}u",
            f"#define {prefix}_AUX_ELEMENT_BYTES "
            f"{profile['aux_element_bytes']}u",
        ])
        if "bsums_count" in profile:
            lines.append(
                f"#define {prefix}_BSUMS_COUNT {profile['bsums_count']}u")
    return "\n".join(lines)


def c_enum(spec: dict, domain: str) -> str:
    entries = [f"  QBS_{domain}_PROFILE_INVALID = 0,"]
    entries.extend(
        f"  {profile_const(domain, name)} = {profile['id']},"
        for name, profile in spec[f"{domain.lower()}_profiles"].items())
    return "\n".join(entries)


def c_layout_enum(spec: dict, domain: str) -> str:
    entries = [f"  QBS_{domain}_LAYOUT_INVALID = 0,"]
    entries.extend(
        f"  QBS_{domain}_LAYOUT_{name} = {layout_id},"
        for name, layout_id in spec[f"{domain.lower()}_layouts"].items())
    return "\n".join(entries)


def c_switch_value(spec: dict, domain: str, field: str) -> str:
    lines = ["  switch (profile) {"]
    for name, profile in spec[f"{domain}_profiles"].items():
        value = profile.get(field, 0)
        lines.append(
            f"    case {profile_const(domain.upper(), name)}: return {value}u;")
    lines.extend(["    default: return 0u;", "  }"])
    return "\n".join(lines)


def c_switch_symbol(spec: dict, domain: str, field: str,
                    symbol_prefix: str, default_symbol: str) -> str:
    lines = ["  switch (profile) {"]
    for name, profile in spec[f"{domain}_profiles"].items():
        lines.append(
            f"    case {profile_const(domain.upper(), name)}: "
            f"return {symbol_prefix}{profile[field]};")
    lines.extend([f"    default: return {default_symbol};", "  }"])
    return "\n".join(lines)


def c_switch_name(spec: dict, domain: str) -> str:
    lines = ["  switch (profile) {"]
    for name in spec[f"{domain}_profiles"]:
        lines.append(
            f'    case {profile_const(domain.upper(), name)}: return "{name}";')
    lines.extend(['    default: return "invalid";', "  }"])
    return "\n".join(lines)


def c_compatibility_switch(spec: dict) -> str:
    lines = ["  switch (weight_profile) {"]
    for name, profile in spec["weight_profiles"].items():
        conditions = " || ".join(
            f"activation_profile == "
            f"{profile_const('ACTIVATION', activation_name)}"
            for activation_name in profile["activation_profiles"])
        lines.extend([
            f"    case {profile_const('WEIGHT', name)}:",
            f"      return {conditions};",
        ])
    lines.extend(["    default: return 0;", "  }"])
    return "\n".join(lines)


def c_default_activation_switch(spec: dict) -> str:
    lines = ["  switch (weight_profile) {"]
    for name, profile in spec["weight_profiles"].items():
        activation_name = profile["activation_profiles"][0]
        lines.append(
            f"    case {profile_const('WEIGHT', name)}: return "
            f"{profile_const('ACTIVATION', activation_name)};")
    lines.extend([
        "    default: return QBS_ACTIVATION_PROFILE_INVALID;",
        "  }",
    ])
    return "\n".join(lines)


def c_capability_cases(spec: dict) -> str:
    lines = []
    for name, profile in spec["weight_profiles"].items():
        mask = " | ".join(
            f"(UINT64_C(1) << {profile_const('ACTIVATION', activation_name)})"
            for activation_name in profile["activation_profiles"])
        lines.extend([
            f"  if (index == 0x{0x10 + profile['id']:02x}u)",
            f"    return {mask};",
            f"  if (index == 0x{0x20 + profile['id']:02x}u)",
            f"    return (uint64_t)QBS_{name}_BLOCK_BYTES |",
            f"           ((uint64_t)QBS_{name}_BLOCK_ELEMENTS << 16) |",
            f"           ((uint64_t)QBS_{name}_SUBGROUP_COUNT << 32) |",
            f"           ((uint64_t)QBS_{name}_SUBGROUP_ELEMENTS << 40) |",
            f"           ((uint64_t)QBS_{name}_SCALE_FORMAT << 48) |",
            f"           ((uint64_t)QBS_{name}_CORRECTION_MODE << 56);",
        ])
    for name, profile in spec["activation_profiles"].items():
        lines.extend([
            f"  if (index == 0x{0x30 + profile['id']:02x}u)",
            f"    return (uint64_t)QBS_{name}_BLOCK_BYTES |",
            f"           ((uint64_t)QBS_{name}_BLOCK_ELEMENTS << 16) |",
            f"           ((uint64_t)QBS_{name}_AUX_COUNT << 32) |",
            f"           ((uint64_t)QBS_{name}_SCALE_BYTES << 40) |",
            f"           ((uint64_t)QBS_{name}_AUX_ELEMENT_BYTES << 48) |",
            f"           ((uint64_t)QBS_{name}_SCALE_FORMAT << 56);",
        ])
    return "\n".join(lines)


def c_header(spec: dict) -> str:
    desc = spec["descriptor"]
    insn = spec["instruction"]
    limits = spec["limits"]
    numerical_contract = spec["numerical_contract"]
    weight_layout_mask = " |\n        ".join(
        f"(UINT64_C(1) << QBS_WEIGHT_LAYOUT_{name})"
        for name in spec["weight_layouts"])
    activation_layout_mask = " |\n        ".join(
        f"(UINT64_C(1) << QBS_ACTIVATION_LAYOUT_{name})"
        for name in spec["activation_layouts"])
    return f"""/* Generated by scripts/gen_qbs_abi.py. Do not edit. */
#ifndef ARA_QBS_ABI_H_
#define ARA_QBS_ABI_H_

#include <stddef.h>
#include <stdint.h>

#define QBS_EXTENSION_NAME \"{spec['extension_name']}\"
#define QBS_ARCH_VERSION {spec['architecture_version']}u
#define QBS_NUMERICAL_CONTRACT_VERSION {spec['numerical_contract_version']}u
#define QBS_ROUNDING_MODE_RNE {ROUNDING_MODES['RNE']}u
#define QBS_NUMERICAL_ROUNDING_MODE QBS_ROUNDING_MODE_{numerical_contract['rounding_mode']}
#define QBS_NUMERICAL_USES_DYNAMIC_FRM {int(numerical_contract['uses_dynamic_frm'])}u
#define QBS_DESCRIPTOR_VERSION {desc['version']}u
#define QBS_DESCRIPTOR_BYTES {desc['bytes']}u
#define QBS_DESCRIPTOR_ALIGNMENT_LOG2 {desc['alignment_log2']}u

#define QBS_OPCODE_CUSTOM2 0x{insn['opcode']:02x}u
#define QBS_QBEXEC_FUNCT3 {insn['qbexec_funct3']}u
#define QBS_QBINFO_FUNCT3 {insn['qbinfo_funct3']}u

#define QBS_MAX_M {limits['max_m']}u
#define QBS_MAX_N {limits['max_n']}u
#define QBS_MAX_K_BLOCKS {limits['max_k_blocks']}u
/* Compatibility alias for numerical-contract v1 K-quant profiles. */
#define QBS_BLOCK_ELEMENTS {limits['block_elements']}u
#define QBS_WEIGHT_BASE_ALIGNMENT_LOG2 {limits['weight_base_alignment_log2']}u
#define QBS_ACTIVATION_BASE_ALIGNMENT_LOG2 {limits['activation_base_alignment_log2']}u

typedef enum {{
  QBS_SCALE_INVALID = 0,
  QBS_SCALE_FP16 = {SCALE_FORMATS['FP16']},
  QBS_SCALE_FP32 = {SCALE_FORMATS['FP32']},
}} qbs_scale_format_t;

typedef enum {{
  QBS_CORRECTION_NONE = {CORRECTION_MODES['NONE']},
  QBS_CORRECTION_AFFINE_MIN = {CORRECTION_MODES['AFFINE_MIN']},
}} qbs_correction_mode_t;

{c_profile_defines(spec)}

typedef enum {{
{c_enum(spec, 'WEIGHT')}
}} qbs_weight_profile_t;

typedef enum {{
{c_enum(spec, 'ACTIVATION')}
}} qbs_activation_profile_t;

typedef enum {{
{c_layout_enum(spec, 'WEIGHT')}
}} qbs_weight_layout_t;

typedef enum {{
{c_layout_enum(spec, 'ACTIVATION')}
}} qbs_activation_layout_t;

typedef struct __attribute__((aligned(16))) {{
  uint64_t header;
  uint64_t weight_base;
}} qbs_descriptor_v1_t;

typedef struct {{
  uint8_t descriptor_version;
  uint8_t weight_profile;
  uint8_t activation_profile;
  uint8_t weight_layout;
  uint8_t activation_layout;
  uint8_t n;
  uint16_t k_blocks;
}} qbs_descriptor_fields_t;

#if defined(__cplusplus)
static_assert(sizeof(qbs_descriptor_v1_t) == QBS_DESCRIPTOR_BYTES,
              "invalid QBS descriptor size");
#else
_Static_assert(sizeof(qbs_descriptor_v1_t) == QBS_DESCRIPTOR_BYTES,
               "invalid QBS descriptor size");
#endif

static inline const char *qbs_weight_profile_name(unsigned profile) {{
{c_switch_name(spec, 'weight')}
}}

static inline const char *qbs_activation_profile_name(unsigned profile) {{
{c_switch_name(spec, 'activation')}
}}

static inline unsigned qbs_weight_block_bytes(unsigned profile) {{
{c_switch_value(spec, 'weight', 'block_bytes')}
}}

static inline unsigned qbs_weight_block_elements(unsigned profile) {{
{c_switch_value(spec, 'weight', 'block_elements')}
}}

static inline unsigned qbs_weight_subgroup_count(unsigned profile) {{
{c_switch_value(spec, 'weight', 'subgroup_count')}
}}

static inline unsigned qbs_weight_subgroup_elements(unsigned profile) {{
{c_switch_value(spec, 'weight', 'subgroup_elements')}
}}

static inline qbs_scale_format_t qbs_weight_scale_format(unsigned profile) {{
{c_switch_symbol(spec, 'weight', 'scale_format', 'QBS_SCALE_', 'QBS_SCALE_INVALID')}
}}

static inline qbs_correction_mode_t qbs_weight_correction_mode(
    unsigned profile) {{
{c_switch_symbol(spec, 'weight', 'correction_mode', 'QBS_CORRECTION_', 'QBS_CORRECTION_NONE')}
}}

static inline unsigned qbs_activation_block_bytes(unsigned profile) {{
{c_switch_value(spec, 'activation', 'block_bytes')}
}}

static inline unsigned qbs_activation_block_elements(unsigned profile) {{
{c_switch_value(spec, 'activation', 'block_elements')}
}}

static inline qbs_scale_format_t qbs_activation_scale_format(
    unsigned profile) {{
{c_switch_symbol(spec, 'activation', 'scale_format', 'QBS_SCALE_', 'QBS_SCALE_INVALID')}
}}

static inline unsigned qbs_activation_scale_bytes(unsigned profile) {{
{c_switch_value(spec, 'activation', 'scale_bytes')}
}}

static inline unsigned qbs_activation_quant_bytes(unsigned profile) {{
{c_switch_value(spec, 'activation', 'quant_bytes')}
}}

static inline unsigned qbs_activation_aux_count(unsigned profile) {{
{c_switch_value(spec, 'activation', 'aux_count')}
}}

static inline unsigned qbs_activation_aux_element_bytes(unsigned profile) {{
{c_switch_value(spec, 'activation', 'aux_element_bytes')}
}}

static inline int qbs_profiles_compatible(unsigned weight_profile,
                                          unsigned activation_profile) {{
{c_compatibility_switch(spec)}
}}

static inline qbs_activation_profile_t qbs_default_activation_profile(
    unsigned weight_profile) {{
{c_default_activation_switch(spec)}
}}

static inline uint64_t qbs_pack_descriptor_header(
    const qbs_descriptor_fields_t *fields) {{
  return ((uint64_t)(fields->descriptor_version & 0x0fu) << 0) |
         ((uint64_t)(fields->weight_profile & 0x0fu) << 4) |
         ((uint64_t)(fields->activation_profile & 0x0fu) << 8) |
         ((uint64_t)(fields->weight_layout & 0x0fu) << 12) |
         ((uint64_t)(fields->activation_layout & 0x0fu) << 16) |
         ((uint64_t)((fields->n - 1u) & 0x1fu) << 20) |
         ((uint64_t)((fields->k_blocks - 1u) & 0xffu) << 25);
}}

static inline qbs_descriptor_fields_t qbs_unpack_descriptor_header(
    uint64_t header) {{
  qbs_descriptor_fields_t fields;
  fields.descriptor_version = (uint8_t)((header >> 0) & 0x0fu);
  fields.weight_profile = (uint8_t)((header >> 4) & 0x0fu);
  fields.activation_profile = (uint8_t)((header >> 8) & 0x0fu);
  fields.weight_layout = (uint8_t)((header >> 12) & 0x0fu);
  fields.activation_layout = (uint8_t)((header >> 16) & 0x0fu);
  fields.n = (uint8_t)(((header >> 20) & 0x1fu) + 1u);
  fields.k_blocks = (uint16_t)(((header >> 25) & 0xffu) + 1u);
  return fields;
}}

static inline uint64_t qbs_capability_word(unsigned index,
                                            unsigned vlen_bits) {{
  unsigned max_n = vlen_bits / 32u;
  if (max_n > QBS_MAX_N) max_n = QBS_MAX_N;
  if (index == 0x00u) {{
    if (max_n == 0) return 0;
    return ((uint64_t)QBS_ARCH_VERSION << 0) |
           ((uint64_t)QBS_DESCRIPTOR_VERSION << 8) |
           ((uint64_t)QBS_DESCRIPTOR_BYTES << 16) |
           ((uint64_t)(QBS_MAX_M - 1u) << 24) |
           ((uint64_t)(max_n - 1u) << 26) |
           ((uint64_t)(QBS_MAX_K_BLOCKS - 1u) << 31) |
           ((uint64_t)QBS_NUMERICAL_CONTRACT_VERSION << 39) |
           (UINT64_C(1) << 43) | (UINT64_C(1) << 44) |
           (UINT64_C(1) << 45) | (UINT64_C(1) << 46) |
           (UINT64_C(1) << 47);
  }}
  if (index == 0x01u) {{
    const uint64_t weight_layouts =
        {weight_layout_mask};
    const uint64_t activation_layouts =
        {activation_layout_mask};
    return weight_layouts | (activation_layouts << 16) |
           ((uint64_t)QBS_DESCRIPTOR_ALIGNMENT_LOG2 << 32) |
           ((uint64_t)QBS_WEIGHT_BASE_ALIGNMENT_LOG2 << 40) |
           ((uint64_t)QBS_ACTIVATION_BASE_ALIGNMENT_LOG2 << 48) |
           (UINT64_C(32) << 56);
  }}
{c_capability_cases(spec)}
  return 0;
}}

static inline uint32_t qbs_encode_qbexec(unsigned vd, unsigned rs1,
                                         unsigned rs2, unsigned m) {{
  const uint32_t funct7 = (uint32_t)((m - 1u) & 0x3u);
  return (funct7 << 25) | ((uint32_t)(rs2 & 0x1fu) << 20) |
         ((uint32_t)(rs1 & 0x1fu) << 15) | (QBS_QBEXEC_FUNCT3 << 12) |
         ((uint32_t)(vd & 0x1fu) << 7) | QBS_OPCODE_CUSTOM2;
}}

static inline uint32_t qbs_encode_qbinfo(unsigned rd, unsigned rs1) {{
  return ((uint32_t)(rs1 & 0x1fu) << 15) | (QBS_QBINFO_FUNCT3 << 12) |
         ((uint32_t)(rd & 0x1fu) << 7) | QBS_OPCODE_CUSTOM2;
}}

#endif  /* ARA_QBS_ABI_H_ */
"""


def sv_profile_constants(spec: dict) -> str:
    lines = [
        f"  localparam int unsigned QbsMaxWeightBlockBytes = "
        f"{max(p['block_bytes'] for p in spec['weight_profiles'].values())};",
        f"  localparam int unsigned QbsMaxActivationBlockBytes = "
        f"{max(p['block_bytes'] for p in spec['activation_profiles'].values())};",
    ]
    for name, profile in spec["weight_profiles"].items():
        prefix = f"Qbs{sv_token(name)}"
        lines.extend([
            f"  localparam int unsigned {prefix}BlockBytes = "
            f"{profile['block_bytes']};",
            f"  localparam int unsigned {prefix}BlockElements = "
            f"{profile['block_elements']};",
            f"  localparam int unsigned {prefix}SubgroupCount = "
            f"{profile.get('subgroup_count', 0)};",
            f"  localparam int unsigned {prefix}SubgroupElements = "
            f"{profile.get('subgroup_elements', 0)};",
            f"  localparam qbs_scale_format_e {prefix}ScaleFormat = "
            f"QBS_SCALE_{profile['scale_format']};",
            f"  localparam qbs_correction_mode_e {prefix}CorrectionMode = "
            f"QBS_CORRECTION_{profile['correction_mode']};",
        ])
    for name, profile in spec["activation_profiles"].items():
        prefix = f"Qbs{sv_token(name)}"
        lines.extend([
            f"  localparam int unsigned {prefix}BlockBytes = "
            f"{profile['block_bytes']};",
            f"  localparam int unsigned {prefix}BlockElements = "
            f"{profile['block_elements']};",
            f"  localparam qbs_scale_format_e {prefix}ScaleFormat = "
            f"QBS_SCALE_{profile['scale_format']};",
            f"  localparam int unsigned {prefix}ScaleBytes = "
            f"{profile['scale_bytes']};",
            f"  localparam int unsigned {prefix}QuantBytes = "
            f"{profile['quant_bytes']};",
            f"  localparam int unsigned {prefix}AuxCount = "
            f"{profile['aux_count']};",
            f"  localparam int unsigned {prefix}AuxElementBytes = "
            f"{profile['aux_element_bytes']};",
        ])
        if "bsums_count" in profile:
            lines.append(
                f"  localparam int unsigned {prefix}BsumsCount = "
                f"{profile['bsums_count']};")
    return "\n".join(lines)


def sv_enum(spec: dict, domain: str) -> str:
    entries = [f"    QBS_{domain}_PROFILE_INVALID = 4'd0"]
    entries.extend(
        f"    {profile_const(domain, name)} = 4'd{profile['id']}"
        for name, profile in spec[f"{domain.lower()}_profiles"].items())
    return ",\n".join(entries)


def sv_layout_enum(spec: dict, domain: str) -> str:
    entries = [f"    QBS_{domain}_LAYOUT_INVALID = 4'd0"]
    entries.extend(
        f"    QBS_{domain}_LAYOUT_{name} = 4'd{layout_id}"
        for name, layout_id in spec[f"{domain.lower()}_layouts"].items())
    return ",\n".join(entries)


def sv_switch_function(spec: dict, domain: str, field: str,
                       function_name: str, enum_type: str) -> str:
    lines = [
        f"  function automatic int unsigned {function_name}(",
        f"      input {enum_type} profile",
        "  );",
        f"    {function_name} = '0;",
        "    unique case (profile)",
    ]
    for name, profile in spec[f"{domain}_profiles"].items():
        lines.append(
            f"      {profile_const(domain.upper(), name)}: "
            f"{function_name} = {profile.get(field, 0)};")
    lines.extend([
        "      default: ;",
        "    endcase",
        f"  endfunction : {function_name}",
    ])
    return "\n".join(lines)


def sv_symbol_switch_function(spec: dict, domain: str, field: str,
                              function_name: str, enum_type: str,
                              return_type: str, symbol_prefix: str,
                              default_symbol: str) -> str:
    lines = [
        f"  function automatic {return_type} {function_name}(",
        f"      input {enum_type} profile",
        "  );",
        f"    {function_name} = {default_symbol};",
        "    unique case (profile)",
    ]
    for name, profile in spec[f"{domain}_profiles"].items():
        lines.append(
            f"      {profile_const(domain.upper(), name)}: "
            f"{function_name} = {symbol_prefix}{profile[field]};")
    lines.extend([
        "      default: ;",
        "    endcase",
        f"  endfunction : {function_name}",
    ])
    return "\n".join(lines)


def sv_compatibility_function(spec: dict) -> str:
    lines = [
        "  function automatic logic qbs_profiles_compatible(",
        "      input qbs_weight_profile_e weight_profile,",
        "      input qbs_activation_profile_e activation_profile",
        "  );",
        "    qbs_profiles_compatible = 1'b0;",
        "    unique case (weight_profile)",
    ]
    for name, profile in spec["weight_profiles"].items():
        values = ", ".join(
            profile_const("ACTIVATION", activation_name)
            for activation_name in profile["activation_profiles"])
        lines.append(
            f"      {profile_const('WEIGHT', name)}: "
            f"qbs_profiles_compatible = activation_profile inside {{{values}}};")
    lines.extend([
        "      default: ;",
        "    endcase",
        "  endfunction : qbs_profiles_compatible",
    ])
    return "\n".join(lines)


def sv_default_activation_function(spec: dict) -> str:
    lines = [
        "  function automatic qbs_activation_profile_e",
        "      qbs_default_activation_profile(",
        "          input qbs_weight_profile_e weight_profile",
        "      );",
        "    qbs_default_activation_profile = QBS_ACTIVATION_PROFILE_INVALID;",
        "    unique case (weight_profile)",
    ]
    for name, profile in spec["weight_profiles"].items():
        activation_name = profile["activation_profiles"][0]
        lines.append(
            f"      {profile_const('WEIGHT', name)}: "
            f"qbs_default_activation_profile = "
            f"{profile_const('ACTIVATION', activation_name)};")
    lines.extend([
        "      default: ;",
        "    endcase",
        "  endfunction : qbs_default_activation_profile",
    ])
    return "\n".join(lines)


def sv_capability_cases(spec: dict) -> str:
    lines = []
    for name, profile in spec["weight_profiles"].items():
        lines.append(f"      64'h{0x10 + profile['id']:02x}: begin")
        for activation_name in profile["activation_profiles"]:
            lines.append(
                f"        result[{profile_const('ACTIVATION', activation_name)}] = "
                "1'b1;")
        lines.extend([
            "      end",
            f"      64'h{0x20 + profile['id']:02x}: begin",
            f"        result[15:0]  = 16'(Qbs{sv_token(name)}BlockBytes);",
            f"        result[31:16] = 16'(Qbs{sv_token(name)}BlockElements);",
            f"        result[39:32] = 8'(Qbs{sv_token(name)}SubgroupCount);",
            f"        result[47:40] = 8'(Qbs{sv_token(name)}SubgroupElements);",
            f"        result[55:48] = 8'(Qbs{sv_token(name)}ScaleFormat);",
            f"        result[63:56] = 8'(Qbs{sv_token(name)}CorrectionMode);",
            "      end",
        ])
    for name, profile in spec["activation_profiles"].items():
        lines.extend([
            f"      64'h{0x30 + profile['id']:02x}: begin",
            f"        result[15:0]  = 16'(Qbs{sv_token(name)}BlockBytes);",
            f"        result[31:16] = 16'(Qbs{sv_token(name)}BlockElements);",
            f"        result[39:32] = 8'(Qbs{sv_token(name)}AuxCount);",
            f"        result[47:40] = 8'(Qbs{sv_token(name)}ScaleBytes);",
            f"        result[55:48] = 8'(Qbs{sv_token(name)}AuxElementBytes);",
            f"        result[63:56] = 8'(Qbs{sv_token(name)}ScaleFormat);",
            "      end",
        ])
    return "\n".join(lines)


def sv_package(spec: dict) -> str:
    desc = spec["descriptor"]
    insn = spec["instruction"]
    limits = spec["limits"]
    numerical_contract = spec["numerical_contract"]
    layout_lines = []
    for name in spec["weight_layouts"]:
        layout_lines.append(
            f"        result[QBS_WEIGHT_LAYOUT_{name}] = 1'b1;")
    for name in spec["activation_layouts"]:
        layout_lines.append(
            f"        result[16 + QBS_ACTIVATION_LAYOUT_{name}] = 1'b1;")
    return f"""// Generated by scripts/gen_qbs_abi.py. Do not edit.
package qbs_pkg;

`ifdef ARA_QBS_ENABLE
  localparam bit QbsEnable = 1'b1;
`else
  localparam bit QbsEnable = 1'b0;
`endif

  localparam int unsigned QbsArchitectureVersion = {spec['architecture_version']};
  localparam int unsigned QbsNumericalContractVersion = {spec['numerical_contract_version']};
  localparam logic [2:0] QbsRoundingModeRne = 3'd{ROUNDING_MODES['RNE']};
  localparam logic [2:0] QbsNumericalRoundingMode =
      QbsRoundingMode{sv_token(numerical_contract['rounding_mode'])};
  localparam bit QbsNumericalUsesDynamicFrm =
      1'b{int(numerical_contract['uses_dynamic_frm'])};
  localparam int unsigned QbsDescriptorVersion = {desc['version']};
  localparam int unsigned QbsDescriptorBytes = {desc['bytes']};
  localparam int unsigned QbsDescriptorAlignmentLog2 = {desc['alignment_log2']};

  localparam logic [6:0] QbsOpcodeCustom2 = 7'h{insn['opcode']:02x};
  localparam logic [2:0] QbsQbexecFunct3 = 3'd{insn['qbexec_funct3']};
  localparam logic [2:0] QbsQbinfoFunct3 = 3'd{insn['qbinfo_funct3']};

  localparam int unsigned QbsMaxM = {limits['max_m']};
  localparam int unsigned QbsMaxN = {limits['max_n']};
  localparam int unsigned QbsMaxKBlocks = {limits['max_k_blocks']};
  // Compatibility alias for numerical-contract v1 K-quant profiles.
  localparam int unsigned QbsBlockElements = {limits['block_elements']};
  localparam int unsigned QbsWeightBaseAlignmentLog2 = {limits['weight_base_alignment_log2']};
  localparam int unsigned QbsActivationBaseAlignmentLog2 = {limits['activation_base_alignment_log2']};

  typedef enum logic [1:0] {{
    QBS_SCALE_INVALID = 2'd0,
    QBS_SCALE_FP16 = 2'd{SCALE_FORMATS['FP16']},
    QBS_SCALE_FP32 = 2'd{SCALE_FORMATS['FP32']}
  }} qbs_scale_format_e;

  typedef enum logic [1:0] {{
    QBS_CORRECTION_NONE = 2'd{CORRECTION_MODES['NONE']},
    QBS_CORRECTION_AFFINE_MIN = 2'd{CORRECTION_MODES['AFFINE_MIN']}
  }} qbs_correction_mode_e;

{sv_profile_constants(spec)}

  typedef enum logic [3:0] {{
{sv_enum(spec, 'WEIGHT')}
  }} qbs_weight_profile_e;

  typedef enum logic [3:0] {{
{sv_enum(spec, 'ACTIVATION')}
  }} qbs_activation_profile_e;

  typedef enum logic [3:0] {{
{sv_layout_enum(spec, 'WEIGHT')}
  }} qbs_weight_layout_e;

  typedef enum logic [3:0] {{
{sv_layout_enum(spec, 'ACTIVATION')}
  }} qbs_activation_layout_e;

  // Internal validation result. These values are not software-visible ABI.
  typedef enum logic [4:0] {{
    QBS_VALIDATION_OK = 5'd0,
    QBS_VALIDATION_DESCRIPTOR_ALIGNMENT = 5'd1,
    QBS_VALIDATION_DESCRIPTOR_VERSION = 5'd2,
    QBS_VALIDATION_DESCRIPTOR_RESERVED = 5'd3,
    QBS_VALIDATION_WEIGHT_PROFILE = 5'd4,
    QBS_VALIDATION_ACTIVATION_PROFILE = 5'd5,
    QBS_VALIDATION_WEIGHT_LAYOUT = 5'd6,
    QBS_VALIDATION_ACTIVATION_LAYOUT = 5'd7,
    QBS_VALIDATION_M_RANGE = 5'd8,
    QBS_VALIDATION_N_RANGE = 5'd9,
    QBS_VALIDATION_K_RANGE = 5'd10,
    QBS_VALIDATION_VD_ALIGNMENT = 5'd11,
    QBS_VALIDATION_WEIGHT_ALIGNMENT = 5'd12,
    QBS_VALIDATION_ACTIVATION_ALIGNMENT = 5'd13,
    QBS_VALIDATION_WEIGHT_RANGE_OVERFLOW = 5'd14,
    QBS_VALIDATION_ACTIVATION_RANGE_OVERFLOW = 5'd15
  }} qbs_validation_error_e;

  // Internal read-path fault attribution; not software-visible ABI.
  typedef enum logic [2:0] {{
    QBS_READ_FAULT_NONE = 3'd0,
    QBS_READ_FAULT_REQUEST = 3'd1,
    QBS_READ_FAULT_MMU = 3'd2,
    QBS_READ_FAULT_AXI_RESPONSE = 3'd3,
    QBS_READ_FAULT_AXI_PROTOCOL = 3'd4,
    QBS_READ_FAULT_PMA = 3'd5
  }} qbs_read_fault_e;

  typedef struct packed {{
    logic [63:0] weight_base;
    logic [63:0] header;
  }} qbs_descriptor_v1_t;

  localparam int unsigned QbsDescVersionLsb = 0;
  localparam int unsigned QbsDescWeightProfileLsb = 4;
  localparam int unsigned QbsDescActivationProfileLsb = 8;
  localparam int unsigned QbsDescWeightLayoutLsb = 12;
  localparam int unsigned QbsDescActivationLayoutLsb = 16;
  localparam int unsigned QbsDescNMinus1Lsb = 20;
  localparam int unsigned QbsDescKBlocksMinus1Lsb = 25;
  localparam int unsigned QbsDescReservedLsb = 33;

{sv_switch_function(spec, 'weight', 'block_bytes', 'qbs_weight_block_bytes', 'qbs_weight_profile_e')}

{sv_switch_function(spec, 'weight', 'block_elements', 'qbs_weight_block_elements', 'qbs_weight_profile_e')}

{sv_switch_function(spec, 'weight', 'subgroup_count', 'qbs_weight_subgroup_count', 'qbs_weight_profile_e')}

{sv_switch_function(spec, 'weight', 'subgroup_elements', 'qbs_weight_subgroup_elements', 'qbs_weight_profile_e')}

{sv_symbol_switch_function(spec, 'weight', 'scale_format', 'qbs_weight_scale_format', 'qbs_weight_profile_e', 'qbs_scale_format_e', 'QBS_SCALE_', 'QBS_SCALE_INVALID')}

{sv_symbol_switch_function(spec, 'weight', 'correction_mode', 'qbs_weight_correction_mode', 'qbs_weight_profile_e', 'qbs_correction_mode_e', 'QBS_CORRECTION_', 'QBS_CORRECTION_NONE')}

{sv_switch_function(spec, 'activation', 'block_bytes', 'qbs_activation_block_bytes', 'qbs_activation_profile_e')}

{sv_switch_function(spec, 'activation', 'block_elements', 'qbs_activation_block_elements', 'qbs_activation_profile_e')}

{sv_symbol_switch_function(spec, 'activation', 'scale_format', 'qbs_activation_scale_format', 'qbs_activation_profile_e', 'qbs_scale_format_e', 'QBS_SCALE_', 'QBS_SCALE_INVALID')}

{sv_switch_function(spec, 'activation', 'scale_bytes', 'qbs_activation_scale_bytes', 'qbs_activation_profile_e')}

{sv_switch_function(spec, 'activation', 'quant_bytes', 'qbs_activation_quant_bytes', 'qbs_activation_profile_e')}

{sv_switch_function(spec, 'activation', 'aux_count', 'qbs_activation_aux_count', 'qbs_activation_profile_e')}

{sv_switch_function(spec, 'activation', 'aux_element_bytes', 'qbs_activation_aux_element_bytes', 'qbs_activation_profile_e')}

{sv_compatibility_function(spec)}

{sv_default_activation_function(spec)}

  function automatic logic [63:0] qbs_capability_word(
      input logic [63:0] index,
      input int unsigned vlen_bits
  );
    int unsigned max_n;
    logic [63:0] result;
    max_n = vlen_bits / 32;
    if (max_n > QbsMaxN) max_n = QbsMaxN;
    result = '0;
    unique case (index)
      64'h00: begin
        if (max_n != 0) begin
          result[7:0]   = 8'(QbsArchitectureVersion);
          result[15:8]  = 8'(QbsDescriptorVersion);
          result[23:16] = 8'(QbsDescriptorBytes);
          result[25:24] = 2'(QbsMaxM - 1);
          result[30:26] = 5'(max_n - 1);
          result[38:31] = 8'(QbsMaxKBlocks - 1);
          result[42:39] = 4'(QbsNumericalContractVersion);
          result[47:43] = 5'b1_1111;
        end
      end
      64'h01: begin
{chr(10).join(layout_lines)}
        result[39:32] = 8'(QbsDescriptorAlignmentLog2);
        result[47:40] = 8'(QbsWeightBaseAlignmentLog2);
        result[55:48] = 8'(QbsActivationBaseAlignmentLog2);
        result[63:56] = 8'd32;
      end
{sv_capability_cases(spec)}
      default: ;
    endcase
    return result;
  endfunction : qbs_capability_word

endpackage : qbs_pkg
"""


def update(path: Path, content: str, check: bool) -> bool:
    current = path.read_text(encoding="utf-8") if path.exists() else None
    if current == content:
        return True
    if check:
        print(f"stale generated file: {path.relative_to(ROOT)}", file=sys.stderr)
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    print(f"wrote {path.relative_to(ROOT)}")
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    try:
        spec = load_spec()
        validate_spec(spec)
    except (KeyError, TypeError, ValueError) as error:
        print(f"invalid QBS ABI specification: {error}", file=sys.stderr)
        return 2
    ok = all(update(path, c_header(spec), args.check) for path in C_PATHS)
    ok &= update(SV_PATH, sv_package(spec), args.check)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
