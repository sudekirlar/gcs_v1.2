import shutil, subprocess, sys
import cv2

ELEMENTS = [
    "nvh264dec", "d3d11h264dec", "avdec_h264",
    "rtspsrc", "rtph264depay", "h264parse", "rtpjitterbuffer",
    "videoconvert", "videoscale", "appsink",
]

def run(cmd):
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    return p.returncode, p.stdout

def yesno(b): return "YES" if b else "NO"

def main():
    exe = shutil.which("gst-inspect-1.0")
    print("gst-inspect path:", exe)
    if not exe:
        print("ERROR: gst-inspect-1.0 not found in PATH")
        sys.exit(1)

    print("\n[GStreamer elements]")
    have = {}
    for e in ELEMENTS:
        rc, out = run([exe, e])
        ok = (rc == 0) and (e in (out or "").lower())
        have[e] = ok
        print(f"  {e:15s}: {yesno(ok)}")

    # OpenCV tarafı
    info = cv2.getBuildInformation()
    gst_flag = ("GStreamer:" in info and "YES" in info.split("GStreamer:",1)[1].splitlines()[0])
    print("\n[OpenCV]")
    print("  CAP_GSTREAMER build flag:", yesno(gst_flag))

    # (İsteğe bağlı) minicik bir pipeline'ı açabiliyor muyuz?
    # GStreamer doğru yoldaysa bu da YES olmalı:
    test_pipe = "videotestsrc num-buffers=1 ! videoconvert ! video/x-raw,format=BGR ! appsink"
    cap = cv2.VideoCapture(test_pipe, cv2.CAP_GSTREAMER)
    print("  OpenCV can open a trivial GStreamer pipeline:", yesno(cap.isOpened()))
    if cap.isOpened():
        cap.release()

    print("\n[Summary]")
    if not have.get("rtspsrc") or not have.get("rtph264depay") or not have.get("appsink"):
        print("  CRITICAL: RTSP için temel elemanlar eksik görünüyor.")
    if not (have.get("nvh264dec") or have.get("d3d11h264dec")):
        print("  WARN: GPU decoder bulunamadı; decode CPU'ya düşer.")
    else:
        which = "NVDEC" if have.get("nvh264dec") else "D3D11"
        print(f"  OK: GPU decoder mevcut ({which}).")

if __name__ == "__main__":
    main()
