# Real-context paired-head three-way successor

Preparation only. Own files in this directory; old threeway files, canonical
native C/assembly, experimental native_bench and helpers stay unchanged. No
simulator launcher is provided. No deployment or numerical runtime PASS is
claimed by build/host tests.

## Data and numerical selection

Default is genuine `...attention-contexts-20260830_070252/kv256`. Both reviewed
profiles128/256 use the same physical K/V capacity256 and strides. Capture
selection, expected visible mask and native kv_length are coupled by the build
profile, never by replacing a KV128 checksum or repeating captured rows.

All five original binary hashes are checked against tensor.sha256. Pin run.conf,
model.json, prompt, completion record, replay metadata, tensors, tools and all
transitive source/header inputs. Preserve source_commit316e72d38 and recorded
source_dirty=true; this does not claim reproduction from a clean host checkout.
Q heads0,1,6,7 and matching golden are cropped offline using the sealed
threeway_build.crop_heads/validate_crop helpers. K/V/mask stay unchanged. This
is a derived Qwen2.5 GQA2 subset, not a Qwen3 capture or original GQA6.

Use original gen_data.make_spec/emit_blob and check linked configuration/blob
bytes. Cropped Q=[128,1,4,1], golden=[512,1,1,1], both2048B. The shared output
is exactly2048B; 64B guards before/after are outside its ABI capacity.

Same ELF/order: rvv,generic,paired,paired,generic,rvv. Actual run_attention_rvv,
not tiled RVV, receives the cropped config without artificial cap queries. AKV
uses sealed native_bench wrappers with real capability/admission checks before
FULL. Query conversion uses original helper and kvhead*2+head. Timing includes
normal preparation, plan/admission, execute, stores/drain; poison, checks and
offline cropping are excluded. Initial RNE FCSR0/VCSR5, sampled before checking.

All512 outputs finite and original atol0.004/rtol0.002; exact rawbits/FCSR/VCSR
repeats per variant; generic/paired exact. Ordinary RVV may differ bits/flags.
No comparison to KV128 numerical identity. Functional PASS accepts neutral or
negative performance and reports it separately; deployment_approved=false.

The integration constraints in hardware/docs/akv_pair_runtime_integration.md
apply: this single-thread experimental wrapper is NOT a production-safe global
selector. No use of the new dispatch.h is implied by this evidence. Odd heads,
six-head special preservation, missing caps, other types, multithreading and
whole-model coverage remain separate gates.

## Expected KV256 work

Per generic/paired call:3082/778 commands, FULL2 REFILL6 RELEASE2;
KCOL2048/256 (panels0/256), PV1024/512, logical columns2048/1024;
replay524288/262144B. Both: Q1024B, KV262144B, payload263296B, ranges1030.
Six trials total7720 commands; RVV must have zero AKV commands. Raw final
AKV_PERF_SUMMARY is mandatory, not synthesized from printed trial claims.

## Build and host verification

```sh
python3 -B -m unittest discover -s verification/akv/paired_heads/contexts -p test_contexts.py -v
python3 -B verification/akv/paired_heads/contexts/build_context.py --kv 256 \
  --output verification/out/akv-context-kv256-threeway-build-20261024-01
```

Fresh GNU rv64gcv_zfh_zvfh objects, no old object reuse; overlap OFF. Build pins
current accepted16MiB/4lane/VLEN1024 image and all its recorded RTL sources but
does not execute it. Post-build pin equality, ELF bounds, real kernel calls,
CSR/drain, ordinary RVV versus tiled exclusion, configuration and every blob
byte/output guard address are verified. build.json stays BUILT_NOT_EXECUTED.
`--kv 128` is supported for a separately named successor build, not a request
to rebuild or mutate the old sealed KV128 campaign.

## Later independent acceptance (not authorized here)

After a future authorized worker executes with +AKV_PERF +AKV_SUMMARY and an
actual +VECTOR_TRACE, it must verify simulator exit0, bounded process cleanup,
source inventory before/after and all input/image pins. Use a fresh checker
output directory:

```sh
python3 -B verification/akv/paired_heads/contexts/check_context.py \
  --build <BUILD> --log <run.vcs.log> --vector-trace <vector_trace.csv> --output <NEW_CHECK_DIR>
```

The checker revalidates capture/crop/build pins, enforces complete six-trial
order, every command/lifecycle/fault/traffic record, actual admission, raw final
summary and its own numerical identities. It runs unchanged ara_verify.uvm_dut
with all four requirements: events, backend, AXI reads, AXI writes. UVM PASS,
empty issues and matching ELF/image/log/vector hashes are mandatory, with
post-check pins reverified. It returns NUMERIC_WORK_AND_UVM_CHECKED, not a claim
that an unobserved simulator process exited correctly. No worker or VCS launch
is included. Host fixtures are explicitly synthetic and do not count as native
execution evidence.
