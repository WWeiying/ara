// SPDX-License-Identifier: GPL-2.0-only
/* One complete group owns the local accelerator; no lease escapes this ioctl. */
#include <linux/cpu.h>
#include <linux/kdebug.h>
#include <linux/ktime.h>
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
#include "buffer_pool.h"
#include "kv_view.h"
#include "sdk/kernel_compute.h"

static DEFINE_MUTEX(accelerator_lock);
static atomic_t device_bound = ATOMIC_INIT(0);
static atomic64_t deployment_epoch = ATOMIC64_INIT(0);
static bool deployment_online;
static DEFINE_PER_CPU(bool, computation_active);
static u64 ram_base, ram_size, allowed_hart;
static struct ara_resident_buffer buffers[6];
static u64 job_sequence;
static bool profile;
module_param(profile, bool, 0444);
MODULE_PARM_DESC(profile, "Collect phase nanoseconds; disabled for primary latency measurements");

struct resident_file {
    u64 epoch;
    struct ara_resident_stats last;
    struct resident_kv_view *views[ARA_RESIDENT_MAX_VIEWS];
};

static u64 profile_time(void)
{
    return profile ? ktime_get_ns() : 0;
}

static void *allocate_buffer(size_t bytes)
{
    return kvmalloc(bytes, GFP_KERNEL);
}

static void release_buffer(const void *p)
{
    kvfree(p);
}

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

    lockdep_assert_held(&accelerator_lock);
    cpus_read_lock();
    /* No other hart may issue an unmediated command to this context. */
    if (num_online_cpus() != 1) {
        cpus_read_unlock();
        return -EOPNOTSUPP;
    }
    if (!READ_ONCE(deployment_online) || epoch != atomic64_read(&deployment_epoch)) {
        result = -ENODEV;
        goto unlock_cpus;
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
unlock_cpus:
    cpus_read_unlock();
    return result;
}

static long run_job(void __user *arg, struct resident_file *file)
{
    struct ara_resident_compute_buffers b = {0};
    struct ara_resident_job job;
    struct ara_resident_sizes sizes;
    struct ara_resident_stats stats = {
        .abi = ARA_RESIDENT_ABI, .bytes = sizeof(stats), .profile_enabled = profile,
    };
    size_t lengths[6];
    u64 begin = profile_time(), stamp;
    long rc = -ENOMEM;

    if (copy_from_user(&job, arg, sizeof(job))) return -EFAULT;
    if (!ara_resident_job_sizes(&job, &sizes)) return -EINVAL;
    if (job.output >= (unsigned long)arg ?
        job.output - (unsigned long)arg < sizeof(job) :
        (unsigned long)arg - job.output < sizes.output) return -EINVAL;
    if (!access_ok(u64_to_user_ptr(job.output), sizes.output)) return -EFAULT;
    b.scratch_bytes = ara_resident_compute_scratch_bytes();
    if (!b.scratch_bytes || b.scratch_bytes > SZ_16K) return -EOVERFLOW;
    if (mutex_lock_interruptible(&accelerator_lock)) return -EINTR;
    if (!READ_ONCE(deployment_online) || file->epoch != atomic64_read(&deployment_epoch)) {
        rc = -ENODEV;
        goto out;
    }
    stats.sequence = ++job_sequence;
    stamp = profile_time();
    lengths[0] = sizes.query; lengths[1] = sizes.key; lengths[2] = sizes.value;
    lengths[3] = sizes.mask; lengths[4] = sizes.output; lengths[5] = b.scratch_bytes;
    for (unsigned i = 0; i < ARRAY_SIZE(buffers); ++i) {
        bool growth = lengths[i] > buffers[i].capacity;
        size_t limit = i == 5 ? SZ_16K : SZ_64K;
        if (!ara_resident_buffer_reserve(&buffers[i], lengths[i], limit,
                                         allocate_buffer, release_buffer)) goto out;
        stats.allocated_buffers += growth;
    }
    b.query = buffers[0].data; b.key = buffers[1].data; b.value = buffers[2].data;
    b.mask = buffers[3].data; b.output = buffers[4].data; b.scratch = buffers[5].data;
    memset(b.output, 0, sizes.output);
    memset(b.scratch, 0, b.scratch_bytes);
    stats.buffer_ns = profile_time() - stamp;
    stamp = profile_time();
    if (copy_from_user(b.query, u64_to_user_ptr(job.query), sizes.query) ||
        copy_from_user(b.key, u64_to_user_ptr(job.key), sizes.key) ||
        copy_from_user(b.value, u64_to_user_ptr(job.value), sizes.value) ||
        copy_from_user(b.mask, u64_to_user_ptr(job.mask), sizes.mask)) {
        rc = -EFAULT;
        goto out;
    }
    stats.input_copy_ns = profile_time() - stamp;
    stats.copied_input_bytes = sizes.query + sizes.key + sizes.value + sizes.mask;
    b.heads = job.heads;
    b.dimension = job.dimension;
    b.tokens = job.tokens;
    b.scale_bits = job.scale_bits;
    stamp = profile_time();
    if (!accelerator_ram(b.query, sizes.query) || !accelerator_ram(b.key, sizes.key) ||
        !accelerator_ram(b.value, sizes.value) || !accelerator_ram(b.mask, sizes.mask) ||
        !accelerator_ram(b.output, sizes.output) || !accelerator_ram(b.scratch, b.scratch_bytes)) {
        rc = -EOPNOTSUPP;
        goto out;
    }
    stats.address_check_ns = profile_time() - stamp;
    stamp = profile_time();
    rc = execute_group(&b, file->epoch);
    stats.execute_ns = profile_time() - stamp;
    /* No publication on computation failure; output stays kernel-private. */
    if (rc) {
        if (b.started) rc = -EIO;
        goto out;
    }
    if (!b.started || !b.resident_used || b.flags & ~31U) { rc = -EIO; goto out; }
    job.fflags = b.flags;
    stamp = profile_time();
    /* A failed user copy is terminal, never permission to replay this ioctl. */
    if (copy_to_user(u64_to_user_ptr(job.output), b.output, sizes.output) ||
        copy_to_user(arg, &job, sizeof(job))) rc = -EFAULT;
    stats.output_copy_ns = profile_time() - stamp;
out:
    stats.status = rc;
    stats.total_ns = profile_time() - begin;
    file->last = stats;
    mutex_unlock(&accelerator_lock);
    return rc;
}

static struct resident_kv_view *find_view(struct resident_file *file, u64 handle)
{
    for (unsigned i = 0; i < ARRAY_SIZE(file->views); ++i)
        if (file->views[i] && file->views[i]->layout.handle == handle) return file->views[i];
    return NULL;
}

static long register_view(void __user *arg, struct resident_file *file)
{
    struct ara_resident_kv_view layout;
    struct ara_resident_view_sizes sizes;
    struct resident_kv_view *v = NULL;
    unsigned slot;
    long rc;
    if (copy_from_user(&layout, arg, sizeof(layout))) return -EFAULT;
    if (!ara_resident_check_view(&layout, &sizes) ||
        ara_resident_ranges_overlap((unsigned long)arg, sizeof(layout), layout.key, sizes.key) ||
        ara_resident_ranges_overlap((unsigned long)arg, sizeof(layout), layout.value, sizes.value)) return -EINVAL;
    if (mutex_lock_interruptible(&accelerator_lock)) return -EINTR;
    rc = -ENODEV;
    if (!READ_ONCE(deployment_online) || file->epoch != atomic64_read(&deployment_epoch)) goto out;
    for (slot = 0; slot < ARRAY_SIZE(file->views) && file->views[slot]; ++slot) {}
    rc = -ENOSPC;
    if (slot == ARRAY_SIZE(file->views)) goto out;
    rc = -EOVERFLOW;
    if (resident_next_handle == U64_MAX) goto out;
    v = kzalloc(sizeof(*v), GFP_KERNEL);
    rc = -ENOMEM;
    if (!v) goto out;
    v->layout = layout;
    v->sizes = sizes;
    rc = resident_pin_map(&v->key, layout.key, sizes.key, ram_base, ram_size);
    if (rc) goto out;
    rc = resident_pin_map(&v->value, layout.value, sizes.value, ram_base, ram_size);
    if (rc) goto out;
    if (!resident_view_valid(v)) { rc = -ESTALE; goto out; }
    v->layout.handle = ++resident_next_handle;
    if (copy_to_user(arg, &v->layout, sizeof(layout))) { rc = -EFAULT; goto out; }
    file->views[slot] = v;
    v = NULL;
    rc = 0;
out:
    resident_free_view(v);
    mutex_unlock(&accelerator_lock);
    return rc;
}

static long release_view(void __user *arg, struct resident_file *file)
{
    struct ara_resident_view_release r;
    long rc = -ENOENT;
    if (copy_from_user(&r, arg, sizeof(r))) return -EFAULT;
    if (r.abi != ARA_RESIDENT_VIEW_ABI || r.bytes != sizeof(r) || !r.handle ||
        r.reserved[0] || r.reserved[1]) return -EINVAL;
    if (mutex_lock_interruptible(&accelerator_lock)) return -EINTR;
    for (unsigned i = 0; i < ARRAY_SIZE(file->views); ++i) {
        if (file->views[i] && file->views[i]->layout.handle == r.handle) {
            resident_free_view(file->views[i]);
            file->views[i] = NULL;
            rc = 0;
            break;
        }
    }
    mutex_unlock(&accelerator_lock);
    return rc;
}

static int execute_batch(struct ara_resident_batch *job,
        const struct ara_resident_batch_group *groups, struct resident_kv_view *v,
        struct ara_resident_compute_buffers *base, u64 epoch)
{
    unsigned long irq_flags;
    unsigned rows = 0;
    int rc = -EOPNOTSUPP;
    lockdep_assert_held(&accelerator_lock);
    cpus_read_lock();
    if (num_online_cpus() != 1) goto unlock_cpus;
    if (!READ_ONCE(deployment_online) || epoch != atomic64_read(&deployment_epoch)) {
        rc = -ENODEV;
        goto unlock_cpus;
    }
    preempt_disable();
    if (cpuid_to_hartid_map(smp_processor_id()) != allowed_hart ||
        !may_use_simd() || !kernel_fpu_available()) goto unlock_preempt;
    this_cpu_write(computation_active, true);
    kernel_fpu_begin();
    kernel_vector_begin();
    for (unsigned i = 0; i < job->count; ++i) {
        struct ara_resident_compute_buffers b = *base;
        b.query = (char *)base->query + rows * job->dimension * 2u;
        b.output = (char *)base->output + rows * job->dimension * 4u;
        b.key = (char *)v->key.data + groups[i].kv_head * v->layout.key_head_stride;
        b.value = (char *)v->value.data + groups[i].kv_head * v->layout.value_head_stride;
        b.key_token_stride = v->layout.key_token_stride;
        b.value_token_stride = v->layout.value_token_stride;
        b.heads = groups[i].heads;
        b.flags = ARA_RESIDENT_COMPUTE_REQUIRED_FLAGS;
        b.started = b.resident_used = 0;
        local_irq_save(irq_flags);
        /* Invalidation is permanent. Check after entering the single-CPU
         * non-preemptible region; no user/MM update can race the computation.
         */
        if (!resident_view_valid(v)) {
            rc = -ESTALE;
            local_irq_restore(irq_flags);
            break;
        }
        rc = ara_resident_compute(&b);
        asm volatile("csrr zero, vl\nfence rw,rw" ::: "memory");
        if (rc && b.started)
            panic("Resident batch failed after execution: hardware reset required");
        local_irq_restore(irq_flags);
        if (rc) break;
        if (!b.started || !b.resident_used || b.flags & ~31U) { rc = -EIO; break; }
        job->fflags |= b.flags;
        ++job->completed;
        rows += b.heads;
        /* IRQ latency remains bounded by one group, not the whole batch. */
    }
    kernel_vector_end();
    kernel_fpu_end();
    this_cpu_write(computation_active, false);
unlock_preempt:
    preempt_enable();
unlock_cpus:
    cpus_read_unlock();
    return rc && job->completed ? -EIO : rc;
}

static long run_batch(void __user *arg, struct resident_file *file)
{
    struct ara_resident_batch job;
    struct ara_resident_batch_group groups[ARA_RESIDENT_MAX_BATCH];
    struct ara_resident_batch_sizes sizes;
    struct ara_resident_compute_buffers b = {0};
    struct resident_kv_view *v;
    struct ara_resident_stats stats = {
        .abi = ARA_RESIDENT_ABI, .bytes = sizeof(stats), .profile_enabled = profile,
    };
    const unsigned indices[] = {0, 3, 4, 5};
    size_t lengths[4];
    u64 begin = profile_time(), stamp;
    long rc = -EINVAL;
    if (copy_from_user(&job, arg, sizeof(job))) return -EFAULT;
    if (!ara_resident_batch_header(&job)) return -EINVAL;
    if (copy_from_user(groups, u64_to_user_ptr(job.groups), job.count * sizeof(groups[0]))) return -EFAULT;
    if (mutex_lock_interruptible(&accelerator_lock)) return -EINTR;
    if (!READ_ONCE(deployment_online) || file->epoch != atomic64_read(&deployment_epoch)) {
        rc = -ENODEV; goto out;
    }
    stats.sequence = ++job_sequence;
    v = find_view(file, job.handle);
    if (!resident_view_valid(v)) { rc = -ESTALE; goto out; }
    if (job.dimension != v->layout.dimension || job.tokens > v->layout.capacity ||
        !ara_resident_check_batch(&job, groups, v->layout.kv_heads, &sizes)) goto out;
    /* The returned descriptor is writable output too, even though all payload
     * reads have completed before copyout. Never publish it into an input span.
     */
    if (ara_resident_ranges_overlap((unsigned long)arg, sizeof(job), job.groups, sizes.groups) ||
        ara_resident_ranges_overlap((unsigned long)arg, sizeof(job), job.query, sizes.query) ||
        ara_resident_ranges_overlap((unsigned long)arg, sizeof(job), job.mask, sizes.mask) ||
        ara_resident_ranges_overlap((unsigned long)arg, sizeof(job), v->layout.key, v->sizes.key) ||
        ara_resident_ranges_overlap((unsigned long)arg, sizeof(job), v->layout.value, v->sizes.value)) goto out;
    if (ara_resident_ranges_overlap(job.output, sizes.output, (unsigned long)arg, sizeof(job)) ||
        ara_resident_ranges_overlap(job.output, sizes.output, job.groups, sizes.groups) ||
        ara_resident_ranges_overlap(job.output, sizes.output, job.query, sizes.query) ||
        ara_resident_ranges_overlap(job.output, sizes.output, job.mask, sizes.mask) ||
        ara_resident_ranges_overlap(job.output, sizes.output, v->layout.key, v->sizes.key) ||
        ara_resident_ranges_overlap(job.output, sizes.output, v->layout.value, v->sizes.value)) goto out;
    if (!access_ok(u64_to_user_ptr(job.output), sizes.output)) { rc = -EFAULT; goto out; }
    b.scratch_bytes = ara_resident_compute_scratch_bytes();
    if (!b.scratch_bytes || b.scratch_bytes > SZ_16K) { rc = -EOVERFLOW; goto out; }
    lengths[0] = sizes.query; lengths[1] = sizes.mask;
    lengths[2] = sizes.output; lengths[3] = b.scratch_bytes;
    rc = -ENOMEM;
    stamp = profile_time();
    for (unsigned i = 0; i < ARRAY_SIZE(indices); ++i) {
        struct ara_resident_buffer *buffer = &buffers[indices[i]];
        bool growth = lengths[i] > buffer->capacity;
        if (!ara_resident_buffer_reserve(buffer, lengths[i], i == 3 ? SZ_16K : SZ_64K,
                                        allocate_buffer, release_buffer)) goto out;
        stats.allocated_buffers += growth;
    }
    b.query = buffers[0].data; b.mask = buffers[3].data;
    b.output = buffers[4].data; b.scratch = buffers[5].data;
    memset(b.output, 0, sizes.output);
    memset(b.scratch, 0, b.scratch_bytes);
    stats.buffer_ns = profile_time() - stamp;
    stamp = profile_time();
    if (copy_from_user(b.query, u64_to_user_ptr(job.query), sizes.query) ||
        copy_from_user(b.mask, u64_to_user_ptr(job.mask), sizes.mask)) { rc = -EFAULT; goto out; }
    stats.copied_input_bytes = sizes.query + sizes.mask;
    stats.input_copy_ns = profile_time() - stamp;
    stamp = profile_time();
    if (!accelerator_ram(b.query, sizes.query) || !accelerator_ram(b.mask, sizes.mask) ||
        !accelerator_ram(b.output, sizes.output) || !accelerator_ram(b.scratch, b.scratch_bytes)) {
        rc = -EOPNOTSUPP; goto out;
    }
    stats.address_check_ns = profile_time() - stamp;
    b.dimension = job.dimension; b.tokens = job.tokens; b.scale_bits = job.scale_bits;
    stamp = profile_time();
    rc = execute_batch(&job, groups, v, &b, file->epoch);
    stats.execute_ns = profile_time() - stamp;
    if (rc) goto out;
    if (job.completed != job.count || job.fflags & ~31U) { rc = -EIO; goto out; }
    stamp = profile_time();
    if (copy_to_user(u64_to_user_ptr(job.output), b.output, sizes.output) ||
        copy_to_user(arg, &job, sizeof(job))) rc = -EFAULT;
    stats.output_copy_ns = profile_time() - stamp;
out:
    stats.status = rc;
    stats.total_ns = profile_time() - begin;
    file->last = stats;
    mutex_unlock(&accelerator_lock);
    return rc;
}

static long resident_ioctl(struct file *file, unsigned int command, unsigned long arg)
{
    struct resident_file *state = file->private_data;
    const u64 epoch = state->epoch;
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
        return run_job((void __user *)arg, state);
    case ARA_RESIDENT_VIEW_CAPS: {
        const struct ara_resident_view_caps caps = {
            .abi = ARA_RESIDENT_VIEW_ABI, .bytes = sizeof(caps),
            .max_views = ARA_RESIDENT_MAX_VIEWS, .max_groups = ARA_RESIDENT_MAX_BATCH,
            .max_kv_heads = ARA_RESIDENT_MAX_KV_HEADS, .max_view_bytes = ARA_RESIDENT_MAX_VIEW_BYTES,
            .pin_limit_bytes = ARA_RESIDENT_PIN_LIMIT_BYTES,
        };
        if (!IS_ENABLED(CONFIG_MMU_NOTIFIER)) return -EOPNOTSUPP;
        return copy_to_user((void __user *)arg, &caps, sizeof(caps)) ? -EFAULT : 0;
    }
    case ARA_RESIDENT_REGISTER_KV:
        return register_view((void __user *)arg, state);
    case ARA_RESIDENT_RELEASE_KV:
        return release_view((void __user *)arg, state);
    case ARA_RESIDENT_EXECUTE_BATCH:
        return run_batch((void __user *)arg, state);
    case ARA_RESIDENT_GET_STATS: {
        struct ara_resident_stats stats;
        mutex_lock(&accelerator_lock);
        stats = state->last;
        mutex_unlock(&accelerator_lock);
        return copy_to_user((void __user *)arg, &stats, sizeof(stats)) ? -EFAULT : 0;
    }
    default:
        return -ENOTTY;
    }
}

static int resident_open(struct inode *inode, struct file *file)
{
    struct resident_file *state;
    (void)inode;
    if (!READ_ONCE(deployment_online)) return -ENODEV;
    state = kzalloc(sizeof(*state), GFP_KERNEL);
    if (!state) return -ENOMEM;
    state->epoch = atomic64_read(&deployment_epoch);
    file->private_data = state;
    return 0;
}

static int resident_close(struct inode *inode, struct file *file)
{
    struct resident_file *state = file->private_data;
    (void)inode;
    mutex_lock(&accelerator_lock);
    for (unsigned i = 0; i < ARRAY_SIZE(state->views); ++i) resident_free_view(state->views[i]);
    mutex_unlock(&accelerator_lock);
    kfree(state);
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
    for (unsigned i = 0; i < ARRAY_SIZE(buffers); ++i) {
        kvfree(buffers[i].allocation);
        buffers[i] = (struct ara_resident_buffer){0};
    }
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
