# Sadece döngü hızı: read + upload + cuda.resize (download YOK)
# Konsola FPS basar, pencere yok.
import cv2, time, collections
from pathlib import Path

VIDEO = Path(r"C:\Users\SUDE\Desktop\gcs_v1.2\source_videos\test2.mp4")
cap = cv2.VideoCapture(str(VIDEO), cv2.CAP_FFMPEG)
assert cap.isOpened()

assert cv2.cuda.getCudaEnabledDeviceCount() > 0
gpu_src = cv2.cuda_GpuMat()

times = collections.deque()
t_end = time.time() + 10.0  # 5 sn ölç
w_target, h_target = 1280, 720

while time.time() < t_end:
    ok, frame = cap.read()
    if not ok: break
    gpu_src.upload(frame)
    _ = cv2.cuda.resize(gpu_src, (w_target, h_target))
    t = time.perf_counter()
    times.append(t)
    while times and (t - times[0]) > 1.0:
        times.popleft()

fps = len(times) / max((times[-1] - times[0]), 1e-6) if len(times) > 1 else 0.0
print(f"Throughput (no display, no download): {fps:0.1f} FPS")
cap.release()
