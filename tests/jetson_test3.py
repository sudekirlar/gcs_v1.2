import os, cv2, time, collections

# --- GStreamer DLL yolu (Windows) ---
GST_BIN = r"C:\Program Files\gstreamer\1.0\msvc_x86_64\bin"
if hasattr(os, "add_dll_directory"):
    os.add_dll_directory(GST_BIN)

# NVDEC'i tercih et; yazılım dekoderi geri plana at
os.environ["GST_PLUGIN_FEATURE_RANK"] = "nvh264dec:MAX;avdec_h264:LOW"
os.environ.pop("GST_PLUGIN_PATH", None)

# --- Jetson UDP/RTP H.264 alıcı pipeline (NVDEC) ---
pipeline = (
    "udpsrc port=5000 ! "
    "application/x-rtp,media=video,encoding-name=H264,payload=96,clock-rate=90000 ! "
    "rtpjitterbuffer latency=0 drop-on-latency=true ! "
    "rtph264depay ! h264parse ! "
    "nvh264dec disable-dx11=1 ! "
    "videoconvert ! video/x-raw,format=BGR ! "
    "appsink drop=true max-buffers=1 sync=false"
)

cap = cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)
if not cap.isOpened():
    raise SystemExit("Pipeline açılmadı! (UDP 5000 firewall açık mı? Jetson stream gönderiyor mu?)")

print("Açıldı (Jetson UDP, NVDEC). 'q' ile çık.")

# --- FPS & işlem-gecikmesi ölçümü ---
times = collections.deque()
last_report = time.perf_counter()
avg_fps = 0.0

# --- Pencere/ekran hedef boyutu (aspect korunur) ---
screen_w, screen_h = 1280, 720  # istersen 1920,1080 yap

# --- Basit siyah HUD kutusu çizici ---
def draw_hud(img, lines, x=10, y=10, pad=6, line_h=24):
    # siyah arka plan kutusu
    max_w = max(cv2.getTextSize(t, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)[0][0] for t in lines)
    box_w = max_w + pad*2
    box_h = line_h*len(lines) + pad*2
    overlay = img.copy()
    cv2.rectangle(overlay, (x, y), (x+box_w, y+box_h), (0,0,0), -1)
    # hafif şeffaflık
    cv2.addWeighted(overlay, 0.6, img, 0.4, 0, img)
    # metinleri yaz
    for i, t in enumerate(lines):
        ty = y + pad + (i+1)*line_h - 6
        cv2.putText(img, t, (x+pad, ty), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (220,220,220), 2, cv2.LINE_AA)

while True:
    t_capture = time.perf_counter()
    ok, frame = cap.read()
    if not ok:
        print("Frame alınamadı!")
        break

    # ---- İşlem gecikmesi (capture→display path) ----
    t_after_read = time.perf_counter()  # decode + appsink’ten sonra
    proc_latency_ms = (t_after_read - t_capture) * 1000.0

    # ---- FPS (son 1 sn penceresi) ----
    times.append(t_after_read)
    while times and (t_after_read - times[0]) > 1.0:
        times.popleft()
    if times:
        avg_fps = len(times) / max(t_after_read - times[0], 1e-6)

    # ---- Ekrana sığdır (aspect korunur) ----
    h, w = frame.shape[:2]
    scale = min(screen_w / w, screen_h / h)
    new_w, new_h = int(w * scale), int(h * scale)
    frame_out = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_AREA)

    # ---- Sol üstte düşük bütçeli (siyah) HUD: FPS + gecikme ----
    hud_lines = [
        f"FPS: {avg_fps:5.1f}",
        f"Latency: {proc_latency_ms:4.1f} ms"
    ]
    draw_hud(frame_out, hud_lines, x=10, y=10)

    # Pencere başlığına da yaz
    if (t_after_read - last_report) >= 1.0:
        cv2.setWindowTitle("UDP Stream (Jetson → PC, NVDEC)",
                           f"UDP Stream (NVDEC)  |  FPS {avg_fps:5.1f}  |  Lat {proc_latency_ms:4.1f} ms")
        last_report = t_after_read

    cv2.imshow("UDP Stream (Jetson → PC, NVDEC)", frame_out)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()
