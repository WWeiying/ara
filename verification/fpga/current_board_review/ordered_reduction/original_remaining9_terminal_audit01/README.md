# Remaining9 Independent Terminal Audit Preparation

Prepare only. No current CSV, strict result, console, complete.json, service status or process is read by `prepare`. No new reference, Host suite, DUT execution or compilation is performed. The only batch-output file permitted during preparation is the sealed `prepared01/plan.json`.

`audit.py prepare` validates static source/ELF/spec geometry for all nine shapes and AST syntax, then exclusively creates `prepared.json` binding this reader, observer and README. This is not runtime Host-test validation and not terminal acceptance. Existing shared checker/runner remain untouched. Full1352-plan-pin and75-terminal-evidence checks are deferred until parent authorizes terminal inspection.

## Prepared Checks

- Exact e16 mf2/m1/m2/m4/m8 plus e32 mf2/m2/m4/m8 membership, CAP32/64/128/256/512 and16/64/128/256 respectively; VL=CAP/2, VLEN1024.
- Canonical handoff03 redspecial02 source bytes, each private ELF's actual instruction bytes, all original helper21 windows, unused op1/op2 full ranges, shape capacity3 and seven legal bootstrap/C CSR instructions. No fixed PC displacement between ELFs.
- One CSV parse per shape through the unmodified sealed checker and a separate lossless observer. Each same row is passed unfiltered/in order and checked unchanged afterward, with equal before/after ordered row digests. All actual PC/encodings and CVX/uop request/completion ownership are checked.
- Original all-eight-scenario input/seed stores, all3360 mask fills and6720 fixture-field reads, selected setup, all21 consecutive helper instructions, fflags NV16/vstart0 reads, complete144-byte output/oldvd/guards and exit0/parking. e16 uses7e00 and e32 uses7fc00000; seed remains64 words even for CAP512.
- Restore evidence is strictly retired frm/fflags writes with saved zero-valued source operands. No post-restore CSR state readback is added, inferred as directly measured, or borrowed from Spike CSR logs.
- Exact nine child results, each rc0/within5400s, COMPLETE run metadata, abort=false/retries0, actual command/private ELF/image identities, raw console/runlog firsterror vetoes, no failure artifacts, before/after pins and producer dictionary equality. Labels alone cannot pass.
- Service launch identity is historical evidence only. No live query or GC-based outer rc0 inference. Result keeps outer terminal returncode/result unknown.

## Entrypoints

Preparation (only mode authorized now):

```sh
python -B audit.py prepare
```

After batch terminal and a separate explicit parent authorization supplying exact complete SHA, run once in a fresh owned output. This is an offline audit, not a DUT launch:

```sh
python -B audit.py terminal --authorize-terminal-audit \
  --prepared-sha256 PREPARED_SHA \
  --complete-sha256 PARENT_CONFIRMED_COMPLETE_SHA \
  --out /home/wangwy/openproject/ara_dsa_signoff_integration/verification/fpga/current_board_review/ordered_reduction/original_remaining9_terminal_audit01/terminal01
```

Sequential offline parsing limits CPU usage to one reader; mf4's measured195s is a planning reference, not a deadline or guaranteed runtime for these shapes. No automatic retry or polling. A parsing/check failure produces NOT_ACCEPTED, retaining any intermediate per-shape reconstruction without batch acceptance. Successful scope is nine reduced singles/1296 oracle bytes, not full6720 parents, all11 records, Linux replay or newer RTL.
