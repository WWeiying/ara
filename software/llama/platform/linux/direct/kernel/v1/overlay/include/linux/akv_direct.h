/* SPDX-License-Identifier: GPL-2.0 */
#ifndef _LINUX_AKV_DIRECT_H
#define _LINUX_AKV_DIRECT_H

#include <linux/types.h>
#include <linux/compiler.h>

struct pt_regs;
struct task_struct;

#ifdef CONFIG_RISCV_AKV_DIRECT
void riscv_akv_direct_enter(void);
void riscv_akv_direct_return(void);
void riscv_akv_direct_abort(void);
bool riscv_akv_direct_fault(struct pt_regs *regs);
bool riscv_akv_direct_syscall(long nr);
void riscv_akv_direct_exit(struct task_struct *task);
#else
static inline void riscv_akv_direct_enter(void) { }
static inline void riscv_akv_direct_return(void) { }
static inline void riscv_akv_direct_abort(void) { }
static inline bool riscv_akv_direct_fault(struct pt_regs *regs) { return false; }
static inline bool riscv_akv_direct_syscall(long nr) { return false; }
static inline void riscv_akv_direct_exit(struct task_struct *task) { }
#endif
#endif
