import cv2

# RTSP linkini kendi mediamtx adresine göre ayarla
# Örnek: rtsp://<ubuntu_ip>:8554/mystream
# rtsp_url = "rtsp://192.168.1.50:8554/mystream"
rtsp_url = "rtsp://10.194.139.96:8554/cam1"

# RTSP yayını aç
cap = cv2.VideoCapture(rtsp_url)

if not cap.isOpened():
    print("RTSP bağlantısı kurulamadı!")
    exit()

while True:
    ret, frame = cap.read()
    if not ret:
        print("Frame alınamadı!")
        break

    # Görüntüyü göster
    cv2.imshow("RTSP Stream", frame)

    # q tuşuna basınca çıkış
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()