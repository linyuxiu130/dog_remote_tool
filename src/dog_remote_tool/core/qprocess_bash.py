from __future__ import annotations

from PyQt5.QtCore import QProcess


BASH_ARG_COMMAND_LIMIT = 60 * 1024


def configure_bash_process(process: QProcess, command: str, *, login_shell: bool = True) -> None:
    process.setProgram("bash")
    if len(command.encode("utf-8")) <= BASH_ARG_COMMAND_LIMIT:
        process.setArguments(["-lc" if login_shell else "-c", command])
        return
    process.setArguments(["-l", "-s"] if login_shell else ["-s"])
    process.started.connect(lambda p=process, script=command: write_stdin_script(p, script))


def write_stdin_script(process: QProcess, script: str) -> None:
    try:
        process.write(script.encode("utf-8"))
        if not script.endswith("\n"):
            process.write(b"\n")
        process.closeWriteChannel()
    except RuntimeError:
        pass
