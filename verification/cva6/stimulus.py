"""Fixed, reviewed schedule. No feedback from DUT probes changes the stimulus."""

FIELDS = (
    "seq", "id", "kind", "view", "cons", "c0_acc", "c0_valid", "c0_id",
    "c1_acc", "c1_valid", "c1_id", "ack0", "flush", "ready", "resp_seq",
    "resp_id", "ld_done", "st_done",
)
MAX_CYCLES = 256


def schedule():
    rows = []
    ready = 1

    def edge(label, **kw):
        row = dict.fromkeys(FIELDS, 0)
        row.update(cons=1, ready=ready)
        row.update(kw)
        rows.append({"label": label, **row})

    def issue(seq, ident, kind):
        edge(f"issue_{seq}", seq=seq, id=ident, kind=kind, view=1)
        edge(f"execute_{seq}")

    def commit(ident, **kw):
        edge(f"commit_{ident}", c0_acc=1, c0_id=ident, **kw)

    def respond(seq, ident, **kw):
        edge(f"response_{seq}", resp_seq=seq, resp_id=ident, **kw)

    def stalls(name):
        for cons in (0, 1):
            for view in range(2, 9):
                edge(f"{name}_view{view}_cons{cons}", view=view, cons=cons)

    edge("initial_empty")
    issue(1, 0, 0)
    issue(2, 1, 1)
    commit(1)  # Both pending; a mismatched head must not pop.
    commit(0)
    edge("younger_recorded_ready")
    edge("drain_pair")
    respond(1, 0)
    respond(2, 1, ld_done=1)

    issue(3, 2, 0)
    for _ in range(3):
        edge("port1_blocked", c0_valid=1, c0_id=7, c1_acc=1, c1_id=2)
    edge("port1_released", c0_valid=1, c0_id=7, c1_acc=1, c1_id=2, ack0=1)
    edge("port1_drain")
    respond(3, 2)

    ready = 0
    issue(4, 3, 1)
    stalls("load_spec")
    commit(3)
    stalls("load_disp")
    issue(5, 4, 2)
    commit(4)
    issue(6, 5, 1)
    commit(5)  # Spill full: readiness is recorded but no pop.
    issue(7, 6, 2)
    edge("queue_capacity", view=1)
    edge("flush_ready_and_pending", flush=1)
    for _ in range(3):
        edge("issued_preserved")
    issue(8, 5, 1)  # Reuse the canceled ready ID with a different identity.
    edge("reuse_canceled_wait")
    ready = 1
    edge("drain_preserved_first")
    edge("drain_preserved_second")
    commit(5)
    edge("drain_reused")
    respond(4, 3, ld_done=1)
    respond(5, 4, st_done=1)
    respond(8, 5)  # Response is deliberately not memory completion.
    issue(9, 3, 1)  # Reuse an issued, responded ID; still needs its own commit.
    edge("reuse_issued_wait")
    commit(3, ld_done=1)  # Complete 8 as 9 moves from queue to spill.
    edge("drain_load_overlap")
    respond(9, 3, ld_done=1)

    issue(10, 0, 2)
    stalls("store_spec")
    commit(0)
    stalls("store_disp")
    respond(10, 0)
    issue(11, 1, 2)
    edge("reuse_store_wait")
    commit(1, st_done=1)
    edge("drain_store_overlap")
    respond(11, 1, st_done=1)
    stalls("empty")
    edge("final_empty")
    assert len(rows) <= MAX_CYCLES
    return rows


def render(rows):
    return "".join(row["label"] + " " + " ".join(str(row[f]) for f in FIELDS)
                   + "\n" for row in rows)
