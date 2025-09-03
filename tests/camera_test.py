import cv2

pipeline = (
    "udpsrc port=5000 caps=application/x-rtp,encoding-name=H264,payload=96 ! "
    "rtph264depay ! avdec_h264 ! videoconvert ! appsink"
)

cap = cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)

if not cap.isOpened():
    print("Pipeline açılmadı!")
    exit()

while True:
    ret, frame = cap.read()
    if not ret:
        print("Frame alınamadı!")
        break

    cv2.imshow("UDP Stream", frame)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()