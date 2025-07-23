import cv2

cap = cv2.VideoCapture("source_videos/test2.mp4")

frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT)
duration_sec = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000  # Bu 0'dır başta
fps = cap.get(cv2.CAP_PROP_FPS)

# Daha güvenli: Toplam kare sayısını ve süresini al
duration = cap.get(cv2.CAP_PROP_FRAME_COUNT) / cap.get(cv2.CAP_PROP_FPS) if fps > 0 else -1

print("Frame count:", frame_count)
print("FPS (OpenCV):", fps)
print("Duration (sec):", duration)

cap.release()
