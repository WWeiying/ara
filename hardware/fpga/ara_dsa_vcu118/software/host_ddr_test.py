#!/usr/bin/env python3
"""Small destructive DDR scratch test. Never a full-capacity DDR qualification."""
import hashlib
import struct

from host_image import CAP_DDR2, DDR1, DDR2, burst_slices, check_range
from host_transport import Operation

SCRATCH_BYTES = 64 * 1024


def plan(caps):
    windows = [DDR1] + ([DDR2] if caps & CAP_DDR2 else [])
    records = []
    for bank, (lo, hi) in enumerate(windows, 1):
        address = hi - SCRATCH_BYTES
        check_range(address, SCRATCH_BYTES, caps)
        records.append({"bank": bank, "address": address, "bytes": SCRATCH_BYTES,
                        "bank_start": lo, "bank_end_exclusive": hi})
    return records


def pattern(bank, offset, size):
    if bank not in (1, 2) or offset % 8 or size % 8:
        raise ValueError("Invalid scratch pattern request")
    salt = 0x0123456789ABCDEF if bank == 1 else 0xFEDCBA9876543210
    return b"".join(struct.pack("<Q", (salt ^ ((offset + i) // 8 * 0x9E3779B97F4A7C15)) &
                                 0xFFFFFFFFFFFFFFFF) for i in range(0, size, 8))


def test_memory(transport, caps, destructive_confirmed=False, full_reset_confirmed=False):
    if not destructive_confirmed or not full_reset_confirmed:
        raise ValueError("DDR scratch test requires destructive and full-reset confirmation")
    records = plan(caps)
    edge_reads = []
    # Bank endpoints are read-only probes. All destructive traffic stays within
    # the fixed last-64-KiB reservations, including their first and last beats.
    for record in records:
        for address in (record["bank_start"], record["bank_end_exclusive"] - 8):
            check_range(address, 8, caps)
            reply = transport.exchange([Operation("M", "READ", address)])[0]
            edge_reads.append({"bank": record["bank"], "address": address,
                               "read_only_data_hex": reply.hex()})
    pending = []
    for record in records:
        for address, offset, size in burst_slices(record["address"], record["bytes"]):
            data = pattern(record["bank"], offset, size)
            pending.append(Operation("M", "WRITE", address, size // 8, data))
            if len(pending) == 32:
                transport.exchange(pending)
                pending.clear()
    if pending:
        transport.exchange(pending)
    # Deliberately verify ONLY AFTER BOTH BANKS have been written: same-offset
    # aliasing would otherwise pass a write-then-read test of each bank alone.
    for record in records:
        expected_hash = hashlib.sha256()
        read_hash = hashlib.sha256()
        for address, offset, size in burst_slices(record["address"], record["bytes"]):
            expected = pattern(record["bank"], offset, size)
            actual = transport.exchange([Operation("M", "READ", address, size // 8)])[0]
            if actual != expected:
                raise RuntimeError(f"DDR{record['bank']} scratch mismatch/possible alias at 0x{address:x}")
            expected_hash.update(expected)
            read_hash.update(actual)
        record.update(expected_sha256=expected_hash.hexdigest(), readback_sha256=read_hash.hexdigest(),
                      verified=True)
    return {"scope": "last 64 KiB per enabled bank only; not a full DDR test",
            "destructive": True, "cross_bank_alias_check": len(records) == 2,
            "records": records, "edge_reads": edge_reads}
