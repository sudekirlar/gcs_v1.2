
import cv2, re
info = cv2.getBuildInformation()
print(info.splitlines()[:30])  # üst başlık
print("\n== CUDA ==")
print([l for l in info.splitlines() if "CUDA" in l or "cuDNN" in l])
print("\n== GStreamer ==")
print([l for l in info.splitlines() if "GStreamer" in l])