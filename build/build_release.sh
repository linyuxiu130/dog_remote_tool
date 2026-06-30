#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION="$(tr -d '[:space:]' < "$ROOT/VERSION")"
CACHE_VERSION="${VERSION}_$(date +%Y%m%d%H%M%S)"
BUILD_ROOT="$ROOT/.build"
BUNDLE="$BUILD_ROOT/dog_remote_tool_bundle"
APP_DIR="$BUNDLE/app"
USR_DIR="$BUNDLE/usr"
OUT_DIR="$ROOT/release"
OUT="$OUT_DIR/DogRemoteTool-v${VERSION}-x86_64.run"
RUN_BASENAME="$(basename "$OUT")"
LEGACY_OUT="$OUT_DIR/DogRemoteTool-x86_64.run"
INCLUDE_RTSP_DEBS="${DOG_REMOTE_BUNDLE_RTSP_DEBS:-1}"
INCLUDE_ALL_GSTREAMER="${DOG_REMOTE_BUNDLE_GSTREAMER_ALL:-0}"
INCLUDE_QT_NATIVE_THEME="${DOG_REMOTE_BUNDLE_QT_NATIVE_THEME:-0}"
INCLUDE_OPENCV="${DOG_REMOTE_BUNDLE_OPENCV:-1}"
STRIP_RUNTIME="${DOG_REMOTE_BUNDLE_STRIP:-1}"
PAYLOAD_COMPRESSION="${DOG_REMOTE_BUNDLE_COMPRESSION:-xz}"

case "$PAYLOAD_COMPRESSION" in
  xz)
    PAYLOAD_SUFFIX="tar.xz"
    TAR_EXTRACT_FLAG="-xJf"
    ;;
  gzip)
    PAYLOAD_SUFFIX="tar.gz"
    TAR_EXTRACT_FLAG="-xzf"
    ;;
  *)
    printf '[ERROR] unsupported DOG_REMOTE_BUNDLE_COMPRESSION: %s\n' "$PAYLOAD_COMPRESSION" >&2
    printf '[ERROR] supported values: xz, gzip\n' >&2
    exit 1
    ;;
esac

require_command() {
  local name="$1"
  if ! command -v "$name" >/dev/null 2>&1; then
    printf '[ERROR] missing required build command: %s\n' "$name" >&2
    exit 1
  fi
}

for cmd in python3 readlink gcc tar ldd file awk find cp rm mkdir chmod date du sha256sum wc; do
  require_command "$cmd"
done
if [[ "$PAYLOAD_COMPRESSION" = "xz" ]]; then
  require_command xz
fi
for tool in ssh sshpass scp rsync; do
  require_command "$tool"
done

PYTHON_BIN="$(command -v python3)"
PYTHON_REAL="$(readlink -f "$PYTHON_BIN")"
PYVER="$("$PYTHON_BIN" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
if [[ "$PYVER" != "3.10" ]]; then
  printf '[ERROR] DogRemoteTool release must be built with Python 3.10, got %s\n' "$PYVER" >&2
  exit 1
fi
STDLIB="$("$PYTHON_BIN" -c 'import sysconfig; print(sysconfig.get_path("stdlib"))')"
PY_DYNLOAD="$STDLIB/lib-dynload"
PY_DIST="$("$PYTHON_BIN" -c 'import sysconfig; print(sysconfig.get_path("platlib"))')"
PYQT_DIR="$("$PYTHON_BIN" -c 'import pathlib, PyQt5; print(pathlib.Path(PyQt5.__file__).resolve().parent)' 2>/dev/null || true)"
if [[ -z "$PYQT_DIR" ]]; then
  printf '[ERROR] PyQt5 is required to build DogRemoteTool release\n' >&2
  exit 1
fi
QT_PLUGIN_DIR="$("$PYTHON_BIN" -c 'from PyQt5.QtCore import QLibraryInfo; print(QLibraryInfo.location(QLibraryInfo.PluginsPath))')"
GST_PLUGIN_DIR="$(pkg-config --variable=pluginsdir gstreamer-1.0 2>/dev/null || true)"
if [[ -z "$GST_PLUGIN_DIR" || ! -d "$GST_PLUGIN_DIR" ]]; then
  GST_PLUGIN_DIR="/usr/lib/x86_64-linux-gnu/gstreamer-1.0"
fi
GST_PLUGIN_SCANNER="$(pkg-config --variable=pluginscannerdir gstreamer-1.0 2>/dev/null || true)"
if [[ -n "$GST_PLUGIN_SCANNER" && -d "$GST_PLUGIN_SCANNER" ]]; then
  GST_PLUGIN_SCANNER="$GST_PLUGIN_SCANNER/gst-plugin-scanner"
elif [[ ! -x "$GST_PLUGIN_SCANNER" ]]; then
  GST_PLUGIN_SCANNER="/usr/lib/x86_64-linux-gnu/gstreamer1.0/gstreamer-1.0/gst-plugin-scanner"
fi
if [[ "$INCLUDE_OPENCV" = "1" && ( ! -d "$GST_PLUGIN_DIR" || ! -f "$GST_PLUGIN_DIR/libgstlibav.so" ) ]]; then
  printf '[ERROR] GStreamer libav plugin is required: install gstreamer1.0-libav\n' >&2
  exit 1
fi
if [[ "$INCLUDE_OPENCV" = "1" && ! -x "$GST_PLUGIN_SCANNER" ]]; then
  printf '[ERROR] GStreamer plugin scanner is required: %s\n' "$GST_PLUGIN_SCANNER" >&2
  exit 1
fi

rm -rf "$BUNDLE"
mkdir -p "$APP_DIR/lib" "$USR_DIR/bin" "$USR_DIR/lib" "$USR_DIR/libexec" "$USR_DIR/lib/python3/dist-packages" "$OUT_DIR"
rm -f "$LEGACY_OUT" "$OUT_DIR/启动DogRemoteTool.sh" "$OUT_DIR/DogRemoteTool.desktop"

compile_app() {
  "$PYTHON_BIN" - "$ROOT/src" "$APP_DIR/lib" "$BUILD_ROOT/run_app.py" "$APP_DIR/run.pyc" <<'PY'
import pathlib
import py_compile
import sys

src_root = pathlib.Path(sys.argv[1]).resolve()
dst_root = pathlib.Path(sys.argv[2]).resolve()
launcher_src = pathlib.Path(sys.argv[3]).resolve()
launcher_pyc = pathlib.Path(sys.argv[4]).resolve()

for src in src_root.rglob("*.py"):
    rel = src.relative_to(src_root).with_suffix(".pyc")
    dst = dst_root / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    py_compile.compile(str(src), cfile=str(dst), dfile=str(src.relative_to(src_root)), doraise=True)

launcher_src.parent.mkdir(parents=True, exist_ok=True)
launcher_src.write_text(
    "from dog_remote_tool.app import main\n"
    "raise SystemExit(main())\n",
    encoding="utf-8",
)
py_compile.compile(str(launcher_src), cfile=str(launcher_pyc), dfile="app/run.py", doraise=True)
PY
}

copy_runtime() {
  cp -aL "$PYTHON_REAL" "$USR_DIR/bin/python3"
  cp -aL "$STDLIB" "$USR_DIR/lib/"
  rm -rf "$USR_DIR/lib/python$PYVER/test" "$USR_DIR/lib/python$PYVER/__pycache__"
  find "$USR_DIR/lib/python$PYVER" -type d -name '__pycache__' -prune -exec rm -rf {} +

  mkdir -p "$USR_DIR/lib/python3/dist-packages"
  cp -aL "$PYQT_DIR" "$USR_DIR/lib/python3/dist-packages/"
  find "$USR_DIR/lib/python3/dist-packages/PyQt5" -type f \( -name '*.pyi' -o -name 'py.typed' \) -delete
  find "$USR_DIR/lib/python3/dist-packages/PyQt5" -maxdepth 1 -type f \
    \( -name 'QtDBus.*.so' -o -name 'QtDesigner.*.so' -o -name 'QtHelp.*.so' \
       -o -name 'QtNetwork.*.so' -o -name 'QtSvg.*.so' \
       -o -name 'QtTest.*.so' -o -name 'QtXml.*.so' \) -delete
  "$PYTHON_BIN" - "$USR_DIR/lib/python3/dist-packages" "$INCLUDE_OPENCV" <<'PY'
import importlib.util
import pathlib
import shutil
import sys

dst = pathlib.Path(sys.argv[1])
include_opencv = sys.argv[2] == "1"
names = ["sip", "PyQt5_sip", "yaml", "_yaml", "PIL"]
if include_opencv:
    names.extend(["numpy", "cv2"])
for name in names:
    spec = importlib.util.find_spec(name)
    if not spec:
        continue
    if spec.submodule_search_locations:
        origin = pathlib.Path(next(iter(spec.submodule_search_locations)))
    elif spec.origin:
        origin = pathlib.Path(spec.origin)
    else:
        continue
    target = dst / origin.name
    if origin.is_dir():
        shutil.copytree(origin, target, dirs_exist_ok=True)
    else:
        shutil.copy2(origin, target)
PY

  mkdir -p "$USR_DIR/lib/qt5/plugins"
  cp -aL "$QT_PLUGIN_DIR/platforms" "$USR_DIR/lib/qt5/plugins/"
  for optional in imageformats iconengines xcbglintegrations; do
    if [[ -d "$QT_PLUGIN_DIR/$optional" ]]; then
      cp -aL "$QT_PLUGIN_DIR/$optional" "$USR_DIR/lib/qt5/plugins/"
    fi
  done
  if [[ "$INCLUDE_QT_NATIVE_THEME" = "1" ]]; then
    for optional in platformthemes styles; do
      if [[ -d "$QT_PLUGIN_DIR/$optional" ]]; then
        cp -aL "$QT_PLUGIN_DIR/$optional" "$USR_DIR/lib/qt5/plugins/"
      fi
    done
  fi
}

copy_cli_tools() {
  for tool in ssh sshpass scp rsync; do
    cp -aL "$(command -v "$tool")" "$USR_DIR/bin/$tool"
  done
}

copy_gstreamer_runtime() {
  mkdir -p "$USR_DIR/lib/gstreamer-1.0" "$USR_DIR/libexec/gstreamer-1.0"
  [[ "$INCLUDE_OPENCV" = "1" ]] || return 0
  if [[ "$INCLUDE_ALL_GSTREAMER" = "1" ]]; then
    cp -aL "$GST_PLUGIN_DIR"/*.so "$USR_DIR/lib/gstreamer-1.0/"
  else
    for plugin in \
      libgstapp.so \
      libgstcoreelements.so \
      libgstlibav.so \
      libgstrtp.so \
      libgstrtpmanager.so \
      libgstrtsp.so \
      libgsttcp.so \
      libgsttypefindfunctions.so \
      libgstudp.so \
      libgstvideoconvert.so \
      libgstvideoparsersbad.so \
      libgstvideoscale.so; do
      if [[ -f "$GST_PLUGIN_DIR/$plugin" ]]; then
        cp -aL "$GST_PLUGIN_DIR/$plugin" "$USR_DIR/lib/gstreamer-1.0/"
      fi
    done
  fi
  cp -aL "$GST_PLUGIN_SCANNER" "$USR_DIR/libexec/gstreamer-1.0/gst-plugin-scanner"
}

install_dep() {
  local src="$1"
  [[ -f "$src" ]] || return 0
  local base
  base="$(basename "$src")"
  case "$base" in
    libc.so.*|libm.so.*|libpthread.so.*|libdl.so.*|librt.so.*|libutil.so.*|libresolv.so.*|libgcc_s.so.*|ld-linux-*.so.*)
      return 0
      ;;
  esac
  cp -aL "$src" "$USR_DIR/lib/$base" 2>/dev/null || true
}

collect_deps_for() {
  local target="$1"
  ldd "$target" 2>/dev/null | awk '
    /=>/ && $3 ~ /^\// { print $3 }
    $1 ~ /^\// { print $1 }
  ' | while read -r dep; do
    install_dep "$dep"
  done
}

collect_deps() {
  local previous_count current_count
  previous_count=-1
  current_count=0
  while [[ "$current_count" != "$previous_count" ]]; do
    previous_count="$current_count"
    find "$USR_DIR/bin" "$USR_DIR/lib" "$USR_DIR/libexec" -type f | while read -r target; do
      if file "$target" 2>/dev/null | grep -Eq 'ELF .* (executable|shared object|pie executable)'; then
        collect_deps_for "$target"
      fi
    done
    current_count="$(find "$USR_DIR/lib" -maxdepth 1 -type f \( -name '*.so' -o -name '*.so.*' \) | wc -l)"
  done
}

prune_runtime() {
  find "$USR_DIR" -type d -name '__pycache__' -prune -exec rm -rf {} +
  find "$USR_DIR" -type f \( -name '*.pyc' -o -name '*.pyo' -o -name '*.pyi' -o -name 'py.typed' \) -delete
  rm -rf \
    "$USR_DIR/lib/python$PYVER/test" \
    "$USR_DIR/lib/python$PYVER/tests" \
    "$USR_DIR/lib/python$PYVER/idlelib" \
    "$USR_DIR/lib/python$PYVER/tkinter" \
    "$USR_DIR/lib/python$PYVER/turtledemo" \
    "$USR_DIR/lib/python$PYVER/ensurepip" \
    "$USR_DIR/lib/python$PYVER/venv" \
    "$USR_DIR/lib/python$PYVER/lib2to3" \
    "$USR_DIR/lib/python$PYVER/pydoc_data" \
    "$USR_DIR/lib/python$PYVER/unittest" \
    "$USR_DIR/lib/python$PYVER/distutils"
  find "$USR_DIR/lib/python$PYVER/config-"* -type f \
    \( -name '*.a' -o -name 'python.o' -o -name 'Makefile' -o -name 'Setup*' -o -name 'config.c' \) \
    -delete 2>/dev/null || true
  find "$USR_DIR/lib/python$PYVER/lib-dynload" -maxdepth 1 -type f \
    \( -name '_tkinter*.so' -o -name '_sqlite3*.so' -o -name '_curses*.so' \
       -o -name '_curses_panel*.so' -o -name '_dbm*.so' -o -name '_gdbm*.so' \
       -o -name '_test*.so' -o -name '_ctypes_test*.so' \) -delete
  rm -rf \
    "$USR_DIR/lib/python3/dist-packages/numpy/distutils" \
    "$USR_DIR/lib/python3/dist-packages/numpy/f2py" \
    "$USR_DIR/lib/python3/dist-packages/numpy/testing" \
    "$USR_DIR/lib/python3/dist-packages/numpy/tests" \
    "$USR_DIR/lib/python3/dist-packages/numpy/doc"
}

strip_runtime() {
  [[ "$STRIP_RUNTIME" = "1" ]] || return 0
  command -v strip >/dev/null 2>&1 || return 0
  find "$USR_DIR/bin" "$USR_DIR/lib" "$USR_DIR/libexec" -type f | while read -r target; do
    if file "$target" 2>/dev/null | grep -Eq 'ELF .* (executable|shared object|pie executable)'; then
      strip --strip-unneeded "$target" >/dev/null 2>&1 || true
    fi
  done
}

copy_resources() {
  [[ -d "$ROOT/resources" ]] || return 0
  cp -a "$ROOT/resources" "$BUNDLE/resources"
  rm -rf "$BUNDLE/resources/platform-tools/linux-x86_64/debs"
  if [[ "$INCLUDE_RTSP_DEBS" != "1" ]]; then
    rm -rf "$BUNDLE/resources/rtsp_bridge"
  else
    local rtsp_dir="$BUNDLE/resources/rtsp_bridge/ubuntu22.04-arm64"
    local keep_file="$rtsp_dir/bundle-keep.txt"
    if [[ -f "$keep_file" && -d "$rtsp_dir/debs" ]]; then
      find "$rtsp_dir/debs" -maxdepth 1 -type f -name '*.deb' | while read -r deb; do
        local package
        package="$(basename "$deb")"
        package="${package%%_*}"
        if ! grep -Fxq "$package" "$keep_file"; then
          rm -f "$deb"
        fi
      done
    fi
  fi
  find "$BUNDLE/resources" -type d -name '__pycache__' -prune -exec rm -rf {} +
  find "$BUNDLE/resources" -type f -name '*.pyc' -delete
}

write_apprun() {
  cat > "$BUNDLE/AppRun" <<EOF
#!/usr/bin/env bash
set -euo pipefail

ROOT="\$(cd "\$(dirname "\${BASH_SOURCE[0]}")" && pwd)"
export DOG_REMOTE_TOOL_ROOT="\$ROOT"
export DOG_REMOTE_TOOL_PYTHON="\$ROOT/usr/bin/python3"
export PYTHONHOME="\$ROOT/usr"
export PYTHONPATH="\$ROOT/app/lib:\$ROOT/usr/lib/python3/dist-packages"
export QT_PLUGIN_PATH="\$ROOT/usr/lib/qt5/plugins"
export QT_QPA_PLATFORM_PLUGIN_PATH="\$ROOT/usr/lib/qt5/plugins/platforms"
export GST_PLUGIN_PATH_1_0="\$ROOT/usr/lib/gstreamer-1.0"
export GST_PLUGIN_SYSTEM_PATH_1_0="\$ROOT/usr/lib/gstreamer-1.0"
export GST_PLUGIN_SCANNER="\$ROOT/usr/libexec/gstreamer-1.0/gst-plugin-scanner"
mkdir -p "\$ROOT/.cache/gstreamer-1.0"
export GST_REGISTRY_1_0="\$ROOT/.cache/gstreamer-1.0/registry.bin"
export LD_LIBRARY_PATH="\$ROOT/usr/lib\${LD_LIBRARY_PATH:+:\$LD_LIBRARY_PATH}"
export PATH="\$ROOT/usr/bin:\$PATH"

exec "\$ROOT/usr/bin/python3" "\$ROOT/app/run.pyc" "\$@"
EOF
  chmod 755 "$BUNDLE/AppRun"
}

write_run_file() {
  local payload="$BUILD_ROOT/dog_remote_tool_bundle.$PAYLOAD_SUFFIX"
  local launcher_src="$BUILD_ROOT/self_extract_launcher.c"
  local launcher_bin="$BUILD_ROOT/DogRemoteTool-launcher"

  rm -f "$BUILD_ROOT"/dog_remote_tool_bundle.tar.gz "$BUILD_ROOT"/dog_remote_tool_bundle.tar.xz
  if [[ "$PAYLOAD_COMPRESSION" = "xz" ]]; then
    tar -C "$BUILD_ROOT" -cf - dog_remote_tool_bundle | xz -T0 -6 -c > "$payload"
  else
    tar -czf "$payload" -C "$BUILD_ROOT" dog_remote_tool_bundle
  fi
  cat > "$launcher_src" <<'EOF'
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>

#ifndef VERSION_TEXT
#define VERSION_TEXT "0.0.0"
#endif
#ifndef TAR_EXTRACT_FLAG
#define TAR_EXTRACT_FLAG "-xJf"
#endif

static int mkdir_p(const char *path) {
    char tmp[4096];
    size_t len = strlen(path);
    if (len >= sizeof(tmp)) return -1;
    strcpy(tmp, path);
    for (char *p = tmp + 1; *p; ++p) {
        if (*p == '/') {
            *p = '\0';
            if (mkdir(tmp, 0700) != 0 && errno != EEXIST) return -1;
            *p = '/';
        }
    }
    if (mkdir(tmp, 0700) != 0 && errno != EEXIST) return -1;
    return 0;
}

static int stream_payload(int in_fd, off_t start, off_t end, int out_fd) {
    if (lseek(in_fd, start, SEEK_SET) < 0) return -1;
    char buffer[1 << 20];
    off_t remaining = end - start;
    while (remaining > 0) {
        ssize_t want = remaining > (off_t)sizeof(buffer) ? (ssize_t)sizeof(buffer) : (ssize_t)remaining;
        ssize_t nread = read(in_fd, buffer, (size_t)want);
        if (nread <= 0) return -1;
        char *ptr = buffer;
        ssize_t left = nread;
        while (left > 0) {
            ssize_t nwritten = write(out_fd, ptr, (size_t)left);
            if (nwritten <= 0) return -1;
            ptr += nwritten;
            left -= nwritten;
        }
        remaining -= nread;
    }
    return 0;
}

static int extract_payload(const char *self_path, uint64_t payload_offset, off_t payload_end, const char *cache_dir) {
    int pipe_fd[2];
    if (pipe(pipe_fd) != 0) return -1;
    pid_t pid = fork();
    if (pid < 0) return -1;
    if (pid == 0) {
        close(pipe_fd[1]);
        dup2(pipe_fd[0], STDIN_FILENO);
        close(pipe_fd[0]);
        execlp("tar", "tar", TAR_EXTRACT_FLAG, "-", "-C", cache_dir, (char *)NULL);
        _exit(127);
    }
    close(pipe_fd[0]);
    int self_fd = open(self_path, O_RDONLY);
    if (self_fd < 0) return -1;
    int rc = stream_payload(self_fd, (off_t)payload_offset, payload_end, pipe_fd[1]);
    close(self_fd);
    close(pipe_fd[1]);
    int status = 0;
    waitpid(pid, &status, 0);
    if (rc != 0 || !WIFEXITED(status) || WEXITSTATUS(status) != 0) return -1;
    return 0;
}

static int marker_matches(const char *path, const char *expected) {
    int fd = open(path, O_RDONLY);
    if (fd < 0) return 0;
    char buffer[512];
    ssize_t nread = read(fd, buffer, sizeof(buffer));
    close(fd);
    if (nread < 0) return 0;
    size_t expected_len = strlen(expected);
    return (size_t)nread == expected_len && memcmp(buffer, expected, expected_len) == 0;
}

static int write_marker(const char *path, const char *text) {
    int fd = open(path, O_WRONLY | O_CREAT | O_TRUNC, 0600);
    if (fd < 0) return -1;
    size_t total = strlen(text);
    const char *ptr = text;
    while (total > 0) {
        ssize_t nwritten = write(fd, ptr, total);
        if (nwritten <= 0) {
            close(fd);
            return -1;
        }
        ptr += nwritten;
        total -= (size_t)nwritten;
    }
    close(fd);
    return 0;
}

int main(int argc, char **argv) {
    char self_path[4096];
    ssize_t n = readlink("/proc/self/exe", self_path, sizeof(self_path) - 1);
    if (n <= 0) {
        perror("readlink");
        return 1;
    }
    self_path[n] = '\0';

    int self_fd = open(self_path, O_RDONLY);
    if (self_fd < 0) {
        perror("open");
        return 1;
    }
    struct stat st;
    if (fstat(self_fd, &st) != 0) {
        perror("fstat");
        close(self_fd);
        return 1;
    }
    uint64_t payload_offset = 0;
    if (lseek(self_fd, -(off_t)sizeof(payload_offset), SEEK_END) < 0 ||
        read(self_fd, &payload_offset, sizeof(payload_offset)) != (ssize_t)sizeof(payload_offset)) {
        fprintf(stderr, "invalid launcher payload\n");
        close(self_fd);
        return 1;
    }
    close(self_fd);
    if (st.st_size <= (off_t)sizeof(payload_offset) ||
        payload_offset == 0 ||
        payload_offset >= (uint64_t)(st.st_size - (off_t)sizeof(payload_offset))) {
        fprintf(stderr, "invalid launcher payload offset\n");
        return 1;
    }

    const char *xdg_cache = getenv("XDG_CACHE_HOME");
    const char *home = getenv("HOME");
    char cache_root[8192];
    if (xdg_cache && xdg_cache[0]) {
        snprintf(cache_root, sizeof(cache_root), "%s", xdg_cache);
    } else if (home && home[0]) {
        snprintf(cache_root, sizeof(cache_root), "%s/.cache", home);
    } else {
        snprintf(cache_root, sizeof(cache_root), "/tmp");
    }

    char cache_dir[16384];
    snprintf(
        cache_dir,
        sizeof(cache_dir),
        "%s/dog_remote_tool_%ld_%s_%llx_%llx",
        cache_root,
        (long)getuid(),
        VERSION_TEXT,
        (unsigned long long)payload_offset,
        (unsigned long long)st.st_size
    );
    if (mkdir_p(cache_dir) != 0) {
        perror("mkdir");
        return 1;
    }

    char app_run[8192];
    snprintf(app_run, sizeof(app_run), "%s/dog_remote_tool_bundle/AppRun", cache_dir);
    char marker_path[8192];
    snprintf(marker_path, sizeof(marker_path), "%s/.payload_marker", cache_dir);
    char marker[256];
    snprintf(
        marker,
        sizeof(marker),
        "version=%s\npayload_offset=%llu\nfile_size=%llu\n",
        VERSION_TEXT,
        (unsigned long long)payload_offset,
        (unsigned long long)st.st_size
    );
    if (access(app_run, X_OK) != 0 || !marker_matches(marker_path, marker)) {
        if (extract_payload(self_path, payload_offset, st.st_size - (off_t)sizeof(payload_offset), cache_dir) != 0) {
            fprintf(stderr, "failed to extract Remote Debug Platform payload\n");
            return 1;
        }
        if (write_marker(marker_path, marker) != 0) {
            fprintf(stderr, "failed to write Remote Debug Platform cache marker\n");
            return 1;
        }
    }
    if (access(app_run, X_OK) != 0) {
        fprintf(stderr, "Remote Debug Platform AppRun is missing after extraction\n");
        return 1;
    }

    char **new_argv = calloc((size_t)argc + 1, sizeof(char *));
    if (!new_argv) return 1;
    new_argv[0] = app_run;
    for (int i = 1; i < argc; ++i) new_argv[i] = argv[i];
    new_argv[argc] = NULL;
    execv(app_run, new_argv);
    perror("execv AppRun");
    return 1;
}
EOF
  gcc -O2 -DVERSION_TEXT="\"$CACHE_VERSION\"" -DTAR_EXTRACT_FLAG="\"$TAR_EXTRACT_FLAG\"" "$launcher_src" -o "$launcher_bin"
  cp "$launcher_bin" "$OUT"
  cat "$payload" >> "$OUT"
  python3 - "$OUT" "$launcher_bin" <<'PY'
import pathlib
import struct
import sys

out = pathlib.Path(sys.argv[1])
launcher = pathlib.Path(sys.argv[2])
offset = launcher.stat().st_size
with out.open("ab") as f:
    f.write(struct.pack("<Q", offset))
PY
  chmod 755 "$OUT"
}

write_manifest() {
  local manifest="$OUT_DIR/BUILD_MANIFEST.txt"
  {
    printf 'name=DogRemoteTool\n'
    printf 'version=%s\n' "$VERSION"
    printf 'cache_version=%s\n' "$CACHE_VERSION"
    printf 'built_at=%s\n' "$(date -Is)"
    printf 'target=Ubuntu 22.04 x86_64\n'
    printf 'python=%s\n' "$PYTHON_REAL"
    printf 'python_version=%s\n' "$PYVER"
    printf 'stdlib=%s\n' "$STDLIB"
    printf 'platlib=%s\n' "$PY_DIST"
    printf 'dynload=%s\n' "$PY_DYNLOAD"
    printf 'pyqt=%s\n' "$PYQT_DIR"
    printf 'qt_plugins=%s\n' "$QT_PLUGIN_DIR"
    printf 'gstreamer_plugins=%s\n' "$GST_PLUGIN_DIR"
    printf 'gstreamer_plugin_scanner=%s\n' "$GST_PLUGIN_SCANNER"
    if [[ "$INCLUDE_OPENCV" = "1" ]]; then
      printf 'included_gstreamer_plugin=libgstlibav.so\n'
    else
      printf 'included_gstreamer_plugin=\n'
    fi
    printf 'include_all_gstreamer=%s\n' "$INCLUDE_ALL_GSTREAMER"
    printf 'include_qt_native_theme=%s\n' "$INCLUDE_QT_NATIVE_THEME"
    printf 'include_opencv=%s\n' "$INCLUDE_OPENCV"
    printf 'include_rtsp_debs=%s\n' "$INCLUDE_RTSP_DEBS"
    printf 'strip_runtime=%s\n' "$STRIP_RUNTIME"
    printf 'payload_compression=%s\n' "$PAYLOAD_COMPRESSION"
    printf 'payload_suffix=%s\n' "$PAYLOAD_SUFFIX"
    printf 'resource_size=%s\n' "$(du -sh "$ROOT/resources" 2>/dev/null | awk '{print $1}')"
    printf 'bundle_size=%s\n' "$(du -sh "$BUNDLE" 2>/dev/null | awk '{print $1}')"
    printf 'run_file=%s\n' "$(basename "$OUT")"
    printf 'run_size_bytes=%s\n' "$(wc -c < "$OUT")"
    printf 'run_sha256=%s\n' "$(sha256sum "$OUT" | awk '{print $1}')"
    printf 'included_cli_tools=ssh sshpass scp rsync\n'
  } > "$manifest"
}

compile_app
copy_runtime
copy_cli_tools
copy_gstreamer_runtime
prune_runtime
collect_deps
strip_runtime
cp "$ROOT/README.md" "$APP_DIR/README.md"
cp "$ROOT/VERSION" "$APP_DIR/VERSION"
copy_resources
write_apprun
write_run_file

write_manifest

printf 'Release created: %s\n' "$OUT"
