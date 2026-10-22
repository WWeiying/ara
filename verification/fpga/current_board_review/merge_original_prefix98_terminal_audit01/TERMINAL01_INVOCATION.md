# Authorized Merge98 Offline Audit Invocation

Actual auditing PID printed by the process: **1389942**.
Original execution session: **41228**.
The parent authorized one offline terminal audit, with no simulator/reference rerun or automatic retry.

Effective command and `sys.argv`:

```sh
/usr/bin/python -B /home/wangwy/openproject/ara_dsa_signoff_integration/verification/fpga/current_board_review/merge_original_prefix98_terminal_audit01/audit.py terminal --authorize-terminal-audit --prepared-sha256 373561d4fcdf916e1b505748b7498da3b173823f2a01b935ae4dad28e377e741 --complete-sha256 6c010fba28fcada854af4c79e08f76e1f36e074dda9b74370d24d624bcdb2c74 --out /home/wangwy/openproject/ara_dsa_signoff_integration/verification/fpga/current_board_review/merge_original_prefix98_terminal_audit01/terminal01
```

Invocation method: `python -B -c` prints its PID and effective command, sets the
above arguments/import directory, then uses `runpy.run_path(..., run_name="__main__")`
in that same process. Frozen audit code is not modified or copied.
This records invocation only; actual terminal acceptance and command exit must
be established from the subsequent output, not inferred here.
