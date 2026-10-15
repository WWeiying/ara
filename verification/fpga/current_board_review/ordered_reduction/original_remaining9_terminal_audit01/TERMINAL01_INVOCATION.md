# Authorized Offline Audit Invocation

The parent explicitly authorized one terminal audit after batch completion.
Actual auditing Python PID printed by the process: **1006545**.
No simulator or reference was launched. No automatic retry is authorized.

Effective audit command and `sys.argv`:

```sh
/usr/bin/python -B /home/wangwy/openproject/ara_dsa_signoff_integration/verification/fpga/current_board_review/ordered_reduction/original_remaining9_terminal_audit01/audit.py terminal --authorize-terminal-audit --prepared-sha256 0eae1de4381ab00d1f76203b1c39cfbfd8e3c59747ee4dc7763323bcd7341154 --complete-sha256 d2b57da8b703fb5e301e3c584856be1d802bb5b0c688c72accef715e531330bc --out /home/wangwy/openproject/ara_dsa_signoff_integration/verification/fpga/current_board_review/ordered_reduction/original_remaining9_terminal_audit01/terminal01
```

Invocation method: `python -B -c` prints `os.getpid()` and the effective command,
sets the above `sys.argv` and the audit import directory, then calls
`runpy.run_path(sys.argv[0], run_name="__main__")` in that same PID. It does not
modify or copy the frozen audit code. The execution tool returned session35772.
This invocation record is not an acceptance result. See subsequent terminal01
output or a preserved failure report for the actual outcome.
