import os, cv2

# GENEL ŞABLON (HER YERDE OLACAK.)
gst_bin = r"C:\Program Files\gstreamer\1.0\msvc_x86_64\bin"
if hasattr(os, "add_dll_directory"):
    os.add_dll_directory(gst_bin)
os.environ.pop("GST_PLUGIN_PATH", None)

# UDP/RTP H.264 ALICI PIPELINE
pipeline = (
    "udpsrc port=5000 ! "
    "application/x-rtp, media=video, encoding-name=H264, payload=96, clock-rate=90000 ! "
    "rtpjitterbuffer latency=0 drop-on-latency=true ! "
    "rtph264depay ! h264parse ! "
    # Donanım decode (NVDEC). İstersen avdec_h264'a düşebilirsin:
    "nvh264dec disable-dx11=1 ! "
    "videoconvert ! video/x-raw,format=BGR ! "
    "appsink drop=true max-buffers=1 sync=false"
)

cap = cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)
if not cap.isOpened():
    print("Pipeline açılmadı!")
    raise SystemExit

while True:
    ok, frame = cap.read()
    if not ok:
        print("Frame alınamadı!")
        break
    cv2.imshow("UDP Stream (Jetson → PC)", frame)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()
