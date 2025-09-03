import cv2, re, sys
print("cv2 file:", cv2.__file__)
print("OpenCV:", cv2.__version__)
print(re.search(r"GStreamer:\s+(\w+)", cv2.getBuildInformation()).group(0))
