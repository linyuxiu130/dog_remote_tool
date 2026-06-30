from __future__ import annotations

import textwrap


def nav_speed_reader_python(config_path: str, prefix: str = "YAML_") -> str:
    return textwrap.dedent(
        f"""
        from pathlib import Path
        path = Path({config_path!r})
        values = {{}}
        stack = []
        for raw in path.read_text(errors='ignore').splitlines():
            if not raw.strip() or raw.lstrip().startswith('#'):
                continue
            indent = len(raw) - len(raw.lstrip(' '))
            stripped = raw.strip()
            while stack and indent <= stack[-1][0]:
                stack.pop()
            if stripped.endswith(':'):
                stack.append((indent, stripped[:-1]))
                continue
            if ':' in stripped and [item[1] for item in stack[-3:]] == ['speed', 'noload', 'nav']:
                key, value = stripped.split(':', 1)
                values[key.strip()] = value.strip()
        for key in ('vertical_move', 'horizontal_move', 'yaw'):
            print(f'{prefix}{{key}}={{values.get(key, "--")}}')
        """
    ).strip()
