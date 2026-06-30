from __future__ import annotations

from dog_remote_tool.core.shell import quote


def ensure_fifo_helper_inner(
    *,
    prefix: str,
    script_path: str,
    pid_file: str,
    fifo_path: str,
    log_path: str,
    script: str,
    failure_message: str,
) -> str:
    helper = quote(script)
    return (
        f"{prefix}_PID_FILE={quote(pid_file)}; "
        f"{prefix}_SCRIPT={quote(script_path)}; "
        f"{prefix}_FIFO={quote(fifo_path)}; "
        f"{prefix}_LOG={quote(log_path)}; "
        f"{prefix}_PID=$(cat \"${prefix}_PID_FILE\" 2>/dev/null || true); "
        f"if [ -n \"${prefix}_PID\" ] && kill -0 \"${prefix}_PID\" 2>/dev/null && [ -p \"${prefix}_FIFO\" ]; then "
        "true; "
        "else "
        f"if [ -n \"${prefix}_PID\" ]; then kill \"${prefix}_PID\" 2>/dev/null || true; fi; "
        f"printf '%s' {helper} > \"${prefix}_SCRIPT\"; "
        f"chmod +x \"${prefix}_SCRIPT\"; "
        f"rm -f \"${prefix}_FIFO\"; "
        f"nohup python3 \"${prefix}_SCRIPT\" >> \"${prefix}_LOG\" 2>&1 & "
        f"{prefix}_PID=$!; echo \"${prefix}_PID\" > \"${prefix}_PID_FILE\"; "
        "for _ in 1 2 3 4 5 6 7 8 9 10; do "
        f"if kill -0 \"${prefix}_PID\" 2>/dev/null && [ -p \"${prefix}_FIFO\" ]; then break; fi; "
        "sleep 0.2; "
        "done; "
        f"if kill -0 \"${prefix}_PID\" 2>/dev/null && [ -p \"${prefix}_FIFO\" ]; then "
        "true; "
        "else "
        f"echo {quote(failure_message)}; "
        f"tail -20 \"${prefix}_LOG\" 2>/dev/null || true; "
        "exit 7; "
        "fi; "
        "fi; "
    )
