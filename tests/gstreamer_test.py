import os, cv2, time, collections
from pathlib import Path

# --- GStreamer DLL yolu ---
GST_BIN = r"C:\Program Files\gstreamer\1.0\msvc_x86_64\bin"
if hasattr(os, "add_dll_directory"):
    os.add_dll_directory(GST_BIN)

# NVDEC'i tercih et, yazılım decoder'ı geri plana at
os.environ["GST_PLUGIN_FEATURE_RANK"] = ";".join([
    "nvh264dec:MAX", "nvh265dec:MAX",
    "avdec_h264:LOW", "avdec_h265:LOW"
])
os.environ.pop("GST_PLUGIN_PATH", None)

# --- Video URI ---
VIDEO = Path(r"C:\Users\SUDE\Desktop\gcs_v1.2\source_videos\test2.mp4")
assert VIDEO.exists(), f"Dosya yok: {VIDEO}"
URI = VIDEO.as_uri()

pipeline = (
    f"uridecodebin uri={URI} expose-all-streams=false ! "
    "videoconvert ! video/x-raw,format=BGR ! "
    "appsink drop=true max-buffers=1 sync=false"
)

cap = cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)
if not cap.isOpened():
    print("GStreamer pipeline açılamadı.")
    raise SystemExit

print("Açıldı. 'q' ile çık.")

# --- FPS ölçümü ---
times = collections.deque()
last_report = time.perf_counter()
avg_fps = 0.0

# --- Ekran çözünürlüğü ---
screen_w, screen_h = 1280, 720

while True:
    t0 = time.perf_counter()
    ok, frame = cap.read()
    if not ok:
        print("Frame alınamadı / EOS.")
        break

    # FPS hesapla
    t1 = time.perf_counter()
    times.append(t1)
    while times and (t1 - times[0]) > 1.0:
        times.popleft()
    if times:
        avg_fps = len(times) / max(t1 - times[0], 1e-6)

    # Overlay FPS
    txt = f"FPS: {avg_fps:5.1f}"
    cv2.putText(frame, txt, (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.8,
                (20, 230, 20), 2, cv2.LINE_AA)

    # --- Frame'i ekrana sığdır ---
    h, w = frame.shape[:2]
    scale = min(screen_w / w, screen_h / h)
    new_w, new_h = int(w * scale), int(h * scale)
    frame_resized = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_AREA)

    # Pencere başlığına FPS yaz
    if (t1 - last_report) >= 1.0:
        cv2.setWindowTitle("GStreamer Video", f"GStreamer Video | {txt}")
        print(txt)
        last_report = t1

    cv2.imshow("GStreamer Video", frame_resized)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()
