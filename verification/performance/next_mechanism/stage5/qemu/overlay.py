"""Exact-anchor QEMU 10.2.0 successor patch; pure transformations, no IO."""

EDITS = {
    "target/riscv/cpu_cfg_fields.h.inc": [
        ("BOOL_FIELD(ext_Xaraqbs)\n",
         "BOOL_FIELD(ext_Xaraqbs)\nBOOL_FIELD(ext_Xaraakv)\nBOOL_FIELD(ext_XaraakvResident)\n")],
    "target/riscv/cpu_cfg.h": [
        ("MATERIALISE_EXT_PREDICATE(Xaraqbs)\n",
         "MATERIALISE_EXT_PREDICATE(Xaraqbs)\nMATERIALISE_EXT_PREDICATE(Xaraakv)\n")],
    "target/riscv/cpu.h": [
        ('#include "qbs_ref.h"\n', '#include "qbs_ref.h"\n#include "akv_model.h"\n'),
        ("    qbs_ref_activation_context_t qbs_activation_context;\n",
         "    qbs_ref_activation_context_t qbs_activation_context;\n"
         "    akv_model akv_context;\n    uint64_t akv_sequence;\n")],
    "target/riscv/cpu.c": [
        ("    ISA_EXT_DATA_ENTRY(xaraqbs, PRIV_VERSION_1_12_0, ext_Xaraqbs),\n",
         "    ISA_EXT_DATA_ENTRY(xaraqbs, PRIV_VERSION_1_12_0, ext_Xaraqbs),\n"
         "    ISA_EXT_DATA_ENTRY(xaraakv, PRIV_VERSION_1_12_0, ext_Xaraakv),\n"),
        ('    MULTI_EXT_CFG_BOOL("xaraqbs", ext_Xaraqbs, false),\n',
         '    MULTI_EXT_CFG_BOOL("xaraqbs", ext_Xaraqbs, false),\n'
         '    MULTI_EXT_CFG_BOOL("xaraakv", ext_Xaraakv, false),\n'),
        ('static const Property riscv_cpu_properties[] = {\n',
         'static const Property riscv_cpu_properties[] = {\n'
         '    DEFINE_PROP_BOOL("xaraakv-resident", RISCVCPU, cfg.ext_XaraakvResident, false),\n'),
        ("    qbs_ref_activation_context_reset(&env->qbs_activation_context);\n",
         "    qbs_ref_activation_context_reset(&env->qbs_activation_context);\n"
         "    akv_model_reset(&env->akv_context);\n    env->akv_sequence = 0;\n"),
        ("    riscv_cpu_register_gdb_regs_for_features(cs);\n",
         "    if (cpu->cfg.ext_XaraakvResident &&\n"
         "        (!cpu->cfg.ext_Xaraakv || !cpu->cfg.ext_zvfh)) {\n"
         '        error_setg(errp, "xaraakv-resident requires xaraakv and zvfh");\n'
         "        return;\n    }\n"
         "    if (cpu->cfg.ext_Xaraakv && (!tcg_enabled() || HOST_BIG_ENDIAN)) {\n"
         '        error_setg(errp, "xaraakv requires little-endian-host TCG");\n'
         "        return;\n    }\n"
         "    riscv_cpu_register_gdb_regs_for_features(cs);\n")],
    "target/riscv/helper.h": [
        ("/* Xaraqbs quantized block-stream extension */\n",
         "/* Experimental AKV; INFO index 4 remains zero. */\n"
         "DEF_HELPER_2(akv_info, tl, env, tl)\n"
         "DEF_HELPER_5(akv_exec, void, env, tl, tl, i32, tl)\n\n"
         "/* Xaraqbs quantized block-stream extension */\n")],
    "target/riscv/translate.c": [
        ('#include "insn_trans/trans_xaraqbs.c.inc"\n',
         '#include "insn_trans/trans_xaraqbs.c.inc"\n'
         '#include "decode-Xaraakv.c.inc"\n#include "insn_trans/trans_xaraakv.c.inc"\n'),
        ("    { has_Xaraqbs_p, decode_Xaraqbs},\n",
         "    { has_Xaraqbs_p, decode_Xaraqbs},\n    { has_Xaraakv_p, decode_Xaraakv},\n")],
    "target/riscv/meson.build": [
        ("  decodetree.process('Xaraqbs.decode', extra_args: '--static-decode=decode_Xaraqbs'),\n",
         "  decodetree.process('Xaraqbs.decode', extra_args: '--static-decode=decode_Xaraqbs'),\n"
         "  decodetree.process('Xaraakv.decode', extra_args: '--static-decode=decode_Xaraakv'),\n"),
        ("  'qbs_helper.c',\n", "  'qbs_helper.c',\n  'akv_helper.c',\n  'akv_model.c',\n")],
    "target/riscv/machine.c": [
        ("static int riscv_cpu_post_load(void *opaque, int version_id)\n",
         "static int riscv_akv_pre_save(void *opaque)\n{\n"
         "    RISCVCPU *cpu = opaque;\n"
         "    return cpu->cfg.ext_Xaraakv ? -ENOTSUP : 0;\n}\n\n"
         "static int riscv_cpu_post_load(void *opaque, int version_id)\n"),
        ("    env->xl = cpu_recompute_xl(env);\n",
         "    if (cpu->cfg.ext_Xaraakv) {\n        return -ENOTSUP;\n    }\n"
         "    env->xl = cpu_recompute_xl(env);\n"),
        ("    .post_load = riscv_cpu_post_load,\n",
         "    .pre_save = riscv_akv_pre_save,\n    .post_load = riscv_cpu_post_load,\n")],
    "include/hw/riscv/virt.h": [
        ("    bool have_aclint;\n", "    bool have_aclint;\n    bool ara_stage4;\n")],
    "hw/riscv/virt.c": [
        ('#include "hw/riscv/virt.h"\n',
         '#include "hw/riscv/virt.h"\n#include "hw/riscv/ara_stage4.h"\n'),
        ("    riscv_setup_rom_reset_vec(machine, &s->soc[0], start_addr,\n"
         "                              s->memmap[VIRT_MROM].base,\n"
         "                              s->memmap[VIRT_MROM].size, kernel_entry,\n"
         "                              fdt_load_addr);\n",
         "    if (s->ara_stage4) {\n"
         "        riscv_ara_stage4_reset_vec(machine, s->memmap[VIRT_MROM].base,\n"
         "                                  s->memmap[VIRT_MROM].size, kernel_entry);\n"
         "    } else {\n"
         "        riscv_setup_rom_reset_vec(machine, &s->soc[0], start_addr,\n"
         "                                  s->memmap[VIRT_MROM].base,\n"
         "                                  s->memmap[VIRT_MROM].size, kernel_entry,\n"
         "                                  fdt_load_addr);\n    }\n"),
        ("    /* boot rom */\n",
         "    if (s->ara_stage4) {\n        riscv_ara_stage4_init(machine);\n    }\n\n"
         "    /* boot rom */\n"),
        ("static void virt_machine_class_init(ObjectClass *oc, const void *data)\n",
         "static bool virt_get_ara_stage4(Object *obj, Error **errp)\n{\n"
         "    return RISCV_VIRT_MACHINE(obj)->ara_stage4;\n}\n\n"
         "static void virt_set_ara_stage4(Object *obj, bool value, Error **errp)\n{\n"
         "    RISCV_VIRT_MACHINE(obj)->ara_stage4 = value;\n}\n\n"
         "static void virt_machine_class_init(ObjectClass *oc, const void *data)\n"),
        ('    object_class_property_add_bool(oc, "aclint", virt_get_aclint,\n',
         '    object_class_property_add_bool(oc, "x-ara-stage4", virt_get_ara_stage4,\n'
         '                                   virt_set_ara_stage4);\n'
         '    object_class_property_add_bool(oc, "aclint", virt_get_aclint,\n')],
    "hw/riscv/meson.build": [
        ("riscv_ss.add(when: 'CONFIG_RISCV_VIRT', if_true: files('virt.c'))\n",
         "riscv_ss.add(when: 'CONFIG_RISCV_VIRT', if_true: files('virt.c', 'ara_stage4.c'))\n")],
}

TRACE_EVENTS = '''
# Experimental AKV architectural events, NOT RTL retirement or cycle counters.
akv_arch_info(uint64_t index, uint64_t result) "index=%" PRIu64 " result=0x%" PRIx64
akv_arch_begin(uint64_t seq, uint64_t pc, uint32_t insn, uint64_t rs1, uint64_t rs2, uint32_t frm, uint32_t fflags) "seq=%" PRIu64 " pc=0x%" PRIx64 " insn=0x%08x rs1=0x%" PRIx64 " rs2=0x%" PRIx64 " frm=%u fflags=%u"
akv_arch_read(uint64_t seq, uint64_t pc, uint64_t address, uint64_t bytes) "seq=%" PRIu64 " pc=0x%" PRIx64 " address=0x%" PRIx64 " bytes=%" PRIu64
akv_arch_end(uint64_t seq, uint64_t pc, unsigned status, unsigned fflags, bool valid, uint64_t tile, unsigned tokens, uint64_t tval) "seq=%" PRIu64 " pc=0x%" PRIx64 " status=%u fflags=%u valid=%d tile=%" PRIu64 " tokens=%u tval=0x%" PRIx64
'''

FILES = {
    "Xaraakv.decode": "target/riscv/Xaraakv.decode",
    "trans_xaraakv.c.inc": "target/riscv/insn_trans/trans_xaraakv.c.inc",
    "akv_helper.c": "target/riscv/akv_helper.c",
    "akv_model.h": "target/riscv/akv_model.h",
    "akv_model.c": "target/riscv/akv_model.c",
    "ara_stage4.h": "include/hw/riscv/ara_stage4.h",
    "ara_stage4.c": "hw/riscv/ara_stage4.c",
}


def transform(relative, text):
    if any(new in text for _, new in EDITS[relative]):
        raise ValueError("Already/partially applied overlay: " + relative)
    for old, new in EDITS[relative]:
        if text.count(old) != 1:
            raise ValueError("Missing/ambiguous source anchor: " + relative)
        text = text.replace(old, new, 1)
    return text
