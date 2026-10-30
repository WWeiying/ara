# Private RVV Stride Repair Acceptance

Run `python3 -B verification/qbs/m4_prepared_reuse/packed_stride/rvv_fallback/repair_accept/accept.py`
from the signoff integration worktree. The fixed output directory must not exist.
No retries are dispatched after unexpected failure.

This builds a private repack object from live, hash-verified source using the
normal compile record and headers plus the strided-input helper include path.
The candidate is exactly `general_transform.py` from commit `30c89b228`.
The original frozen test object is linked unchanged with that private object
and the four normal archives. No live source, archive, RTL or installed runtime
is modified. Inherited inventories merge with conflict rejection; the active
1880-entry VCS inventory and original failed artifacts remain pinned unchanged.

`check.py` is an explicit successor of the original checker, mechanically
copied with exactly one accounting-expression replacement, verified before
compilation. Each case must have two generic disabled K512 producer records
and two generic disabled K256 gathered producer records, in that order.
All original finite, bit-exact numeric, ownership, callback, integrity and
stop-contract checks remain unchanged. The runner additionally requires all
four cases to pass. `test_check.py` mutates the resulting complete raw evidence
to check rejection of altered producers, numbers, ownership and completion.

One unchanged QEMU command (except the private initramfs path) runs with
`xaraqbs=false` and a 180-second bound. M4/M7 padded-row and element-stride
Q4_K N32 K512 cases are the functional acceptance scope. The linker map and
demangled symbols prove the ordinary `block_q4_Kx32` trait's private provider.

Output: `verification/out/m4-stride-rvv-repair-20261027-01`, including commands,
exit records, raw logs, source diff, symbols, inventories, comparison and result.
QEMU host elapsed time is workflow information only, not target performance.
This does not accept Q8_0, QBS execution, packed/cache selection, MUL_MAT_ID,
installed-runtime integration, hardware timing or RTL. Parent review and
separate regression/integration acceptance remain required. No commit is made.
