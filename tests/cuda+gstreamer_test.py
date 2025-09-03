import os, cv2, time, collections
from pathlib import Path

# --- GStreamer DLL yolu ---
GST_BIN = r"C:\Program Files\gstreamer\1.0\msvc_x86_64\bin"
if hasattr(os, "add_dll_directory"):
    os.add_dll_directory(GST_BIN)

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

# --- CUDA kontrolü ---
if cv2.cuda.getCudaEnabledDeviceCount() <= 0:
    raise SystemExit("CUDA destekli OpenCV gerekli.")

cap = cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)
if not cap.isOpened():
    raise SystemExit("GStreamer pipeline açılamadı.")

print("Açıldı (CUDA resize + latency ölçümü). 'q' ile çık.")

# --- FPS ölçümü ---
times = collections.deque()
last_report = time.perf_counter()
avg_fps = 0.0

# --- Ekran çözünürlüğü ---
screen_w, screen_h = 1280, 720

# --- CUDA buffer'ları ---
gpu_src = cv2.cuda_GpuMat()

while True:
    t_capture = time.perf_counter()
    ok, frame = cap.read()
    if not ok:
        print("Frame alınamadı / EOS.")
        break

    # ---- CUDA: upload & resize (aspect koru) ----
    h, w = frame.shape[:2]
    scale = min(screen_w / w, screen_h / h)
    new_w, new_h = int(w * scale), int(h * scale)

    gpu_src.upload(frame)
    gpu_resized = cv2.cuda.resize(gpu_src, (new_w, new_h), interpolation=cv2.INTER_AREA)
    frame_resized = gpu_resized.download()

    t_done = time.perf_counter()
    latency_ms = (t_done - t_capture) * 1000.0

    # ---- FPS hesapla (1 sn pencere) ----
    times.append(t_done)
    while times and (t_done - times[0]) > 1.0:
        times.popleft()
    if times:
        avg_fps = len(times) / max(t_done - times[0], 1e-6)

    # Overlay FPS + latency
    txt = f"FPS: {avg_fps:5.1f} | Latency: {latency_ms:4.1f} ms"
    cv2.putText(frame_resized, txt, (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.8,
                (0, 0, 0), 2, cv2.LINE_AA)

    # Pencere başlığı
    if (t_done - last_report) >= 1.0:
        cv2.setWindowTitle("GStreamer + CUDA", f"GStreamer + CUDA  |  {txt}")
        print(txt)
        last_report = t_done

    cv2.imshow("GStreamer + CUDA", frame_resized)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()
