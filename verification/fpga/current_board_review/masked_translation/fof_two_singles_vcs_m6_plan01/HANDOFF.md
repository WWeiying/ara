# Prepared, Not Launched

Frozen plan: `prepared01/plan.json`

SHA256: `da842f3be54dc8d15eaf4b6551766152c375e97321624c525f9350dbc16affa1`

The plan binds 744 pins, including all 118 original reference pins, unchanged
SoC ELFs, M6 image/source/config, transitive decoder/runner imports, and the
actual Confucius decision/REVIEW. Independent review scope remains static
source/adapter plus reference metadata, not an independent full raw parse.

Host `host04/status.json`: 44 checks PASS, actual process exit0 in15.73s.
SHA256: `9824206cb9e7b1af4e81165861cfc0ccc6c7466963b58f5ce25072274951cb05`.
Both complete synthetic SoC-PC oracles passed; negatives include defined data,
guards/tail/neighbor, returned VL/vstart versus restored VL, missing full reads,
unused internal PCs, duplicate helper window, typed e64 old-vd, missing oracle,
actual partial-line failure monitoring, plan/image/ELF/budget drift and sticky
postcheck failure with durable child numeric0. e8 undefined5..8 arbitrary values
are positively accepted. Synthetic Host evidence is not a DUT measurement.

`host01`/`host02` retain synthetic-generator errors (selected sd-zero and an
unavailable register setter). `host03` retains the earlier37-check PASS. These
are not reference/DUT failures; no reference was rerun or changed.

Two actual runner dryrun results: `prepared01/dryrun_gate.json`, SHA256
`8ca68ad001723032ede5c35f24d675e3cf83af5753ac0b05ae2589da5f91816d`.
Dryrun prints commands against original immutable inputs; actual execution
uses the existing runner's private-copy/preload contract, checked postrun.
No simulator, service, compiler or new reference was started. No live DUT query.

Main's exact launch command template and worker arguments are in
`prepared01/ready.json`, SHA256
`24fe3f02cb74bb051fa5b9460b365fc472b98af9b2f88ba599060c46291f5b58`.
Provide the new parent-review path/SHA in that template. The gate requires
`AUTHORIZE_FOF_TWO_ORIGINAL_M6_ONCE`, this exact plan SHA, unit
`ara-fof-original-two-m6-01.service`, READY SHA, actual review pins and explicit
budget-risk acceptance. Jobs2, sim1800s each, worker3000s, service3600s; no retry,
FSDB or build. Runtime resource admission remains deferred to Main's launch.

Only two source-derived Sv39 singles are in scope, not Linux signals/all eight
historical ELFs. Architectural target exception0 is required; zero physical
MMU activity is not measured or claimed. Sealed worker/checker/plan files will
not be edited after this handoff.
