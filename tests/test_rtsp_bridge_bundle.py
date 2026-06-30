from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RTSP_BRIDGE_DIR = ROOT / "resources" / "rtsp_bridge" / "ubuntu22.04-arm64"


def test_rtsp_bridge_bundle_keeps_only_packages_missing_from_zg_rk3588_image():
    keep_file = RTSP_BRIDGE_DIR / "bundle-keep.txt"
    keep = {
        line.strip()
        for line in keep_file.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    }

    assert keep == {
        "python3-gst-1.0",
        "gir1.2-gst-rtsp-server-1.0",
        "gstreamer1.0-plugins-ugly",
        "liba52-0.7.4",
        "libmpeg2-4",
        "libopencore-amrnb0",
        "libopencore-amrwb0",
        "libsidplay1v5",
    }
    for package in keep:
        assert list((RTSP_BRIDGE_DIR / "debs").glob(f"{package}_*.deb")), package


def test_release_bundle_includes_minimal_rtsp_debs_by_default():
    script = (ROOT / "build" / "build_release.sh").read_text(encoding="utf-8")

    assert 'INCLUDE_RTSP_DEBS="${DOG_REMOTE_BUNDLE_RTSP_DEBS:-1}"' in script
