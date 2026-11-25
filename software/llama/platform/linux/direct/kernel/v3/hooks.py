#!/usr/bin/env python3
"""Exact-context Linux 6.19.6 hook patch generator; never edits the base."""
import difflib


def patch(base):
    edits = {}

    def replace(path, old, new):
        if path not in edits:
            original = (base / path).read_text()
            edits[path] = [original, original]
        text = edits[path][1]
        if text.count(old) != 1:
            raise ValueError("non-unique/missing hook context: " + path)
        edits[path][1] = text.replace(old, new, 1)

    path = "arch/riscv/include/asm/entry-common.h"
    replace(path, "#include <asm/stacktrace.h>",
            "#include <linux/akv_direct.h>\n#include <asm/stacktrace.h>")
    replace(path, "static inline void arch_exit_to_user_mode_prepare",
            "static __always_inline void arch_enter_from_user_mode(struct pt_regs *regs)\n"
            "{\n\triscv_akv_direct_user_enter(regs);\n}\n"
            "#define arch_enter_from_user_mode arch_enter_from_user_mode\n\n"
            "static inline void arch_exit_to_user_mode_prepare")
    replace(path, "\t}\n}\n\n#define arch_exit_to_user_mode_prepare",
            "\t}\n\triscv_akv_direct_return();\n}\n\n#define arch_exit_to_user_mode_prepare")
    path = "arch/riscv/include/asm/switch_to.h"
    replace(path, "#include <linux/jump_label.h>",
            "#include <linux/akv_direct.h>\n#include <linux/jump_label.h>")
    replace(path, "\t__set_prev_cpu(__prev->thread);",
            "\triscv_akv_direct_enter();\t\t\t\\\n\t__set_prev_cpu(__prev->thread);")
    path = "arch/riscv/kernel/traps.c"
    replace(path, "#include <linux/cpu.h>",
            "#include <linux/akv_direct.h>\n#include <linux/cpu.h>")
    replace(path, "\t\tdo_trap(regs, signo, code, addr);",
            "\t\tif (!riscv_akv_direct_fault(regs))\n"
            "\t\t\tdo_trap(regs, signo, code, addr);")
    replace(path, "\tif (misaligned_handler[type].handler(regs))",
            "\tif (!riscv_akv_direct_fault(regs) &&\n"
            "\t    misaligned_handler[type].handler(regs))")
    replace(path, "\t\triscv_v_vstate_discard(regs);",
            "\t\triscv_akv_direct_user_enter(regs);\n\t\triscv_v_vstate_discard(regs);")
    replace(path, "\t\tif (syscall >= 0 && syscall < NR_syscalls) {",
            "\t\tif (riscv_akv_direct_syscall(syscall))\n"
            "\t\t\tregs->a0 = -EPERM;\n"
            "\t\telse if (syscall >= 0 && syscall < NR_syscalls) {")
    path = "arch/riscv/mm/fault.c"
    replace(path, "#include <linux/mm.h>",
            "#include <linux/akv_direct.h>\n#include <linux/mm.h>")
    replace(path, "\tif (kprobe_page_fault(regs, cause))",
            "\t/* Never retry a leased custom fault (including REFILL). */\n"
            "\tif (riscv_akv_direct_fault(regs))\n\t\treturn;\n\n"
            "\tif (kprobe_page_fault(regs, cause))")
    path = "arch/riscv/kernel/signal.c"
    replace(path, "#include <linux/compat.h>",
            "#include <linux/akv_direct.h>\n#include <linux/compat.h>")
    replace(path, "\tbool syscall = (regs->cause == EXC_SYSCALL);\n",
            "\tbool syscall = (regs->cause == EXC_SYSCALL);\n\n"
            "\t/* Revoke before get_signal can stop/exit or install a handler. */\n"
            "\triscv_akv_direct_abort();\n")
    path = "kernel/exit.c"
    replace(path, "#include <linux/mm.h>",
            "#include <linux/akv_direct.h>\n#include <linux/mm.h>")
    replace(path, "\texit_mm();", "\triscv_akv_direct_exit(tsk);\n\texit_mm();")
    path = "kernel/module/main.c"
    replace(path, "\tif (flags & MODULE_INIT_IGNORE_VERMAGIC)",
            "\t/* This TEST kernel cannot coexist with the S-mode broker. */\n"
            "\tif (IS_ENABLED(CONFIG_RISCV_AKV_DIRECT) &&\n"
            "\t    !strcmp(mod->name, \"ara_resident\"))\n"
            "\t\treturn -EOPNOTSUPP;\n\n"
            "\tif (flags & MODULE_INIT_IGNORE_VERMAGIC)")
    replace("arch/riscv/Kconfig", 'source "arch/riscv/kvm/Kconfig"',
            'source "arch/riscv/kvm/Kconfig"\n\nsource "arch/riscv/Kconfig.akv_direct"')
    replace("arch/riscv/kernel/Makefile", "obj-y\t+= traps.o",
            "obj-y\t+= traps.o\nobj-$(CONFIG_RISCV_AKV_DIRECT) += akv_direct.o")
    return "".join("".join(difflib.unified_diff(
        before.splitlines(True), after.splitlines(True), "a/" + path, "b/" + path))
        for path, (before, after) in sorted(edits.items()))
