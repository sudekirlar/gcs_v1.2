import cv2, os, time, collections
import numpy as np

# rtsp://KULLANICI:PAROLA@JETSON_IP:8554/stream  (auth yoksa kullanıcı/parola kısmını çıkar)
RTSP_URL = "rtsp://<JETSON_IP>:8554/test"   # ör: rtsp://192.168.1.50:8554/test

# OpenCV'yi FFmpeg backend ile zorla (GStreamer yok!)
cap = cv2.VideoCapture(RTSP_URL, cv2.CAP_FFMPEG)
if not cap.isOpened():
    raise SystemExit("RTSP açılamadı (FFmpeg). URL/firewall kontrol et.")

print("RTSP (FFmpeg) + CUDA HUD. 'q' ile çık.")
times = collections.deque()
screen_w, screen_h = 1280, 720

# CUDA var mı?
has_cuda = False
try:
    has_cuda = cv2.cuda.getCudaEnabledDeviceCount() > 0
except Exception:
    pass
gpu_mat = cv2.cuda_GpuMat() if has_cuda else None

def draw_hud(img, lines, x=10, y=10, pad=6, line_h=24):
    max_w = max(cv2.getTextSize(t, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)[0][0] for t in lines)
    box = img.copy()
    cv2.rectangle(box, (x,y), (x+max_w+pad*2, y+line_h*len(lines)+pad*2), (0,0,0), -1)
    cv2.addWeighted(box, 0.6, img, 0.4, 0, img)
    for i, t in enumerate(lines):
        ty = y + pad + (i+1)*line_h - 6
        cv2.putText(img, t, (x+pad, ty), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (220,220,220), 2, cv2.LINE_AA)

last_print = time.perf_counter()
while True:
    t0 = time.perf_counter()
    ok, frame = cap.read()
    if not ok:
        print("Frame alınamadı / EOS"); break

    # --- CUDA ile ekrana sığdır (opsiyonel) ---
    h, w = frame.shape[:2]
    scale = min(screen_w / w, screen_h / h)
    new_w, new_h = int(w*scale), int(h*scale)
    if has_cuda:
        gpu_mat.upload(frame)
        frame = cv2.cuda.resize(gpu_mat, (new_w, new_h), interpolation=cv2.INTER_AREA).download()
    else:
        frame = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_AREA)

    t1 = time.perf_counter()
    proc_latency_ms = (t1 - t0) * 1000.0

    # FPS (1 sn pencere)
    times.append(t1)
    while times and (t1 - times[0]) > 1.0: times.popleft()
    fps = len(times) / max(t1 - times[0], 1e-6)

    draw_hud(frame, [f"FPS: {fps:5.1f}", f"Latency: {proc_latency_ms:4.1f} ms"])

    if (t1 - last_print) >= 1.0:
        cv2.setWindowTitle("RTSP (FFmpeg)", f"RTSP (FFmpeg) | FPS {fps:5.1f} | Lat {proc_latency_ms:4.1f} ms")
        print(f"FPS {fps:5.1f} | Lat {proc_latency_ms:4.1f} ms")
        last_print = t1

    cv2.imshow("RTSP (FFmpeg)", frame)
    if cv2.waitKey(1) & 0xFF == ord('q'): break

cap.release(); cv2.destroyAllWindows()
