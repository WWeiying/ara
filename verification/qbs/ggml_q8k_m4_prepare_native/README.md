# Q8_K M4 native numerical gate

This suite compares the isolated RVV preparation candidate with the actual
linked production `ggml_quantize_mat_q8_K_4x1_ara_generic`. It does not measure
RTL cycles or prove production GGML dispatch into the candidate.

## Coverage

- 50 datasets, including six real activation slices from attention projection,
  FFN gate and FFN down projection (K=1536 or K=8960, four input rows).
- Five rounding modes, eight initial FCSR/VCSR combinations and three AVL caps
  (1, 7, 16): 6000 comparisons per VLEN.
- Signed maximum ties, signed zeros, FMA versus separate-multiply rounding,
  underflow, group boundaries, multiple block counts and rejected domains.
- Exact output bytes, scales and signed 16-element block sums; output guards
  and unchanged input; exact FCSR/VCSR and expected candidate/fallback choice.
- VLEN128 and VLEN1024 must have identical per-dataset output digests.

The checker expects 936 candidate and 5064 fallback comparisons per VLEN.
Fallback correctness is tested but is not counted as vector-path coverage.
Subnormal/nonfinite inputs, unsupported scale domains and non-RNE modes retain
the production generic path. The candidate does not alter production defaults.

## Execution and evidence

`build.py --help` describes the sealed cross-build. It captures the actual
production archive identity, checks its FMA disassembly and records source
capture offsets and hashes. Use a new output directory for each build/run.

From the repository root, run the bounded worker with:

```sh
python3 verification/qbs/run_q8k_m4_native.py \
  --build /absolute/path/to/sealed-build \
  --configuration /absolute/path/to/native-qemu-configuration.json \
  --output /absolute/path/to/new-run
```

For background execution, make this worker the direct systemd service command.
Each guest has a 900-second limit. Read `status.json` together with the raw
`qemu-128.log` and `qemu-1024.log`. A READY build or a RUNNING worker is not a
passing result. The runner rejects pin drift and incomplete guest records.

`test_check.py` checks the acceptance parser; passing those host tests is not
execution of the RVV candidate. Native numerical acceptance is followed by
same-image VCS preparation and projection measurements, including preflight
cost, before any speedup or production enablement is claimed.
