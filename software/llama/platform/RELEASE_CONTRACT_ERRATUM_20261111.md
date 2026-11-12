# Release contract erratum

This additive successor corrects the release callback documentation only.
It supersedes the blanket no-syscall/no-CSR-write wording for release in
`resident_deployment.h` and `DEPLOYMENT.md`. Those original files and the
`extension_resident_deployment_20261111_01` inputs/results remain sealed.
No C layout, symbol, runtime implementation or default authorization changes.

## Correction

The upstream `platform.h` acquire/release ABI requires preservation of
FCSR/VCSR/VSTART, no accelerator computation, and scalar-safe release even
after BAD_VSTART. It does not prohibit a supported kernel syscall or scalar
CSR restoration. Stage5's syscall-free release is one implementation choice,
not a universal deployment restriction. The adapter already delegates release
to the binding without imposing a runtime syscall ban.

The corrected release contract is:

- Validate the cookie and calling owner, including cleanup after revocation.
- Remain scalar-safe in the user callback. Do not issue FP/vector or custom
  accelerator computation, clear BAD_VSTART, or retry partially executed work.
- A reviewed platform binding may call its kernel lease-release interface when
  the complete syscall/return path is proven safe for its CSR and context
  contract. Preserve the entry FCSR/VCSR/VSTART exactly, including nonzero
  VSTART. Scalar CSR writes used to restore these saved values are permitted;
  changing policy, rounding or clearing an invalid state is not permitted.
- Maintain ownership and memory lifetime until SDK completion/RELEASE and
  kernel-confirmed release. Do not silently return success on cleanup failure.
  The void callback must fail fatally if its cleanup guarantee cannot be met.

Read-state/observe still cannot enter the OS or modify CSR state before the
existing VSTART-first guard. This erratum does not authorize a new platform,
relax any admission guarantee, or imply that generic Linux ioctl is safe.

## Future Linux implementation boundary

The checked local Linux syscall entry discards vector state before the ioctl
handler. A scalar driver handler alone therefore does not prove preservation.
A future binding needs an audited scalar save/syscall/restore wrapper or a
proved kernel preservation path. Save nonzero VSTART with a dedicated cleanup
snapshot helper, not the existing admission reader which rejects it. Restore
VSTART last and return without FP/vector work. Kernel owner checks, context
protection, release errors and interrupted/repeated cleanup need explicit
semantics and tests before deployment. This is permitted future work, not an
implemented wrapper or accepted kernel path in this change.

## Scope and evidence

Keep the mature default-deny provider entry. No kernel, RTL, FPGA, board or
physical validation is added. The original 918 checks remain evidence for
their original narrower implementation, not kernel syscall acceptance.
`review_release_erratum.py` records a separate static documentation review and
checks the original sealed source/artifact inventories without rerunning them.
Resident on the board remains unauthorized; QBS QBINFO5 is unrelated authority.
