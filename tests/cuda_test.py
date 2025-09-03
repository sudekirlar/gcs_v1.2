import cv2, time, collections
from pathlib import Path

# --- Test videosu (dosya) ---
VIDEO = Path(r"C:\Users\SUDE\Desktop\gcs_v1.2\source_videos\newest_test.mp4")
assert VIDEO.exists(), f"Dosya yok: {VIDEO}"

# --- Sadece FFmpeg backend ile aç (GStreamer yok) ---
cap = cv2.VideoCapture(str(VIDEO), cv2.CAP_FFMPEG)
if not cap.isOpened():
    raise SystemExit("Video açılamadı (FFmpeg).")

# --- CUDA kontrolü ---
try:
    HAS_CUDA = cv2.cuda.getCudaEnabledDeviceCount() > 0
except Exception:
    HAS_CUDA = False
if not HAS_CUDA:
    raise SystemExit("CUDA destekli OpenCV gerekli (cv2.cuda.*).")

print("Açıldı (FFmpeg + CUDA). 'q' ile çık.")

# --- Ölçüm penceresi & hedef ekran sığdırma ---
times = collections.deque()
last_print = time.perf_counter()
screen_w, screen_h = 1280, 720   # istersen 1920,1080

# --- CUDA buffer ---
gpu_src = cv2.cuda_GpuMat()

def draw_hud(img, lines, x=10, y=10, pad=6, line_h=24):
    # sol üstte siyah şeffaf kutu + gri yazı (düşük bütçeli HUD)
    max_w = max(cv2.getTextSize(t, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)[0][0] for t in lines)
    overlay = img.copy()
    cv2.rectangle(overlay, (x, y), (x + max_w + pad*2, y + line_h*len(lines) + pad*2), (0, 0, 0), -1)
    cv2.addWeighted(overlay, 0.6, img, 0.4, 0, img)
    for i, t in enumerate(lines):
        ty = y + pad + (i+1)*line_h - 6
        cv2.putText(img, t, (x+pad, ty), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (220,220,220), 2, cv2.LINE_AA)

while True:
    t0 = time.perf_counter()
    ok, frame = cap.read()
    if not ok:
        print("Frame alınamadı / EOS")
        break

    # --- CUDA ile ekrana sığdır (aspect korunur) ---
    h, w = frame.shape[:2]
    scale = min(screen_w / w, screen_h / h)
    new_w, new_h = int(w * scale), int(h * scale)

    gpu_src.upload(frame)
    frame_resized = cv2.cuda.resize(gpu_src, (new_w, new_h), interpolation=cv2.INTER_AREA).download()

    # --- İşlem gecikmesi (capture→display pipeline süresi) ---
    t1 = time.perf_counter()
    latency_ms = (t1 - t0) * 1000.0

    # --- FPS (son 1 sn pencere) ---
    times.append(t1)
    while times and (t1 - times[0]) > 1.0:
        times.popleft()
    fps = len(times) / max(t1 - times[0], 1e-6) if times else 0.0

    # --- HUD ---
    draw_hud(frame_resized, [f"FPS: {fps:5.1f}", f"Latency: {latency_ms:4.1f} ms"])

    # Pencere başlığı (isteğe bağlı log)
    if (t1 - last_print) >= 1.0:
        cv2.setWindowTitle("FFmpeg + CUDA", f"FFmpeg + CUDA  |  FPS {fps:5.1f} | Lat {latency_ms:4.1f} ms")
        print(f"FPS {fps:5.1f} | Lat {latency_ms:4.1f} ms")
        last_print = t1

    cv2.imshow("FFmpeg + CUDA", frame_resized)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()
