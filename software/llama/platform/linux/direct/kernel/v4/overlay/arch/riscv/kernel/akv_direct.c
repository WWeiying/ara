// SPDX-License-Identifier: GPL-2.0
/* Isolated UP test environment. Hardware prerequisites are in v4/README.md. */
#include <linux/akv_direct.h>
#include <linux/akv_direct_policy.h>
#include <linux/capability.h>
#include <linux/cpu.h>
#include <linux/init.h>
#include <linux/miscdevice.h>
#include <linux/mm.h>
#include <linux/mmu_notifier.h>
#include <linux/mutex.h>
#include <linux/ptrace.h>
#include <linux/sched/signal.h>
#include <linux/sched/task.h>
#include <linux/slab.h>
#include <linux/uaccess.h>
#include <asm/asm-extable.h>
#include <asm/csr.h>
#include <asm/smp.h>
#include <asm/unistd.h>
#include <asm/vector.h>

struct akv_file {
	struct mmu_notifier notifier;
	struct task_struct *owner;
	struct mm_struct *mm;
	bool registered;
	bool invalid;
	bool active;
};

static DEFINE_MUTEX(akv_control);
static DEFINE_RAW_SPINLOCK(akv_lock);
static struct akv_file *akv_lease;
static bool akv_present;
static bool akv_user_granted;
static bool akv_poisoned;
static u64 akv_generation;

/* Exception-table fixups cover an absent CSR on older hardware. */
static int akv_probe(unsigned long *value)
{
	unsigned long v;
	int err;

	asm volatile("1: csrr %0, 0x5c0\n"
		     "li %1, 0\nj 4f\n"
		     "3: li %0, 0\nli %1, -19\n4:\n"
		     _ASM_EXTABLE(1b, 3b)
		     : "=&r" (v), "=&r" (err) : : "memory");
	*value = v;
	return err;
}

static int akv_probe_strict(void)
{
	int err;
	unsigned long mode = ARA_AKV_GATE_STRICT;

	asm volatile("1: csrw 0x5c0, %1\n"
		     "li %0, 0\nj 4f\n"
		     "3: li %0, -19\n4:\n"
		     _ASM_EXTABLE(1b, 3b)
		     : "=&r" (err) : "r" (mode) : "memory");
	return err;
}

/*
 * UP, IRQs off, before RCU/context tracking and before ecall V discard.
 * Only final owner return sets the grant. Consume it exactly once, before
 * Linux can skip a dirty-state save or transfer physical VRF ownership.
 */
void noinstr riscv_akv_direct_user_enter(struct pt_regs *regs)
{
	unsigned long status;

	if (!READ_ONCE(akv_present))
		return;
	csr_write(ARA_AKV_GATE_CSR, ARA_AKV_GATE_STRICT);
	if (!READ_ONCE(akv_user_granted))
		return;
	WRITE_ONCE(akv_user_granted, false);
	status = csr_read_set(CSR_STATUS, SR_VS);
	asm volatile("csrr zero, vl\nfence rw, rw" : : : "memory");
	csr_clear(CSR_STATUS, SR_VS);
	csr_set(CSR_STATUS, status & SR_VS);
	/* ACQUIRE requires allocated, enabled V state and enabled F state. */
	if (regs->status & SR_VS)
		regs->status |= SR_VS_DIRTY;
	if (regs->status & SR_FS)
		regs->status |= SR_FS_DIRTY;
}

/* A switch must not drop an outstanding grant without performing its drain. */
void noinstr riscv_akv_direct_enter(void)
{
	riscv_akv_direct_user_enter(task_pt_regs(current));
}

/*
 * IRQs off, UP only. External-memory/Resident terminal completion and
 * CSR-vl draining of local replay are HARDWARE prerequisites.
 * RELEASE must not write VRF, VL, VTYPE or FCSR.
 * No kernel_vector_begin(): this path is also used by scheduler/MM hooks.
 */
static int akv_clean_locked(void)
{
	unsigned long status, start;
	int err;

	WRITE_ONCE(akv_user_granted, false);
	csr_write(ARA_AKV_GATE_CSR, ARA_AKV_GATE_STRICT);
	status = csr_read(CSR_STATUS);
	csr_set(CSR_STATUS, SR_VS);
	start = csr_read(CSR_VSTART);
	asm volatile("csrr zero, vl\nfence rw, rw" : : : "memory");
	csr_write(CSR_VSTART, 0);
	csr_write(ARA_AKV_GATE_CSR,
		  ARA_AKV_GATE_STRICT | ARA_AKV_GATE_SUPERVISOR);
	asm volatile("1: .word 0x0000505b\n"
		     "li %0, 0\nj 4f\n"
		     "3: li %0, -5\n4:\n"
		     _ASM_EXTABLE(1b, 3b)
		     : "=&r" (err) : : "memory");
	asm volatile("csrr zero, vl\nfence rw, rw" : : : "memory");
	csr_write(ARA_AKV_GATE_CSR, ARA_AKV_GATE_STRICT);
	csr_write(CSR_VSTART, start);
	csr_clear(CSR_STATUS, SR_VS);
	csr_set(CSR_STATUS, status & SR_VS);
	if (err)
		akv_poisoned = true;
	return err;
}

static bool akv_authorized(void)
{
	return uid_eq(current_euid(), GLOBAL_ROOT_UID) &&
	       ns_capable(&init_user_ns, CAP_SYS_RAWIO);
}

/* All callers hold akv_lock. A revoked FD retains exclusivity until close. */
static struct task_struct *akv_revoke_locked(struct akv_file *f, bool kill)
{
	struct task_struct *victim = NULL;

	f->invalid = true;
	if (f->active) {
		f->active = false;
		akv_clean_locked();
		if (akv_generation != U64_MAX)
			akv_generation++;
		else
			akv_poisoned = true;
		if (kill) {
			victim = f->owner;
			get_task_struct(victim);
		}
	}
	return victim;
}

static void akv_kill(struct task_struct *victim)
{
	if (victim) {
		send_sig(SIGKILL, victim, 1);
		put_task_struct(victim);
	}
}

void riscv_akv_direct_abort(void)
{
	unsigned long flags;
	struct task_struct *victim = NULL;

	raw_spin_lock_irqsave(&akv_lock, flags);
	if (akv_lease && akv_lease->owner == current)
		victim = akv_revoke_locked(akv_lease, true);
	raw_spin_unlock_irqrestore(&akv_lock, flags);
	akv_kill(victim);
}

void riscv_akv_direct_exit(struct task_struct *task)
{
	unsigned long flags;

	raw_spin_lock_irqsave(&akv_lock, flags);
	if (akv_lease && akv_lease->owner == task)
		akv_revoke_locked(akv_lease, false);
	raw_spin_unlock_irqrestore(&akv_lock, flags);
}

bool riscv_akv_direct_fault(struct pt_regs *regs)
{
	unsigned long flags;
	struct task_struct *victim = NULL;

	if (!user_mode(regs))
		return false;
	raw_spin_lock_irqsave(&akv_lock, flags);
	if (akv_lease && akv_lease->owner == current && akv_lease->active)
		victim = akv_revoke_locked(akv_lease, true);
	raw_spin_unlock_irqrestore(&akv_lock, flags);
	if (!victim)
		return false;
	akv_kill(victim);
	return true;
}

bool riscv_akv_direct_syscall(long nr)
{
	bool reject = false;
	unsigned long flags;
	struct task_struct *victim = NULL;

	switch (nr) {
	case __NR_clone:
	case __NR_clone3:
	case __NR_execve:
	case __NR_execveat:
	case __NR_sched_setaffinity:
		raw_spin_lock_irqsave(&akv_lock, flags);
		if (akv_lease && akv_lease->owner == current && akv_lease->active) {
			victim = akv_revoke_locked(akv_lease, true);
			reject = true;
		}
		raw_spin_unlock_irqrestore(&akv_lock, flags);
		akv_kill(victim);
	}
	return reject;
}

void riscv_akv_direct_return(void)
{
	unsigned long flags;
	struct task_struct *victim = NULL;
	struct akv_file *f;

	if (!READ_ONCE(akv_present))
		return;
	raw_spin_lock_irqsave(&akv_lock, flags);
	csr_write(ARA_AKV_GATE_CSR, ARA_AKV_GATE_STRICT);
	f = akv_lease;
	if (f && f->active && f->owner == current) {
		if (akv_poisoned || f->invalid || f->mm != current->mm ||
		    signal_pending(current) || current->ptrace ||
		    get_nr_threads(current) != 1 || !uid_eq(current_euid(), GLOBAL_ROOT_UID) ||
		    !current->thread.vstate.datap ||
		    !(task_pt_regs(current)->status & SR_VS) ||
		    !(task_pt_regs(current)->status & SR_FS) ||
		    !riscv_v_vstate_ctrl_user_allowed())
			victim = akv_revoke_locked(f, true);
		else {
			WRITE_ONCE(akv_user_granted, true);
			csr_write(ARA_AKV_GATE_CSR,
				  ARA_AKV_GATE_STRICT | ARA_AKV_GATE_USER);
		}
	}
	raw_spin_unlock_irqrestore(&akv_lock, flags);
	akv_kill(victim);
}

static int akv_invalidate(struct mmu_notifier *mn,
			  const struct mmu_notifier_range *range)
{
	struct akv_file *f = container_of(mn, struct akv_file, notifier);
	struct task_struct *victim;
	unsigned long flags;

	raw_spin_lock_irqsave(&akv_lock, flags);
	victim = akv_revoke_locked(f, true);
	raw_spin_unlock_irqrestore(&akv_lock, flags);
	akv_kill(victim);
	return 0;
}

static void akv_mm_release(struct mmu_notifier *mn, struct mm_struct *mm)
{
	akv_invalidate(mn, NULL);
}

static const struct mmu_notifier_ops akv_mn_ops = {
	.invalidate_range_start = akv_invalidate,
	.release = akv_mm_release,
};

/* akv_control held; notifier unregister may sleep, never under akv_lock. */
static void akv_detach(struct akv_file *f)
{
	unsigned long flags;

	if (f->registered) {
		mmu_notifier_unregister(&f->notifier, f->mm);
		f->registered = false;
	}
	raw_spin_lock_irqsave(&akv_lock, flags);
	if (akv_lease == f)
		akv_lease = NULL;
	raw_spin_unlock_irqrestore(&akv_lock, flags);
	if (f->owner)
		put_task_struct(f->owner);
	f->owner = NULL;
	f->mm = NULL;
}

static int akv_acquire(struct akv_file *f, void __user *arg)
{
	struct ara_akv_direct_lease v;
	unsigned long flags;
	int err;

	if (copy_from_user(&v, arg, sizeof(v)))
		return -EFAULT;
	if (!akv_direct_valid_lease(&v))
		return -EINVAL;
	if (!akv_present)
		return -ENODEV;
	if (!akv_authorized())
		return -EPERM;
	if (akv_poisoned)
		return -EIO;
	if (akv_lease || f->owner)
		return -EBUSY;
	if (!current->mm || get_nr_threads(current) != 1 ||
	    atomic_read(&current->mm->mm_users) != 1 || current->ptrace ||
	    is_global_init(current) || signal_pending(current) ||
	    num_online_cpus() != 1 || smp_processor_id() != 0 ||
	    cpuid_to_hartid_map(0) != 0 || !has_vector() ||
	    !riscv_v_vstate_ctrl_user_allowed() || !current->thread.vstate.datap ||
	    !(task_pt_regs(current)->status & SR_VS) ||
	    !(task_pt_regs(current)->status & SR_FS))
		return -EPERM;
	f->owner = current;
	get_task_struct(current);
	f->mm = current->mm;
	f->invalid = false;
	f->notifier.ops = &akv_mn_ops;
	err = mmu_notifier_register(&f->notifier, f->mm);
	if (err)
		goto fail;
	f->registered = true;
	raw_spin_lock_irqsave(&akv_lock, flags);
	akv_lease = f;
	if (f->invalid || akv_generation == U64_MAX)
		err = -EOVERFLOW;
	else
		err = akv_clean_locked();
	if (!err)
		v.generation = ++akv_generation;
	raw_spin_unlock_irqrestore(&akv_lock, flags);
	if (err)
		goto fail;
	v.owner_tid = task_pid_vnr(current);
	v.hart = 0;
	if (copy_to_user(arg, &v, sizeof(v))) {
		err = -EFAULT;
		goto fail;
	}
	raw_spin_lock_irqsave(&akv_lock, flags);
	if (f->invalid || signal_pending(current))
		err = -EAGAIN;
	else
		f->active = true;
	raw_spin_unlock_irqrestore(&akv_lock, flags);
	if (!err)
		return 0;
fail:
	akv_detach(f);
	return err;
}

static long akv_ioctl(struct file *file, unsigned int cmd, unsigned long arg)
{
	struct akv_file *f = file->private_data;
	struct ara_akv_direct_info info = {0};
	unsigned long flags;
	int err = 0;

	mutex_lock(&akv_control);
	switch (cmd) {
	case ARA_AKV_DIRECT_GET_INFO:
		if (!akv_present) {
			err = -ENODEV;
			break;
		}
		info.abi = ARA_AKV_DIRECT_ABI;
		info.bytes = sizeof(info);
		info.features = ARA_AKV_DIRECT_REQUIRED_FEATURES;
		info.online_cpus = num_online_cpus();
		info.gate_signature = ARA_AKV_GATE_SIGNATURE;
		info.generation = akv_generation;
		if (copy_to_user((void __user *)arg, &info, sizeof(info)))
			err = -EFAULT;
		break;
	case ARA_AKV_DIRECT_ACQUIRE:
		err = akv_acquire(f, (void __user *)arg);
		break;
	case ARA_AKV_DIRECT_RELEASE:
		if (arg) {
			err = -EINVAL;
			break;
		}
		if (!f->owner) {
			err = -ENOENT;
			break;
		}
		if (f->owner != current || f->mm != current->mm) {
			err = -EPERM;
			break;
		}
		raw_spin_lock_irqsave(&akv_lock, flags);
		akv_revoke_locked(f, false);
		err = akv_poisoned ? -EIO : 0;
		raw_spin_unlock_irqrestore(&akv_lock, flags);
		akv_detach(f);
		break;
	default:
		err = -ENOTTY;
	}
	mutex_unlock(&akv_control);
	return err;
}

static int akv_open(struct inode *inode, struct file *file)
{
	if (!akv_authorized())
		return -EPERM;
	file->private_data = kzalloc(sizeof(struct akv_file), GFP_KERNEL);
	return file->private_data ? nonseekable_open(inode, file) : -ENOMEM;
}

static int akv_close(struct inode *inode, struct file *file)
{
	struct akv_file *f = file->private_data;
	struct task_struct *victim;
	unsigned long flags;

	mutex_lock(&akv_control);
	raw_spin_lock_irqsave(&akv_lock, flags);
	victim = akv_revoke_locked(f, f->owner != current);
	raw_spin_unlock_irqrestore(&akv_lock, flags);
	akv_kill(victim);
	akv_detach(f);
	mutex_unlock(&akv_control);
	kfree(f);
	return 0;
}

static const struct file_operations akv_fops = {
	.open = akv_open,
	.release = akv_close,
	.unlocked_ioctl = akv_ioctl,
	.llseek = NULL,
};

static struct miscdevice akv_device = {
	.minor = MISC_DYNAMIC_MINOR,
	.name = "ara-akv-direct",
	.fops = &akv_fops,
	.mode = 0600,
};

static int __init akv_init(void)
{
	unsigned long value, flags;
	int err;

	BUILD_BUG_ON(sizeof(struct ara_akv_direct_info) != 64);
	BUILD_BUG_ON(sizeof(struct ara_akv_direct_lease) != 64);
	local_irq_save(flags);
	err = akv_probe(&value);
	if (!err && akv_direct_valid_gate(value)) {
		err = akv_probe_strict();
		if (!err)
			err = akv_probe(&value);
		if (!err && akv_direct_valid_gate(value) &&
		    (value & 7) == ARA_AKV_GATE_STRICT)
			WRITE_ONCE(akv_present, true);
	}
	local_irq_restore(flags);
	pr_warn("AKV direct TEST kernel: gate %s; ara_resident prohibited\n",
		akv_present ? "STRICT (unleased AKV disabled)" : "unavailable");
	return misc_register(&akv_device);
}
device_initcall(akv_init);
