/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef ARA_RESIDENT_KV_VIEW_H
#define ARA_RESIDENT_KV_VIEW_H
#include <linux/mmu_notifier.h>
#include <linux/spinlock.h>
#include "view_layout.h"

struct resident_pinned_map {
    struct mmu_interval_notifier notifier;
    spinlock_t lock;
    struct page **pages;
    void *mapping, *data;
    unsigned reserved_pages, pinned_pages;
    bool inserted, invalid;
};

struct resident_kv_view {
    struct ara_resident_kv_view layout;
    struct ara_resident_view_sizes sizes;
    struct resident_pinned_map key, value;
};

/* All accounting and table operations run under accelerator_lock. */
static unsigned long resident_pinned_pages;
static u64 resident_next_handle;

#ifdef CONFIG_MMU_NOTIFIER
static bool resident_invalidate(struct mmu_interval_notifier *notifier,
        const struct mmu_notifier_range *range, unsigned long sequence)
{
    struct resident_pinned_map *map = container_of(notifier, struct resident_pinned_map, notifier);
    unsigned long flags;
    (void)range;
    spin_lock_irqsave(&map->lock, flags);
    WRITE_ONCE(map->invalid, true);
    mmu_interval_set_seq(notifier, sequence);
    spin_unlock_irqrestore(&map->lock, flags);
    /* Long-term pins retain the old pages, but this handle can never run again.
     * Execution is synchronous on the only online CPU with preemption/IRQs off.
     * No device transaction survives the protected group or this callback.
     */
    return true;
}

static const struct mmu_interval_notifier_ops resident_notifier_ops = {
    .invalidate = resident_invalidate,
};
#endif

static void resident_unpin_map(struct resident_pinned_map *map)
{
#ifdef CONFIG_MMU_NOTIFIER
    if (map->inserted) mmu_interval_notifier_remove(&map->notifier);
#endif
    if (map->mapping) vunmap(map->mapping);
    if (map->pinned_pages) unpin_user_pages(map->pages, map->pinned_pages);
    resident_pinned_pages -= map->reserved_pages;
    kvfree(map->pages);
    *map = (struct resident_pinned_map){0};
}

static int resident_pin_map(struct resident_pinned_map *map, u64 address,
        unsigned bytes, u64 allowed_base, u64 allowed_size)
{
#ifdef CONFIG_MMU_NOTIFIER
    unsigned long first = address & PAGE_MASK;
    unsigned pages = DIV_ROUND_UP(offset_in_page(address) + bytes, PAGE_SIZE);
    unsigned long sequence, flags;
    long pinned;
    int rc;
    bool invalid;
    if (!current->mm || !access_ok(u64_to_user_ptr(address), bytes)) return -EFAULT;
    if (pages > (ARA_RESIDENT_PIN_LIMIT_BYTES >> PAGE_SHIFT) - resident_pinned_pages)
        return -ENOSPC;
    map->pages = kvmalloc_array(pages, sizeof(*map->pages), GFP_KERNEL);
    if (!map->pages) return -ENOMEM;
    map->reserved_pages = pages;
    resident_pinned_pages += pages;
    spin_lock_init(&map->lock);
    rc = mmu_interval_notifier_insert(&map->notifier, current->mm, first,
                                      (unsigned long)pages << PAGE_SHIFT, &resident_notifier_ops);
    if (rc) goto fail;
    map->inserted = true;
    sequence = mmu_interval_read_begin(&map->notifier);
    pinned = pin_user_pages_fast(first, pages, FOLL_LONGTERM, map->pages);
    if (pinned > 0) map->pinned_pages = pinned;
    if (pinned != pages) { rc = pinned < 0 ? pinned : -EFAULT; goto fail; }
    for (unsigned i = 0; i < pages; ++i) {
        phys_addr_t p = page_to_phys(map->pages[i]);
        if (p < allowed_base || p - allowed_base >= allowed_size ||
            PAGE_SIZE > allowed_size - (p - allowed_base)) { rc = -EOPNOTSUPP; goto fail; }
    }
    map->mapping = vmap(map->pages, pages, VM_MAP, PAGE_KERNEL_RO);
    if (!map->mapping) { rc = -ENOMEM; goto fail; }
    map->data = (char *)map->mapping + offset_in_page(address);
    spin_lock_irqsave(&map->lock, flags);
    invalid = map->invalid || mmu_interval_read_retry(&map->notifier, sequence);
    spin_unlock_irqrestore(&map->lock, flags);
    if (invalid) { rc = -ESTALE; goto fail; }
    return 0;
fail:
    resident_unpin_map(map);
    return rc;
#else
    (void)map; (void)address; (void)bytes; (void)allowed_base; (void)allowed_size;
    return -EOPNOTSUPP;
#endif
}

static bool resident_view_valid(const struct resident_kv_view *v)
{
    return v && v->key.notifier.mm == current->mm && v->value.notifier.mm == current->mm &&
           !READ_ONCE(v->key.invalid) && !READ_ONCE(v->value.invalid);
}

static void resident_free_view(struct resident_kv_view *v)
{
    if (!v) return;
    resident_unpin_map(&v->key);
    resident_unpin_map(&v->value);
    kfree(v);
}
#endif
