import ast
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_release_bundle_drops_platform_tool_deb_cache():
    script = (ROOT / "build" / "build_release.sh").read_text(encoding="utf-8")

    assert 'rm -rf "$BUNDLE/resources/platform-tools/linux-x86_64/debs"' in script


def test_release_bundle_drops_numpy_development_files():
    script = (ROOT / "build" / "build_release.sh").read_text(encoding="utf-8")

    assert '"$USR_DIR/lib/python3/dist-packages/numpy/distutils"' in script
    assert '"$USR_DIR/lib/python3/dist-packages/numpy/f2py"' in script
    assert '"$USR_DIR/lib/python3/dist-packages/numpy/testing"' in script


def test_release_bundle_keeps_qt_print_support_for_route_pdf_export():
    script = (ROOT / "build" / "build_release.sh").read_text(encoding="utf-8")

    assert "QtPrintSupport.*.so" not in script


def test_release_bundle_does_not_prune_imported_pyqt_modules():
    script = (ROOT / "build" / "build_release.sh").read_text(encoding="utf-8")
    pruned = set(re.findall(r"Qt[A-Za-z]+(?=\.\*\.so)", script))
    imported = set()
    for path in (ROOT / "src").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[1] for alias in node.names if alias.name.startswith("PyQt5."))
            elif isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("PyQt5."):
                imported.add(node.module.split(".")[1])

    assert imported.isdisjoint(pruned)


def test_release_build_outputs_single_run_file():
    script = (ROOT / "build" / "build_release.sh").read_text(encoding="utf-8")

    assert "cat > \"$OUT_DIR/启动DogRemoteTool.sh\"" not in script
    assert "cat > \"$OUT_DIR/DogRemoteTool.desktop\"" not in script
