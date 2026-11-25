/* SPDX-License-Identifier: Apache-2.0 */
/* Targeted v2 successor: metadata-output aliases and prefaulted private KV.
 * Independent QEMU/Linux successor. Reuse only scalar syscall/logging helpers;
 * --gc-sections drops the old main and its client/CSR wrapper references. */
#define smoke_main inherited_smoke_main
#include "../linux_smoke/init_v2.c"
#undef smoke_main
#include "view_uapi.h"
#include <linux/mman.h>
#include <stddef.h>

_Static_assert(sizeof(struct ara_resident_kv_view) == 96, "view ABI");
_Static_assert(sizeof(struct ara_resident_batch) == 104, "batch ABI");
_Static_assert(sizeof(struct ara_resident_view_release) == 32, "release ABI");

asm(".section .text.views_start,\"ax\",@progbits\n"
    ".option push\n.option norelax\n.globl _start\n.type _start,@function\n"
    "_start:\nla gp, __global_pointer$\nandi sp, sp, -16\ncall smoke_main\n"
    "1: j 1b\n.size _start, .-_start\n.option pop\n.previous\n");

enum { MAP_BYTES = 8192, DIM = 96, TOKENS = 17, KV_HEADS = 2 };
static uint16_t view_query[16 * 128] __attribute__((aligned(64)));
static uint16_t view_mask[256] __attribute__((aligned(64)));
static unsigned char view_output[16 * 128 * 4] __attribute__((aligned(64)));
static struct ara_resident_batch_group groups[16] __attribute__((aligned(64)));
static unsigned info_rounds, guest_cpus;

/* GCC may lower aggregate initializers/copies to these freestanding routines. */
void *memset(void *dest, int value, size_t size)
{
    unsigned char *p = dest;
    for (size_t i = 0; i < size; ++i) p[i] = (unsigned char)value;
    return dest;
}

void *memcpy(void *dest, const void *source, size_t size)
{
    unsigned char *d = dest;
    const unsigned char *s = source;
    for (size_t i = 0; i < size; ++i) d[i] = s[i];
    return dest;
}

static void clear_bytes(void *p, unsigned size)
{
    unsigned char *bytes = p;
    for (unsigned i = 0; i < size; ++i) bytes[i] = 0;
}

static unsigned different(const void *a, const void *b, unsigned size)
{
    const unsigned char *x = a, *y = b;
    unsigned diff = 0;
    for (unsigned i = 0; i < size; ++i) diff |= x[i] ^ y[i];
    return diff;
}

static void *map_kv(void *address)
{
    long p = call(__NR_mmap, (long)address, MAP_BYTES, PROT_READ | PROT_WRITE,
                  MAP_SHARED | MAP_ANONYMOUS | (address ? MAP_FIXED_NOREPLACE : 0), -1, 0);
    check("mmap_shared", p > 0, 1);
    if (p < 0) return 0;
    if (address) check("remap_exact_address", p, (long)address);
    clear_bytes((void *)p, MAP_BYTES); /* Fault in writable pages before read-only GUP. */
    return (void *)p;
}

static struct ara_resident_kv_view descriptor(void *k, void *v)
{
    struct ara_resident_kv_view d = {0};
    d.abi = 1; d.bytes = sizeof(d); d.dimension = DIM;
    d.kv_heads = KV_HEADS; d.capacity = TOKENS;
    d.key_token_stride = DIM * 2; d.key_head_stride = TOKENS * DIM * 2;
    d.value_token_stride = KV_HEADS * DIM * 2; d.value_head_stride = DIM * 2;
    d.key = (uintptr_t)k; d.value = (uintptr_t)v;
    return d;
}

static long register_kv(int fd, struct ara_resident_kv_view *v, const char *name)
{
    struct ara_resident_kv_view before = *v;
    long rc = ioctl(fd, ARA_RESIDENT_REGISTER_KV, v);
    check(name, rc, 0);
    if (!rc) {
        check("handle_nonzero", v->handle != 0, 1);
        before.handle = v->handle;
        check("registration_only_returns_handle", different(&before, v, sizeof(*v)), 0);
    }
    return rc;
}

static long release_kv(int fd, __u64 handle)
{
    struct ara_resident_view_release r = {0};
    r.abi = 1; r.bytes = sizeof(r); r.handle = handle;
    return ioctl(fd, ARA_RESIDENT_RELEASE_KV, &r);
}

static struct ara_resident_batch batch(__u64 handle)
{
    struct ara_resident_batch b = {0};
    b.abi = 1; b.bytes = sizeof(b); b.count = 1; b.dimension = DIM; b.tokens = TOKENS;
    b.scale_bits = 0x3f000000; b.handle = handle;
    b.groups = (uintptr_t)groups; b.query = (uintptr_t)view_query;
    b.mask = (uintptr_t)view_mask; b.output = (uintptr_t)view_output;
    return b;
}

static void batch_result(int fd, struct ara_resident_batch *b, const char *name,
                         long expected, int finite_discovery)
{
    struct ara_resident_batch before = *b;
    for (unsigned i = 0; i < sizeof(view_output); ++i) view_output[i] = 0xa5;
    check(name, ioctl(fd, ARA_RESIDENT_EXECUTE_BATCH, b), expected);
    check("batch_descriptor_unpublished", different(b, &before, sizeof(*b)), 0);
    unsigned changed = 0;
    for (unsigned i = 0; i < sizeof(view_output); ++i) changed |= view_output[i] ^ 0xa5;
    check("batch_output_unpublished", changed, 0);
    if (finite_discovery && guest_cpus == 1) ++info_rounds;
}

static void invalid_requests(int fd)
{
    struct ara_resident_kv_view v = {0};
    struct ara_resident_batch b = {0};
    struct ara_resident_view_release r = {0};
    check("register_zero_descriptor", ioctl(fd, ARA_RESIDENT_REGISTER_KV, &v), -22);
    check("batch_zero_descriptor", ioctl(fd, ARA_RESIDENT_EXECUTE_BATCH, &b), -22);
    check("release_zero_descriptor", ioctl(fd, ARA_RESIDENT_RELEASE_KV, &r), -22);
    check("caps_bad_pointer", ioctl(fd, ARA_RESIDENT_VIEW_CAPS, (void *)1), -14);
    check("register_bad_pointer", ioctl(fd, ARA_RESIDENT_REGISTER_KV, (void *)1), -14);
    check("batch_bad_pointer", ioctl(fd, ARA_RESIDENT_EXECUTE_BATCH, (void *)1), -14);
    check("release_bad_pointer", ioctl(fd, ARA_RESIDENT_RELEASE_KV, (void *)1), -14);
}

static void live_inputs(int fd, struct ara_resident_kv_view *v)
{
    struct ara_resident_batch b = batch(v->handle);
    struct ara_resident_stats s = {0};
    volatile uint16_t *k = (volatile uint16_t *)(uintptr_t)v->key;
    volatile uint16_t *val = (volatile uint16_t *)(uintptr_t)v->value;
    unsigned ki = (v->key_head_stride + (TOKENS - 1) * v->key_token_stride) / 2 + DIM - 1;
    unsigned vi = (v->value_head_stride + (TOKENS - 1) * v->value_token_stride) / 2 + DIM - 1;
    batch_result(fd, &b, "finite_capability_decline", -EOPNOTSUPP, 1);
    check("stats_after_finite", ioctl(fd, ARA_RESIDENT_GET_STATS, &s), 0);
    check("stats_only_copies_query_mask", s.copied_input_bytes, DIM * 2 + TOKENS * 2);
    check("stats_decline_status", s.status, -EOPNOTSUPP);
    k[ki] = 0x3c00; val[vi] = 0x4000; view_query[DIM - 1] = 0x3800;
    batch_result(fd, &b, "live_finite_update_decline", -EOPNOTSUPP, 1);
    k[ki] = 0x7e00;
    batch_result(fd, &b, "live_key_nan_before_info", -EOPNOTSUPP, 0);
    k[ki] = 0x3c00;
    batch_result(fd, &b, "live_key_restored_info", -EOPNOTSUPP, 1);
    val[vi] = 0x7c00;
    batch_result(fd, &b, "live_value_inf_before_info", -EOPNOTSUPP, 0);
    val[vi] = 0x4000;
    batch_result(fd, &b, "live_value_restored_info", -EOPNOTSUPP, 1);
    view_query[DIM - 1] = 0x7e00;
    batch_result(fd, &b, "live_query_nan_before_info", -EOPNOTSUPP, 0);
    view_query[DIM - 1] = 0x3800;
    view_mask[TOKENS - 1] = 0x7e00;
    batch_result(fd, &b, "live_mask_nan_before_info", -EOPNOTSUPP, 0);
    view_mask[TOKENS - 1] = 0;
    batch_result(fd, &b, "live_inputs_restored_info", -EOPNOTSUPP, 1);
    b.count = 16;
    batch_result(fd, &b, "sixteen_groups_decline_first", -EOPNOTSUPP, 1);
    b.count = 17;
    batch_result(fd, &b, "seventeen_groups_rejected", -22, 0);
    b = batch(v->handle); b.tokens = TOKENS + 1;
    batch_result(fd, &b, "tokens_beyond_registered_capacity", -22, 0);
    b = batch(v->handle); b.dimension = 128;
    batch_result(fd, &b, "dimension_mismatch", -22, 0);
    b = batch(v->handle); groups[0].kv_head = KV_HEADS;
    batch_result(fd, &b, "group_kv_out_of_range", -22, 0);
    groups[0].kv_head = 1;
    const __u64 aliases[] = {(uintptr_t)&b, (uintptr_t)groups, b.query, b.mask, v->key, v->value};
    for (unsigned i = 0; i < sizeof(aliases) / sizeof(aliases[0]); ++i) {
        b.output = aliases[i];
        batch_result(fd, &b, "output_alias_rejected", -22, 0);
    }
}

static void fork_wrong_mm(int fd, __u64 handle)
{
    /* MAP_SHARED avoids parent COW invalidation, isolating the child-mm gate. */
    long pid = call(__NR_clone, 17 /* SIGCHLD, fork semantics */, 0, 0, 0, 0, 0);
    if (pid == 0) {
        unsigned old_errors = errors;
        struct ara_resident_batch b = batch(handle);
        batch_result(fd, &b, "fork_inherited_fd_wrong_mm", -116, 0);
        check("child_close_inherited_fd", call(__NR_close, fd, 0, 0, 0, 0, 0), 0);
        call(__NR_exit_group, errors != old_errors, 0, 0, 0, 0, 0);
        for (;;) asm volatile("" ::: "memory");
    }
    if (pid < 0) { check("fork_created_child", 0, 1); return; }
    int status = -1;
    /* The inherited logger uses multiple writes per line. Do not interleave
     * parent output with the child's checks, including on the two-CPU guest. */
    long waited = call(__NR_wait4, pid, (long)&status, 0, 0, 0, 0);
    check("fork_created_child", pid > 0, 1);
    check("wait_child", waited, pid);
    check("child_exit_status", status, 0);
    struct ara_resident_batch b = batch(handle);
    batch_result(fd, &b, "parent_handle_survives_shared_fork", -EOPNOTSUPP, 1);
}

static void invalidate_mapping(int fd, void **k, void **v, int value_axis, int unmap)
{
    struct ara_resident_kv_view d = descriptor(*k, *v);
    if (register_kv(fd, &d, "register_for_invalidation")) return;
    struct ara_resident_batch b = batch(d.handle);
    void **target = value_axis ? v : k;
    void *old = *target;
    if (unmap) {
        long rc = call(__NR_munmap, (long)old, MAP_BYTES, 0, 0, 0, 0);
        check("unmap_registered_storage", rc, 0);
        if (!rc) *target = 0;
    } else {
        check("mprotect_registered_none", call(__NR_mprotect, (long)old, MAP_BYTES, PROT_NONE, 0, 0, 0), 0);
    }
    batch_result(fd, &b, value_axis ? "value_mapping_stale" : "key_mapping_stale", -116, 0);
    if (unmap && !*target) *target = map_kv(old);
    else if (!unmap)
        check("mprotect_restore_rw", call(__NR_mprotect, (long)old, MAP_BYTES,
                                          PROT_READ | PROT_WRITE, 0, 0, 0), 0);
    batch_result(fd, &b, "restored_address_still_stale", -116, 0);
    check("release_invalidated_handle", release_kv(fd, d.handle), 0);
    check("released_handle_missing", release_kv(fd, d.handle), -2);
    if (*k && *v) {
        struct ara_resident_kv_view fresh = descriptor(*k, *v);
        if (!register_kv(fd, &fresh, "register_fresh_after_invalidation")) {
            check("new_handle_not_recycled", fresh.handle != d.handle, 1);
            b = batch(fresh.handle);
            batch_result(fd, &b, "fresh_mapping_cap_decline", -EOPNOTSUPP, 1);
            check("release_fresh_mapping", release_kv(fd, fresh.handle), 0);
        }
    }
}


/* These buffers are test-owned storage, not extra registered payloads. */
static unsigned char metadata_scratch[256] __attribute__((aligned(64)));
static unsigned char alias_original[MAP_BYTES], alias_expected[MAP_BYTES];

static void metadata_alias_case(int fd, const struct ara_resident_kv_view *v,
        void *storage, unsigned bytes, unsigned offset, const char *name, int group_alias)
{
    struct ara_resident_batch b = batch(v->handle);
    unsigned char *arg = (unsigned char *)storage + offset;
    memcpy(alias_original, storage, bytes);
    if (group_alias) {
        /* An unaligned descriptor ends one byte into an aligned, valid group.
         * That shared byte is both reserved[2]'s last zero and kv_head's low zero.
         * A full descriptor/group alias would make heads or reserved invalid and
         * could falsely pass even without the metadata-overlap guard. */
        struct ara_resident_batch_group g = {0, 1, 0};
        b.groups = (uintptr_t)(metadata_scratch + 104);
        memcpy((void *)(uintptr_t)b.groups, &g, sizeof(g));
    }
    memcpy(arg, &b, sizeof(b));
    if (group_alias) {
        struct ara_resident_batch_group g;
        memcpy(&g, (const void *)(uintptr_t)b.groups, sizeof(g));
        check("metadata_group_independently_valid",
              g.kv_head == 0 && g.heads == 1 && g.reserved == 0, 1);
        check("metadata_group_overlap_one_byte",
              (uintptr_t)arg + sizeof(b) - b.groups, 1);
    }
    memcpy(alias_expected, storage, bytes);
    for (unsigned i = 0; i < sizeof(view_output); ++i) view_output[i] = 0xa5;
    /* Use byte copies: the group-alias argument deliberately has no C alignment. */
    check(name, ioctl(fd, ARA_RESIDENT_EXECUTE_BATCH, arg), -22);
    check("metadata_alias_descriptor_unpublished", different(arg, &b, sizeof(b)), 0);
    check("metadata_alias_input_unchanged", different(storage, alias_expected, bytes), 0);
    unsigned changed = 0;
    for (unsigned i = 0; i < sizeof(view_output); ++i) changed |= view_output[i] ^ 0xa5;
    check("metadata_alias_output_unpublished", changed, 0);
    memcpy(storage, alias_original, bytes);
}

static void metadata_aliases(int fd, const struct ara_resident_kv_view *v)
{
    struct ara_resident_batch b = batch(v->handle);
    batch_result(fd, &b, "metadata_disjoint_control_before", -EOPNOTSUPP, 1);
    /* K/V aliases occupy head zero; the first batch group reads head one. */
    metadata_alias_case(fd, v, (void *)(uintptr_t)v->key, MAP_BYTES, 0,
                        "metadata_alias_key", 0);
    metadata_alias_case(fd, v, (void *)(uintptr_t)v->value, MAP_BYTES, 0,
                        "metadata_alias_value", 0);
    metadata_alias_case(fd, v, view_query, sizeof(view_query), 0,
                        "metadata_alias_query", 0);
    metadata_alias_case(fd, v, view_mask, sizeof(view_mask), 0,
                        "metadata_alias_mask", 0);
    metadata_alias_case(fd, v, metadata_scratch, sizeof(metadata_scratch), 1,
                        "metadata_alias_groups", 1);
    batch_result(fd, &b, "metadata_disjoint_control_after", -EOPNOTSUPP, 1);
}

static void *map_private_prefaulted(void)
{
    long p = call(__NR_mmap, 0, MAP_BYTES, PROT_READ | PROT_WRITE,
                  MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    check("private_mmap_writable", p > 0, 1);
    if (p < 0) return 0;
    /* Model GGML KVbuffer_clear: write every byte before registering read pins. */
    volatile unsigned char *bytes = (volatile unsigned char *)p;
    for (unsigned i = 0; i < MAP_BYTES; ++i) bytes[i] = 0;
    return (void *)p;
}

static void private_lifecycle(int fd)
{
    void *k = map_private_prefaulted(), *v = map_private_prefaulted();
    if (!k || !v) goto cleanup;
    struct ara_resident_kv_view d = descriptor(k, v);
    if (register_kv(fd, &d, "private_prefaulted_register")) goto cleanup;
    struct ara_resident_batch b = batch(d.handle);
    batch_result(fd, &b, "private_finite_capability_decline", -EOPNOTSUPP, 1);
    volatile uint16_t *key_data = k, *value_data = v;
    unsigned ki = (d.key_head_stride + (TOKENS - 1) * d.key_token_stride) / 2 + DIM - 1;
    unsigned vi = (d.value_head_stride + (TOKENS - 1) * d.value_token_stride) / 2 + DIM - 1;
    key_data[ki] = 0x3c00; value_data[vi] = 0x4000;
    batch_result(fd, &b, "private_live_update_decline", -EOPNOTSUPP, 1);
    key_data[ki] = 0x7e00;
    batch_result(fd, &b, "private_live_nan_before_info", -EOPNOTSUPP, 0);
    key_data[ki] = 0x3c00;
    batch_result(fd, &b, "private_live_restored_info", -EOPNOTSUPP, 1);
    check("private_mprotect_none", call(__NR_mprotect, (long)k, MAP_BYTES, PROT_NONE, 0, 0, 0), 0);
    batch_result(fd, &b, "private_protection_stale", -116, 0);
    check("private_mprotect_restore", call(__NR_mprotect, (long)k, MAP_BYTES,
                                          PROT_READ | PROT_WRITE, 0, 0, 0), 0);
    batch_result(fd, &b, "private_protection_sticky_stale", -116, 0);
    check("private_release_invalidated", release_kv(fd, d.handle), 0);
    batch_result(fd, &b, "private_released_stale", -116, 0);
    check("private_release_twice_missing", release_kv(fd, d.handle), -2);
    __u64 previous = d.handle;
    d = descriptor(k, v);
    if (register_kv(fd, &d, "private_reregister_restored")) goto cleanup;
    check("private_new_handle_identity", d.handle != previous, 1);
    b = batch(d.handle);
    batch_result(fd, &b, "private_reregister_capability_decline", -EOPNOTSUPP, 1);
    long rc = call(__NR_munmap, (long)v, MAP_BYTES, 0, 0, 0, 0);
    check("private_unmap_value", rc, 0);
    if (!rc) v = 0;
    batch_result(fd, &b, "private_unmapped_stale", -116, 0);
    check("private_release_unmapped", release_kv(fd, d.handle), 0);
cleanup:
    if (k) check("private_cleanup_key", call(__NR_munmap, (long)k, MAP_BYTES, 0, 0, 0, 0), 0);
    if (v) check("private_cleanup_value", call(__NR_munmap, (long)v, MAP_BYTES, 0, 0, 0, 0), 0);
}

static void handle_limits(int fd, void *k, void *v)
{
    __u64 handles[32] = {0};
    unsigned n = 0;
    for (; n < 32; ++n) {
        struct ara_resident_kv_view d = descriptor(k, v);
        if (register_kv(fd, &d, "fill_handle_table")) break;
        handles[n] = d.handle;
    }
    if (n == 32) {
        struct ara_resident_kv_view d = descriptor(k, v);
        check("handle_limit_33", ioctl(fd, ARA_RESIDENT_REGISTER_KV, &d), -28);
        check("failed_register_no_handle", d.handle, 0);
        check("release_table_slot", release_kv(fd, handles[15]), 0);
        struct ara_resident_batch b = batch(handles[15]);
        batch_result(fd, &b, "released_handle_stale", -116, 0);
        if (!register_kv(fd, &d, "reuse_free_table_slot")) {
            check("slot_new_identity", d.handle != handles[15], 1);
            handles[15] = d.handle;
        } else handles[15] = 0;
    }
    for (unsigned i = 0; i < n; ++i)
        if (handles[i]) check("release_table_handle", release_kv(fd, handles[i]), 0);
}

void smoke_main(void)
{
    long fd = -1, module_fd = -1, rc;
    void *k = 0, *v = 0;
    int loaded = 0;
    guest_cpus = 1;
    put("RESIDENT_VIEWS_V2_LINUX_BEGIN\n");
    check("mount_proc", call(__NR_mount, (long)"proc", (long)"/proc", (long)"proc", 0, 0, 0), 0);
    check("mount_sys", call(__NR_mount, (long)"sysfs", (long)"/sys", (long)"sysfs", 0, 0, 0), 0);
    if (read_file("/proc/cmdline") > 0 && contains(text, "resident_views_cpus=2")) guest_cpus = 2;
    if (read_file("/sys/devices/system/cpu/online") <= 0) { check("cpu_online_read", -1, 0); goto finish; }
    check("online_exact", equal(text, guest_cpus == 1 ? "0\n" : "0-1\n"), 1);
    module_fd = call(__NR_openat, AT_FDCWD, (long)"/ara_resident.ko", 0, 0, 0, 0);
    check("module_open", module_fd >= 0, 1);
    if (module_fd < 0) goto finish;
    rc = call(__NR_finit_module, module_fd, (long)"", 0, 0, 0, 0);
    check("finit_module", rc, 0);
    if (rc) goto finish;
    loaded = 1;
    rc = make_device(); check("mknod", rc, 0);
    if (rc) goto finish;
    fd = call(__NR_openat, AT_FDCWD, (long)"/dev/ara-resident", O_RDWR, 0, 0, 0);
    check("device_open", fd >= 0, 1);
    if (fd < 0) goto finish;
    struct ara_resident_view_caps caps;
    for (unsigned i = 0; i < sizeof(caps); ++i) ((unsigned char *)&caps)[i] = 0xa5;
    check("view_caps", ioctl(fd, ARA_RESIDENT_VIEW_CAPS, &caps), 0);
    check("caps_abi_size", caps.abi == 1 && caps.bytes == sizeof(caps), 1);
    check("caps_limits", caps.max_views == 32 && caps.max_groups == 16 && caps.max_kv_heads == 32 &&
          caps.max_view_bytes == 1048576 && caps.pin_limit_bytes == 67108864, 1);
    check("caps_zero_flags_reserved", caps.flags | caps.reserved[0] | caps.reserved[1] |
          caps.reserved[2] | caps.reserved[3], 0);
    invalid_requests(fd);
    k = map_kv(0); v = map_kv(0);
    if (!k || !v) goto finish;
    for (unsigned i = 0; i < 16; ++i) { groups[i].kv_head = i % 2; groups[i].heads = 1; }
    groups[0].kv_head = 1;
    struct ara_resident_kv_view d = descriptor(k, v);
    if (register_kv(fd, &d, "register_live_view")) goto finish;
    live_inputs(fd, &d);
    metadata_aliases(fd, &d);
    private_lifecycle(fd);
    long other = call(__NR_openat, AT_FDCWD, (long)"/dev/ara-resident", O_RDWR, 0, 0, 0);
    check("second_fd_open", other >= 0, 1);
    if (other >= 0) {
        struct ara_resident_batch b = batch(d.handle);
        batch_result(other, &b, "handle_is_fd_local", -116, 0);
        check("other_fd_cannot_release", release_kv(other, d.handle), -2);
        check("second_fd_close", call(__NR_close, other, 0, 0, 0, 0, 0), 0);
    }
    fork_wrong_mm(fd, d.handle);
    check("release_live_view", release_kv(fd, d.handle), 0);
    struct ara_resident_batch old = batch(d.handle);
    batch_result(fd, &old, "released_live_view_stale", -116, 0);
    check("release_twice_missing", release_kv(fd, d.handle), -2);
    for (unsigned axis = 0; axis < 2 && k && v; ++axis)
        for (unsigned unmap = 0; unmap < 2 && k && v; ++unmap)
            invalidate_mapping(fd, &k, &v, axis, unmap);
    if (k && v) {
        handle_limits(fd, k, v);
        d = descriptor(k, v);
        if (!register_kv(fd, &d, "register_close_owned")) {
            check("close_releases_live_views", call(__NR_close, fd, 0, 0, 0, 0, 0), 0);
            fd = call(__NR_openat, AT_FDCWD, (long)"/dev/ara-resident", O_RDWR, 0, 0, 0);
            check("reopen_fd", fd >= 0, 1);
            if (fd >= 0) {
                old = batch(d.handle);
                batch_result(fd, &old, "closed_fd_handle_stale", -116, 0);
                handle_limits(fd, k, v);
            }
        }
    }
finish:
    if (fd >= 0) check("device_close", call(__NR_close, fd, 0, 0, 0, 0, 0), 0);
    if (k) check("cleanup_key_mapping", call(__NR_munmap, (long)k, MAP_BYTES, 0, 0, 0, 0), 0);
    if (v) check("cleanup_value_mapping", call(__NR_munmap, (long)v, MAP_BYTES, 0, 0, 0, 0), 0);
    if (loaded) check("delete_module", call(__NR_delete_module, (long)"ara_resident", O_NONBLOCK, 0, 0, 0, 0), 0);
    if (module_fd >= 0) call(__NR_close, module_fd, 0, 0, 0, 0, 0);
    rc = call(__NR_syslog, 3, (long)text, sizeof(text) - 1, 0, 0, 0);
    if (rc >= 0) { text[rc] = 0; put("DMESG_BEGIN\n"); put(text); put("DMESG_END\n"); }
    else check("dmesg", rc, 0);
    put("INFO_EXPECT cpus="); number(guest_cpus); put(" rounds="); number(info_rounds); put("\n");
    put("ARITHMETIC_NOT_EXECUTED INFO4_ZERO_EXPECTED NO_BOARD_TEST\n");
    put(errors ? "RESIDENT_VIEWS_V2_LINUX_FAIL cpus=" : "RESIDENT_VIEWS_V2_LINUX_PASS cpus=");
    number(guest_cpus); put(" checks="); number(checks); put(" errors="); number(errors); put("\n");
    call(__NR_reboot, 0xfee1dead, 0x28121969, 0x4321fedc, 0, 0, 0);
    for (;;) asm volatile("" ::: "memory");
}
