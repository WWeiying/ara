// SPDX-License-Identifier: GPL-2.0-only
/* One complete group owns the local accelerator; no lease escapes this ioctl. */
#include <linux/cpu.h>
#include <linux/kdebug.h>
#include <linux/fs.h>
#include <linux/miscdevice.h>
#include <linux/mm.h>
#include <linux/module.h>
#include <linux/mutex.h>
#include <linux/of.h>
#include <linux/of_address.h>
#include <linux/panic.h>
#include <linux/percpu.h>
#include <linux/platform_device.h>
#include <linux/slab.h>
#include <linux/sizes.h>
#include <linux/uaccess.h>
#include <linux/vmalloc.h>
#include <asm/fpu.h>
#include <asm/simd.h>
#include <asm/smp.h>
#include <asm/vector.h>

#include "ara_resident_uapi.h"
#include "job_layout.h"
#include "sdk/kernel_compute.h"

static DEFINE_MUTEX(accelerator_lock);
static atomic_t device_bound = ATOMIC_INIT(0);
static atomic64_t deployment_epoch = ATOMIC64_INIT(0);
static bool deployment_online;
static DEFINE_PER_CPU(bool, computation_active);
static u64 ram_base, ram_size, allowed_hart;

/* A synchronous kernel fault cannot safely unwind a live accelerator command. */
static int resident_die(struct notifier_block *nb, unsigned long event, void *data)
{
    (void)nb; (void)event; (void)data;
    if (this_cpu_read(computation_active))
        panic("Resident computation fault: hardware reset required; no retry");
    return NOTIFY_DONE;
}

static struct notifier_block resident_die_notifier = {
    .notifier_call = resident_die, .priority = INT_MAX,
};

static bool accelerator_ram(const void *base, size_t bytes)
{
    unsigned long address = (unsigned long)base;
    if (!base || !bytes || bytes > ULONG_MAX - address) return false;
    while (bytes) {
        struct page *page = is_vmalloc_addr((void *)address) ?
            vmalloc_to_page((void *)address) : virt_to_page((void *)address);
        size_t length = min_t(size_t, bytes, PAGE_SIZE - offset_in_page(address));
        phys_addr_t physical;
        if (!page) return false;
        physical = page_to_phys(page) + offset_in_page(address);
        if (physical < ram_base || physical - ram_base >= ram_size ||
            length > ram_size - (physical - ram_base)) return false;
        address += length;
        bytes -= length;
    }
    return true;
}

static int execute_group(struct ara_resident_compute_buffers *b, u64 epoch)
{
    unsigned long irq_flags;
    int result;

    cpus_read_lock();
    /* No other hart may issue an unmediated command to this context. */
    if (num_online_cpus() != 1) {
        cpus_read_unlock();
        return -EOPNOTSUPP;
    }
    if (mutex_lock_interruptible(&accelerator_lock)) {
        cpus_read_unlock();
        return -EINTR;
    }
    if (!READ_ONCE(deployment_online) || epoch != atomic64_read(&deployment_epoch)) {
        result = -ENODEV;
        goto unlock_mutex;
    }
    preempt_disable();
    if (cpuid_to_hartid_map(smp_processor_id()) != allowed_hart ||
        !may_use_simd() || !kernel_fpu_available()) {
        result = -EOPNOTSUPP;
        goto unlock_preempt;
    }
    this_cpu_write(computation_active, true);
    kernel_fpu_begin();
    /* begin/end must run with IRQs enabled; vector_end may enable bottom halves. */
    kernel_vector_begin();
    local_irq_save(irq_flags);
    b->flags = ARA_RESIDENT_COMPUTE_REQUIRED_FLAGS;
    result = ara_resident_compute(b);
    /* CSR requests wait for Ara idle; fence then drains the memory writes. */
    asm volatile("csrr zero, vl\nfence rw,rw" ::: "memory");
    if (result && b->started)
        panic("Resident failed after execution: hardware reset required; no retry");
    local_irq_restore(irq_flags);
    kernel_vector_end();
    kernel_fpu_end();
    this_cpu_write(computation_active, false);
unlock_preempt:
    preempt_enable();
unlock_mutex:
    mutex_unlock(&accelerator_lock);
    cpus_read_unlock();
    return result;
}

static void *copy_input(__u64 address, size_t bytes, void **allocation)
{
    void *raw = kvmalloc(bytes + 63, GFP_KERNEL);
    void *p;
    if (!raw) return ERR_PTR(-ENOMEM);
    p = PTR_ALIGN(raw, 64);
    if (copy_from_user(p, u64_to_user_ptr(address), bytes)) {
        kvfree(raw);
        return ERR_PTR(-EFAULT);
    }
    *allocation = raw;
    return p;
}

static long run_job(void __user *arg, u64 epoch)
{
    struct ara_resident_compute_buffers b = {0};
    struct ara_resident_job job;
    struct ara_resident_sizes sizes;
    void *input_allocations[4] = {0};
    void *scratch_allocation = NULL;
    long rc = -ENOMEM;

    if (copy_from_user(&job, arg, sizeof(job))) return -EFAULT;
    if (!ara_resident_job_sizes(&job, &sizes)) return -EINVAL;
    if (job.output >= (unsigned long)arg ?
        job.output - (unsigned long)arg < sizeof(job) :
        (unsigned long)arg - job.output < sizes.output) return -EINVAL;
    if (!access_ok(u64_to_user_ptr(job.output), sizes.output)) return -EFAULT;
    b.query = copy_input(job.query, sizes.query, &input_allocations[0]);
    if (IS_ERR(b.query)) { rc = PTR_ERR(b.query); b.query = NULL; goto out; }
    b.key = copy_input(job.key, sizes.key, &input_allocations[1]);
    if (IS_ERR(b.key)) { rc = PTR_ERR(b.key); b.key = NULL; goto out; }
    b.value = copy_input(job.value, sizes.value, &input_allocations[2]);
    if (IS_ERR(b.value)) { rc = PTR_ERR(b.value); b.value = NULL; goto out; }
    b.mask = copy_input(job.mask, sizes.mask, &input_allocations[3]);
    if (IS_ERR(b.mask)) { rc = PTR_ERR(b.mask); b.mask = NULL; goto out; }
    b.output = kvzalloc(sizes.output, GFP_KERNEL);
    b.scratch_bytes = ara_resident_compute_scratch_bytes();
    if (!b.scratch_bytes || b.scratch_bytes > SZ_1M - 63) { rc = -EOVERFLOW; goto out; }
    scratch_allocation = kvzalloc(b.scratch_bytes + 63, GFP_KERNEL);
    if (!b.output || !scratch_allocation) goto out;
    b.scratch = PTR_ALIGN(scratch_allocation, 64);
    b.heads = job.heads;
    b.dimension = job.dimension;
    b.tokens = job.tokens;
    b.scale_bits = job.scale_bits;
    if (!accelerator_ram(b.query, sizes.query) || !accelerator_ram(b.key, sizes.key) ||
        !accelerator_ram(b.value, sizes.value) || !accelerator_ram(b.mask, sizes.mask) ||
        !accelerator_ram(b.output, sizes.output) || !accelerator_ram(b.scratch, b.scratch_bytes)) {
        rc = -EOPNOTSUPP;
        goto out;
    }
    rc = execute_group(&b, epoch);
    /* No publication on computation failure; output stays kernel-private. */
    if (rc) {
        if (b.started) rc = -EIO;
        goto out;
    }
    if (!b.started || !b.resident_used || b.flags & ~31U) { rc = -EIO; goto out; }
    job.fflags = b.flags;
    /* A failed user copy is terminal, never permission to replay this ioctl. */
    if (copy_to_user(u64_to_user_ptr(job.output), b.output, sizes.output) ||
        copy_to_user(arg, &job, sizeof(job))) rc = -EFAULT;
out:
    kvfree(scratch_allocation);
    kvfree(b.output);
    for (unsigned i = 0; i < 4; ++i) kvfree(input_allocations[i]);
    return rc;
}

static long resident_ioctl(struct file *file, unsigned int command, unsigned long arg)
{
    const u64 epoch = *(u64 *)file->private_data;
    const struct ara_resident_info info = {
        .abi = ARA_RESIDENT_ABI, .bytes = sizeof(info),
        .features = ARA_RESIDENT_FEATURE_ATOMIC_GROUP | ARA_RESIDENT_FEATURE_COPY_IO,
        .dimensions = ARA_RESIDENT_DIM64 | ARA_RESIDENT_DIM96 | ARA_RESIDENT_DIM128,
        .max_heads = ARA_RESIDENT_MAX_HEADS, .max_tokens = ARA_RESIDENT_MAX_TOKENS,
        .nr_lanes = 4, .vlen_bits = 1024,
    };
    if (!READ_ONCE(deployment_online) || epoch != atomic64_read(&deployment_epoch)) return -ENODEV;
    switch (command) {
    case ARA_RESIDENT_GET_INFO:
        return copy_to_user((void __user *)arg, &info, sizeof(info)) ? -EFAULT : 0;
    case ARA_RESIDENT_EXECUTE:
        return run_job((void __user *)arg, epoch);
    default:
        return -ENOTTY;
    }
}

static int resident_open(struct inode *inode, struct file *file)
{
    u64 *epoch;
    (void)inode;
    if (!READ_ONCE(deployment_online)) return -ENODEV;
    epoch = kmalloc(sizeof(*epoch), GFP_KERNEL);
    if (!epoch) return -ENOMEM;
    *epoch = atomic64_read(&deployment_epoch);
    file->private_data = epoch;
    return 0;
}

static int resident_close(struct inode *inode, struct file *file)
{
    (void)inode;
    kfree(file->private_data);
    return 0;
}

static const struct file_operations resident_ops = {
    .owner = THIS_MODULE, .open = resident_open, .release = resident_close,
    .unlocked_ioctl = resident_ioctl,
};

static struct miscdevice resident_device = {
    .minor = MISC_DYNAMIC_MINOR, .name = "ara-resident", .fops = &resident_ops,
    .mode = 0600,
};

static int resident_probe(struct platform_device *pdev)
{
    u32 lanes, vlen;
    u64 first, length, hart;
    int result;
    if (of_property_read_u32(pdev->dev.of_node, "pulp,nr-lanes", &lanes) ||
        of_property_read_u32(pdev->dev.of_node, "pulp,vlen-bits", &vlen) ||
        lanes != 4 || vlen != 1024 ||
        of_property_read_u64(pdev->dev.of_node, "pulp,hart-id", &hart) ||
        of_property_read_u64(pdev->dev.of_node, "pulp,ram-base", &first) ||
        of_property_read_u64(pdev->dev.of_node, "pulp,ram-size", &length) ||
        !length || first >= (1ULL << 48) || length > (1ULL << 48) - first ||
        !of_dma_is_coherent(pdev->dev.of_node) ||
        !of_property_read_bool(pdev->dev.of_node, "pulp,firmware-preserves-accelerator"))
        return -ENODEV;
    if (IS_ENABLED(CONFIG_PREEMPT_RT) || IS_ENABLED(CONFIG_RISCV_ISA_V_PREEMPTIVE))
        return -EOPNOTSUPP;
    if (atomic_cmpxchg(&device_bound, 0, 1)) return -EBUSY;
    ram_base = first;
    ram_size = length;
    allowed_hart = hart;
    result = register_die_notifier(&resident_die_notifier);
    if (result) { atomic_set(&device_bound, 0); return result; }
    resident_device.parent = &pdev->dev;
    result = misc_register(&resident_device);
    if (result) {
        unregister_die_notifier(&resident_die_notifier);
        atomic_set(&device_bound, 0);
    } else {
        atomic64_inc(&deployment_epoch);
        WRITE_ONCE(deployment_online, true);
    }
    return result;
}

static void resident_remove(struct platform_device *pdev)
{
    (void)pdev;
    WRITE_ONCE(deployment_online, false);
    misc_deregister(&resident_device);
    mutex_lock(&accelerator_lock);
    unregister_die_notifier(&resident_die_notifier);
    mutex_unlock(&accelerator_lock);
    atomic_set(&device_bound, 0);
}

static const struct of_device_id resident_of_match[] = {
    { .compatible = "pulp,ara-resident-attention-v1" }, {}
};
MODULE_DEVICE_TABLE(of, resident_of_match);

static struct platform_driver resident_driver = {
    .probe = resident_probe, .remove = resident_remove,
    .driver = { .name = "ara-resident", .of_match_table = resident_of_match,
                .suppress_bind_attrs = true },
};
module_platform_driver(resident_driver);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("Bounded, single-hart, kernel-owned Resident Attention groups");
