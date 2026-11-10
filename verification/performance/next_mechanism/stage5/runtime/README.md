# Experimental Resident Platform Contract V1

New Ara-owned helper only. No SDK/native-core, RTL or actual llama source is
modified. The weak `akv_resident_platform_current_v1()` returns NULL. There is
no environment registration, runtime capability override or positive board
provider. This is a trusted linked platform interface, not a security boundary
against arbitrary code already executing in the process.

## API And Lifetime

`admit_v1(provider, request, session)` checks the provider's version, contract
identity and profile, then reads actual thread state before request metadata
or device/options copies. The provider's immutable SHA256 binds a sealed
launcher, image or validated instruction model, ISA, OS, RAM, single-worker
and exclusive-process contract. TEST_MODEL and EXTERNAL_DEPLOYMENT have distinct
kind values. A successful model grant is not board acceptance or index4 support.

The scalar provider acquire callback validates every supplied span/lifetime and
returns a whole-operation ownership cookie. Failed acquire retains no lease.
An acquired callback changing CSR state returns INVALID after scalar cleanup,
not transparent fallback with altered flags. All request/span/provider metadata
stays immutable through finish. Input Q can still be F32 before conversion;
its converted scratch and every output/workspace span must also be covered.

`group_v1(session, index, device, plan, features, options)` preflights each group
in order, checks actual state, original SDK shape/caps/plain masks and authorized
spans, then produces existing SDK options. It does not execute any instruction
stream or copy the plan/device. `start_v1(session)` requires all groups prepared;
once started, reselection returns NO_RETRY. `finish_v1(session)` releases exactly
once after SDK completion/RELEASE, or before execution on a declined group.

KEEP_NATIVE is only a resident decline. It does not authorize legacy INFO/AKV:
the frontend needs independent native admission, otherwise ordinary GGML/RVV.
BAD_VSTART is an invalid vector ABI state, not a normal vector fallback. The
helper never clears CSR state. Environment selectors only express a request.

## Safe State Access

The provider must establish CSR read safety before supplying `read_state`.
Linux providers use auxiliary-vector/HWCAP and supported hwprobe extension
results plus per-thread Vector policy; they must not read privileged mstatus/
sstatus in user mode or change the parent's Vector policy with SET_CONTROL.
Unavailable/unknown OS support denies admission. These OS checks are provider
startup/thread authorization, not fabricated live FS/VS status bits.

`read_state.S` reads VSTART first and rejects nonzero before any output store;
then it reads VLENB/FCSR/VCSR. It has no CSR writes, FP/vector/custom instruction,
stack frame or libc call. Provider callbacks, including release on rejection,
must be scalar-safe. Compile platform.c with both loop and SLP vectorization
disabled; GNU object audit checks the entire helper for FP/vector/custom code.

## Verification And Integration Boundary

`test_platform.py --output OUT/stage5_resident_platform_host_YYYYMMDD_NN` archives
SDK f50092f2d and runs host/UBSan policy tests plus a GNU scalar object audit.
Host provider data is synthetic policy-test input, NOT an accepted QEMU model.
A later positive gate must use the explicitly linked, validated QEMU provider
and execute real native QK/PV through the actual GGML entry. Default/absent,
unsupported and last-group declines must show zero resident/custom work where
native admission is absent. No goal is closed by always taking fallback.

The future registered GGML overlay is based on da56 archive, then a reviewed
adaptation of the old auto-pair patch targeting akv.cpp SHA40e41f2a, followed by
the reviewed platform/dispatch delta. Preserve da56 feature/quant-KV handling;
never use HEAD039 or copy the dirty tree. Actual akv.cpp/CMake patches await
API review. Stage4 A and the feature extension remain unpromoted/default OFF.
