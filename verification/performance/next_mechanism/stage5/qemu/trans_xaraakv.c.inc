/* SPDX-License-Identifier: GPL-2.0-or-later */
/* Experimental, fixed-VLEN architecture model; no cycle/overlap model. */

static bool trans_akvinfo(DisasContext *ctx, arg_akvinfo *a)
{
    TCGv result;

    /* Scalar discovery does not read vector/FP state. Unsupported VLEN is 0. */
    result = dest_gpr(ctx, a->rd);
    gen_helper_akv_info(result, tcg_env, get_gpr(ctx, a->rs1, EXT_NONE));
    gen_set_gpr(ctx, a->rd, result);
    return true;
}

static bool trans_akvexec(DisasContext *ctx, arg_akvexec *a)
{
    unsigned funct3 = (ctx->opcode >> 12) & 7;
    unsigned funct7 = ctx->opcode >> 25;
    bool resident = funct3 == 7 && (funct7 == 2 || funct7 == 3);

    if (ctx->mstatus_vs == EXT_STATUS_DISABLED ||
        !ctx->cfg_ptr->ext_zve32f || ctx->cfg_ptr->vlenb != 128 ||
        !ctx->vstart_eq_zero) {
        return false;
    }
    if (resident && (!ctx->cfg_ptr->ext_XaraakvResident ||
                     !ctx->cfg_ptr->ext_zvfh ||
                     ctx->mstatus_fs == EXT_STATUS_DISABLED)) {
        return false;
    }

    gen_helper_akv_exec(tcg_env, get_gpr(ctx, a->rs1, EXT_NONE),
                        get_gpr(ctx, a->rs2, EXT_NONE),
                        tcg_constant_i32(ctx->opcode),
                        tcg_constant_tl(ctx->base.pc_next));
    mark_vs_dirty(ctx);
    if (resident) {
        mark_fs_dirty(ctx);
    }
    ctx->vstart_eq_zero = true;
    return true;
}
