import socket

host = '10.194.139.194'
port = 8554  # RTSP port

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.settimeout(5)  # 5 saniye timeout

try:
    sock.connect((host, port))
    print("TCP bağlantısı başarılı!")
except socket.timeout:
    print("TCP bağlantısı timeout oldu.")
except Exception as e:
    print("Hata:", e)
finally:
    sock.close()