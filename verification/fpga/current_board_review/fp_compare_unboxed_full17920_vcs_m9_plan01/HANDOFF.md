# Entry Review Handoff

Prepare/dryrun completed, no launch. Aquinas is reviewing the following exact inputs:

| Input | SHA256 |
| --- | --- |
| prepared01/plan.json | 54f4fbbac1603f1742cbb6d6ad090aee20a9609f9d2efed2dc1c29dd85b0bbdd |
| replay.py | 88d7d1472f9475f6a678b7e2e3c114816cc49cb72acf255cb20a0a9adf95f4ac |
| checker.py | c3e5f0847d652f2ac7939372e91002a8ee0c56dd32808333a6527228417172f5 |
| strict.py | 0bfc7055399b1b3bac8692d0469b617f8efc93f8f752ac67fe01d3ee31c7d485 |
| specification.py | 168b5484eba4ddb4f5ffa513b11d5a78af883f9c788bc0355953e6e0b479a7c2 |
| host02.json | 31906b71ef66309a92d377eec85e3814b7c937667eaca50f651878f7cbba0684 |

The worker validates this independent entry schema, at `ENTRY_REVIEW.json`:

```json
{
  "decision": "NO_BLOCKER_FULL17920_M9_ENTRY",
  "plan_sha256": "54f4fbbac1603f1742cbb6d6ad090aee20a9609f9d2efed2dc1c29dd85b0bbdd",
  "worker_sha256": "88d7d1472f9475f6a678b7e2e3c114816cc49cb72acf255cb20a0a9adf95f4ac",
  "checker_sha256": "c3e5f0847d652f2ac7939372e91002a8ee0c56dd32808333a6527228417172f5",
  "strict_sha256": "0bfc7055399b1b3bac8692d0469b617f8efc93f8f752ac67fe01d3ee31c7d485",
  "reference_review_sha256": "50a0025d6c03a2df9e4396631b8431b8a36535d45962cc3ac7c837228b9c13c9"
}
```

This example is a schema, **not an issued independent decision**. The real
review file/hash must be supplied, followed by a separate new parent run
authorization. The latest parent instruction permits preparation only.

No running service exists for this preparation. No old reference, shared
helper, RTL, image, source ELF or parent-maintained pending index was edited.
