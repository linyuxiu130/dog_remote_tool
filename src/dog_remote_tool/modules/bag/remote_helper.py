from __future__ import annotations

import base64
import json
import os
import shlex

from dog_remote_tool.modules.bag.names import safe_filename_component


HELPER_PATH = "/tmp/dog_remote_bag_helper.py"
HELPER_DIR = "/tmp/dog_remote_bag_helper"
HELPER_VERSION = "1"


def helper_script() -> str:
    return f"""#!/usr/bin/env python3
import json
import os
import re
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

VERSION = {HELPER_VERSION!r}
ROOT = Path({HELPER_DIR!r})
ROOT.mkdir(mode=0o700, exist_ok=True)


def safe_name(value):
    safe = ''.join(c if c.isalnum() or c in '._-' else '_' for c in value)
    return safe.strip('._-') or 'record'


def state_path(name):
    return ROOT / (safe_name(name) + '.json')


def read_state(name):
    try:
        return json.loads(state_path(name).read_text())
    except Exception:
        return {{}}


def write_state(name, data):
    path = state_path(name)
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, separators=(',', ':')))
    os.replace(tmp, path)


def proc_state(pid):
    try:
        parts = Path(f'/proc/{{pid}}/stat').read_text().split()
        return parts[2] if len(parts) > 2 else ''
    except FileNotFoundError:
        return ''


def alive(pid):
    state = proc_state(pid)
    return bool(state and state != 'Z')


def cmdline(pid):
    try:
        raw = Path(f'/proc/{{pid}}/cmdline').read_bytes()
    except FileNotFoundError:
        return ''
    return raw.replace(b'\\0', b' ').decode('utf-8', errors='replace')


def record_pids_for_paths(paths):
    found = []
    for entry in Path('/proc').iterdir():
        if not entry.name.isdigit():
            continue
        pid = int(entry.name)
        text = cmdline(pid)
        if not text or 'ros2 bag record' not in text:
            continue
        if any(output_arg_matches(text, path) for path in paths):
            found.append(pid)
    return found


def output_arg_matches(text, path):
    if not path:
        return False
    patterns = (f' -o {{path}}', f' -o={{path}}', f' --output {{path}}', f' --output={{path}}')
    return any(has_arg_boundary(text, pattern) for pattern in patterns)


def has_arg_boundary(text, pattern):
    start = text.find(pattern)
    while start >= 0:
        end = start + len(pattern)
        if end >= len(text) or text[end] in (' ', '\\t'):
            return True
        start = text.find(pattern, start + 1)
    return False


def bag_size(path):
    root = Path(path)
    total = 0
    for pattern in ('*.mcap', '*.db3'):
        for item in root.glob(pattern):
            try:
                total += item.stat().st_size
            except OSError:
                pass
    return total


def bag_status(path):
    root = Path(path)
    return {{
        'exists': 1 if root.is_dir() else 0,
        'active': len(record_pids_for_paths([path])),
        'meta': 1 if (root / 'metadata.yaml').is_file() and (root / 'metadata.yaml').stat().st_size > 0 else 0,
        'size': bag_size(path),
    }}


def print_json(data):
    print(json.dumps(data, ensure_ascii=False, separators=(',', ':')), flush=True)


def start(argv):
    if len(argv) < 4 or '--' not in argv:
        raise SystemExit('usage: start NAME PATHS_JSON -- COMMAND...')
    name = argv[1]
    paths = json.loads(argv[2])
    sep = argv.index('--')
    command = argv[sep + 1:]
    if not command:
        raise SystemExit('missing command')
    state = read_state(name)
    pid = int(state.get('pid') or 0)
    if pid and alive(pid):
        state['running'] = True
        write_state(name, state)
        print_json({{'ok': True, 'already_running': True, 'pid': pid, 'log': state.get('log', '')}})
        return
    log_path = str(ROOT / (safe_name(name) + '.log'))
    output = open(log_path, 'ab', buffering=0)
    process = subprocess.Popen(
        command,
        stdout=output,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
    )
    state = {{
        'version': VERSION,
        'name': name,
        'pid': process.pid,
        'pgid': process.pid,
        'paths': paths,
        'command': command,
        'log': log_path,
        'started_at': time.time(),
        'running': True,
    }}
    write_state(name, state)
    print_json({{'ok': True, 'pid': process.pid, 'log': log_path}})


def stop(argv):
    if len(argv) < 3:
        raise SystemExit('usage: stop NAME PATHS_JSON [TIMEOUT]')
    name = argv[1]
    paths = json.loads(argv[2])
    timeout = float(argv[3]) if len(argv) > 3 else 6.0
    state = read_state(name)
    pid = int(state.get('pid') or 0)
    if not pid or not alive(pid):
        pids = record_pids_for_paths(paths)
        if pids:
            pid = pids[0]
            state.update({{'pid': pid, 'pgid': pid, 'paths': paths, 'running': True}})
    if not pid or not alive(pid):
        state['running'] = False
        write_state(name, state)
        print_json({{'ok': True, 'running': False, 'already_stopped': True}})
        return
    try:
        os.killpg(int(state.get('pgid') or pid), signal.SIGINT)
    except ProcessLookupError:
        try:
            os.kill(pid, signal.SIGINT)
        except ProcessLookupError:
            pass
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not alive(pid):
            state['running'] = False
            state['stopped_at'] = time.time()
            write_state(name, state)
            print_json({{'ok': True, 'running': False, 'signal': 'SIGINT'}})
            return
        time.sleep(0.05)
    state['running'] = True
    state['stop_requested_at'] = time.time()
    write_state(name, state)
    print_json({{'ok': True, 'running': True, 'signal': 'SIGINT', 'deferred': True}})


def status(argv):
    if len(argv) < 2:
        raise SystemExit('usage: status NAME')
    name = argv[1]
    state = read_state(name)
    pid = int(state.get('pid') or 0)
    state['running'] = bool(pid and alive(pid))
    write_state(name, state)
    print_json(state)


def status_paths(argv):
    if len(argv) < 2:
        raise SystemExit('usage: status-paths PATHS_JSON')
    for path in json.loads(argv[1]):
        status = bag_status(path)
        print(f"{{path}}\\texists={{status['exists']}} active={{status['active']}} meta={{status['meta']}} size={{status['size']}}")


def scan(argv):
    if len(argv) < 2:
        raise SystemExit('usage: scan DIRS_JSON')
    scan_dirs = json.loads(argv[1])
    base_dir = scan_dirs[0] if scan_dirs else ''
    try:
        stat = os.statvfs(base_dir)
        available = stat.f_bavail * stat.f_frsize
        total = stat.f_blocks * stat.f_frsize
        print(f"__DISK__\\t{{available}}\\t{{total}}\\t{{base_dir}}")
    except OSError:
        print(f"__DISK_ERROR__\\t{{base_dir}}")
    name_pattern = re.compile(r'^(?:rosbag2_)?(?:xg|zg|air|l2)_\\d{{8}}_\\d{{6}}$', re.I)
    rows = []
    for parent in scan_dirs:
        root = Path(parent)
        if not root.is_dir():
            continue
        try:
            children = list(root.iterdir())
        except OSError:
            continue
        for child in children:
            if not child.is_dir() or not name_pattern.match(child.name):
                continue
            try:
                epoch = child.stat().st_mtime
            except OSError:
                continue
            rows.append((epoch, str(child)))
    rows.sort(reverse=True)
    for epoch, path in rows[:100]:
        status = bag_status(path)
        mtime = datetime.fromtimestamp(epoch).strftime('%Y-%m-%d %H:%M')
        print(f"{{epoch}}\\t{{mtime}}\\t{{status['size']}}\\t{{status['active']}}\\t{{path}}")


def sizes(argv):
    if len(argv) < 2:
        raise SystemExit('usage: sizes PATHS_JSON')
    total = sum(bag_size(path) for path in json.loads(argv[1]))
    print(total)


def main():
    commands = {{'start': start, 'stop': stop, 'status': status, 'status-paths': status_paths, 'scan': scan, 'sizes': sizes}}
    command = sys.argv[1] if len(sys.argv) > 1 else ''
    if command not in commands:
        raise SystemExit('usage: start|stop|status|status-paths|scan|sizes')
    commands[command](sys.argv[1:])


if __name__ == '__main__':
    main()
"""


def install_helper_command() -> str:
    encoded = base64.b64encode(helper_script().encode("utf-8")).decode("ascii")
    return (
        "python3 - <<'DOG_REMOTE_INSTALL_HELPER'\n"
        "import base64, pathlib\n"
        f"path = pathlib.Path({HELPER_PATH!r})\n"
        f"path.write_bytes(base64.b64decode({encoded!r}))\n"
        "path.chmod(0o700)\n"
        "print(path)\n"
        "DOG_REMOTE_INSTALL_HELPER\n"
    )


def recording_name(remote_bag_paths: list[str]) -> str:
    first = remote_bag_paths[0] if remote_bag_paths else "record"
    return safe_filename_component(os.path.basename(first.rstrip("/")), "record")


def start_recording_command(script: str, remote_bag_paths: list[str]) -> str:
    name = recording_name(remote_bag_paths)
    script_path = f"{HELPER_DIR}/{name}.sh"
    paths_json = json.dumps(remote_bag_paths, ensure_ascii=False, separators=(",", ":"))
    return (
        f"{install_helper_command()}"
        f"mkdir -p {shlex.quote(HELPER_DIR)}; "
        f"cat > {shlex.quote(script_path)} <<'DOG_REMOTE_RECORD_SCRIPT'\n"
        f"{script}\n"
        "DOG_REMOTE_RECORD_SCRIPT\n"
        f"chmod 700 {shlex.quote(script_path)}; "
        f"python3 {shlex.quote(HELPER_PATH)} start {shlex.quote(name)} {shlex.quote(paths_json)} -- bash {shlex.quote(script_path)}"
    )


def stop_recording_command(remote_bag_paths: list[str], timeout_seconds: float = 6.0) -> str:
    name = recording_name(remote_bag_paths)
    paths_json = json.dumps(remote_bag_paths, ensure_ascii=False, separators=(",", ":"))
    return (
        f"{install_helper_command()}"
        f"python3 {shlex.quote(HELPER_PATH)} stop {shlex.quote(name)} {shlex.quote(paths_json)} {shlex.quote(str(timeout_seconds))}"
    )


def status_recording_command(remote_bag_paths: list[str]) -> str:
    name = recording_name(remote_bag_paths)
    return (
        f"{install_helper_command()}"
        f"python3 {shlex.quote(HELPER_PATH)} status {shlex.quote(name)}"
    )


def status_paths_command(remote_paths: list[str]) -> str:
    paths_json = json.dumps(remote_paths, ensure_ascii=False, separators=(",", ":"))
    return (
        f"{install_helper_command()}"
        f"python3 {shlex.quote(HELPER_PATH)} status-paths {shlex.quote(paths_json)}"
    )


def scan_command(scan_dirs: list[str]) -> str:
    dirs_json = json.dumps(scan_dirs, ensure_ascii=False, separators=(",", ":"))
    return (
        f"{install_helper_command()}"
        f"python3 {shlex.quote(HELPER_PATH)} scan {shlex.quote(dirs_json)}"
    )


def sizes_command(remote_paths: list[str]) -> str:
    paths_json = json.dumps(remote_paths, ensure_ascii=False, separators=(",", ":"))
    return (
        f"{install_helper_command()}"
        f"python3 {shlex.quote(HELPER_PATH)} sizes {shlex.quote(paths_json)}"
    )


def parse_helper_json(output: str) -> dict:
    for line in reversed(output.splitlines()):
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            continue
    return {}
