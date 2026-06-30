from __future__ import annotations

import json


OWNER_GROUP_HELPERS = """
user_cache = {}
group_cache = {}

def owner_name(uid):
    if uid not in user_cache:
        try:
            user_cache[uid] = pwd.getpwuid(uid).pw_name
        except KeyError:
            user_cache[uid] = str(uid)
    return user_cache[uid]

def group_name(gid):
    if gid not in group_cache:
        try:
            group_cache[gid] = grp.getgrgid(gid).gr_name
        except KeyError:
            group_cache[gid] = str(gid)
    return group_cache[gid]
""".strip()


def list_directory_script(safe_path: str) -> str:
    return f"""
import json
import os
import grp
import pwd
import stat
import sys

path = {json.dumps(safe_path, ensure_ascii=False)}
{OWNER_GROUP_HELPERS}

try:
    current = os.path.abspath(os.path.expanduser(path))
    entries = []
    with os.scandir(current) as iterator:
        for entry in iterator:
            try:
                info = entry.stat(follow_symlinks=False)
            except OSError:
                continue
            mode_bits = info.st_mode
            if stat.S_ISDIR(mode_bits):
                kind = "dir"
            elif stat.S_ISLNK(mode_bits):
                kind = "link"
            elif stat.S_ISREG(mode_bits):
                kind = "file"
            else:
                kind = "other"
            owner = owner_name(info.st_uid)
            group = group_name(info.st_gid)
            size = -1 if kind == "dir" else int(info.st_size)
            entries.append({{
                "name": entry.name,
                "path": os.path.join(current, entry.name),
                "kind": kind,
                "size": size,
                "mtime": float(info.st_mtime),
                "mode": stat.filemode(mode_bits),
                "owner": owner,
                "group": group,
            }})
    entries.sort(key=lambda item: (item["kind"] != "dir", item["name"].lower()))
    print("DOG_REMOTE_FILE_BEGIN")
    print(json.dumps({{"current": current, "items": entries}}, ensure_ascii=False))
    print("DOG_REMOTE_FILE_END")
except Exception as exc:
    print("DOG_REMOTE_FILE_BEGIN")
    print(json.dumps({{"error": str(exc), "current": path, "items": []}}, ensure_ascii=False))
    print("DOG_REMOTE_FILE_END")
    sys.exit(2)
"""


def search_directory_script(safe_path: str, keyword: str, recursive: bool = False) -> str:
    return f"""
import itertools
import json
import os
import grp
import pwd
import stat
import sys

root = {json.dumps(safe_path, ensure_ascii=False)}
keyword = {json.dumps(keyword, ensure_ascii=False)}.lower()
recursive = {str(bool(recursive))}
limit = 500
{OWNER_GROUP_HELPERS}

def item_from_path(parent, name):
    path = os.path.join(parent, name)
    info = os.lstat(path)
    mode_bits = info.st_mode
    if stat.S_ISDIR(mode_bits):
        kind = "dir"
    elif stat.S_ISLNK(mode_bits):
        kind = "link"
    elif stat.S_ISREG(mode_bits):
        kind = "file"
    else:
        kind = "other"
    owner = owner_name(info.st_uid)
    group = group_name(info.st_gid)
    size = -1 if kind == "dir" else int(info.st_size)
    return {{
        "name": name,
        "path": path,
        "kind": kind,
        "size": size,
        "mtime": float(info.st_mtime),
        "mode": stat.filemode(mode_bits),
        "owner": owner,
        "group": group,
    }}

try:
    current = os.path.abspath(os.path.expanduser(root))
    entries = []
    if keyword:
        if recursive:
            for parent, dirs, files in os.walk(current):
                for name in itertools.chain(dirs, files):
                    if keyword in name.lower():
                        try:
                            entries.append(item_from_path(parent, name))
                        except OSError:
                            pass
                    if len(entries) >= limit:
                        break
                if len(entries) >= limit:
                    break
        else:
            with os.scandir(current) as iterator:
                for entry in iterator:
                    if keyword in entry.name.lower():
                        try:
                            entries.append(item_from_path(current, entry.name))
                        except OSError:
                            pass
    entries.sort(key=lambda item: (item["kind"] != "dir", item["path"].lower()))
    print("DOG_REMOTE_FILE_BEGIN")
    print(json.dumps({{"current": current, "items": entries, "limited": len(entries) >= limit}}, ensure_ascii=False))
    print("DOG_REMOTE_FILE_END")
except Exception as exc:
    print("DOG_REMOTE_FILE_BEGIN")
    print(json.dumps({{"error": str(exc), "current": root, "items": []}}, ensure_ascii=False))
    print("DOG_REMOTE_FILE_END")
    sys.exit(2)
"""


def preview_file_script(safe_path: str, max_bytes: int = 131_072) -> str:
    return f"""
import json
import os
import sys

path = {json.dumps(safe_path, ensure_ascii=False)}
limit = {max_bytes}
try:
    if not os.path.isfile(path):
        raise RuntimeError("不是普通文件")
    size = os.path.getsize(path)
    with open(path, "rb") as handle:
        data = handle.read(limit + 1)
    if b"\\0" in data[:limit]:
        raise RuntimeError("疑似二进制文件，未预览")
    text = data[:limit].decode("utf-8", errors="replace")
    payload = {{"path": path, "size": size, "truncated": len(data) > limit, "text": text}}
    print("DOG_REMOTE_PREVIEW_BEGIN")
    print(json.dumps(payload, ensure_ascii=False))
    print("DOG_REMOTE_PREVIEW_END")
except Exception as exc:
    print("DOG_REMOTE_PREVIEW_BEGIN")
    print(json.dumps({{"path": path, "error": str(exc), "text": ""}}, ensure_ascii=False))
    print("DOG_REMOTE_PREVIEW_END")
    sys.exit(2)
"""
