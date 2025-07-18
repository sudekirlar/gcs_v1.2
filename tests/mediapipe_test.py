import cv2
import mediapipe as mp
import numpy as np
from enum import Enum
from collections import deque

# ==========================
# FSM Enum ve Sınıf
# ==========================

class PoseState(Enum):
    NO_PERSON = 0
    NEUTRAL = 1
    EQUAL = 2
    CROSS = 3

class PoseStateMachine:
    def __init__(self, stable_frame_threshold=5):
        self.state = PoseState.NO_PERSON
        self.state_queue = deque(maxlen=stable_frame_threshold)

    def update(self, current_state, person_detected):
        if not person_detected:
            self.state_queue.clear()
            self.state = PoseState.NO_PERSON
            return self.state

        self.state_queue.append(current_state)
        if len(self.state_queue) == self.state_queue.maxlen:
            if all(s == current_state for s in self.state_queue):
                self.state = current_state

        return self.state

# ==========================
# Yardımcı Fonksiyonlar
# ==========================

def orientation(p, q, r):
    val = (q[1] - p[1]) * (r[0] - q[0]) - (q[0] - p[0]) * (r[1] - q[1])
    if val == 0: return 0
    return 1 if val > 0 else 2

def do_segments_intersect(p1, q1, p2, q2):
    o1 = orientation(p1, q1, p2)
    o2 = orientation(p1, q1, q2)
    o3 = orientation(p2, q2, p1)
    o4 = orientation(p2, q2, q1)
    return o1 != o2 and o3 != o4

def is_cross_pose(landmarks):
    try:
        LE = landmarks[mp_pose.PoseLandmark.LEFT_ELBOW.value]
        LW = landmarks[mp_pose.PoseLandmark.LEFT_WRIST.value]
        RE = landmarks[mp_pose.PoseLandmark.RIGHT_ELBOW.value]
        RW = landmarks[mp_pose.PoseLandmark.RIGHT_WRIST.value]

        p1 = (LE.x, LE.y)
        q1 = (LW.x, LW.y)
        p2 = (RE.x, RE.y)
        q2 = (RW.x, RW.y)

        return do_segments_intersect(p1, q1, p2, q2)
    except:
        return False

def cosine_similarity(v1, v2):
    dot = np.dot(v1, v2)
    norm = np.linalg.norm(v1) * np.linalg.norm(v2)
    return dot / (norm + 1e-6)

def is_equal_pose(landmarks, similarity_threshold=0.8):
    try:
        LS = landmarks[mp_pose.PoseLandmark.LEFT_SHOULDER.value]
        RS = landmarks[mp_pose.PoseLandmark.RIGHT_SHOULDER.value]
        LE = landmarks[mp_pose.PoseLandmark.LEFT_ELBOW.value]
        LW = landmarks[mp_pose.PoseLandmark.LEFT_WRIST.value]
        RE = landmarks[mp_pose.PoseLandmark.RIGHT_ELBOW.value]
        RW = landmarks[mp_pose.PoseLandmark.RIGHT_WRIST.value]

        # Omuz vektörü (yatay referans)
        omuz_v = np.array([RS.x - LS.x, RS.y - LS.y])
        sol_kol_v = np.array([LW.x - LE.x, LW.y - LE.y])
        sag_kol_v = np.array([RW.x - RE.x, RW.y - RE.y])

        sol_sim = abs(cosine_similarity(sol_kol_v, omuz_v))
        sag_sim = abs(cosine_similarity(sag_kol_v, omuz_v))

        return sol_sim > similarity_threshold and sag_sim > similarity_threshold
    except:
        return False

# ==========================
# MediaPipe & Video
# ==========================

mp_pose = mp.solutions.pose
mp_drawing = mp.solutions.drawing_utils

video_file = r'C:\Users\SUDE\Desktop\gcs_v1.2\source_videos\test1.MP4'
cap = cv2.VideoCapture(video_file)

if not cap.isOpened():
    print(f"HATA: '{video_file}' video dosyası açılamadı.")
    exit()

fps = cap.get(cv2.CAP_PROP_FPS)
wait_time = int(1000 / fps) if fps > 0 else 33
pose_fsm = PoseStateMachine()

with mp_pose.Pose(min_detection_confidence=0.5, min_tracking_confidence=0.5) as pose_model:
    while cap.isOpened():
        success, image = cap.read()
        if not success:
            print("Video sonuna gelindi.")
            break

        image = cv2.resize(image, (1280, 720))
        image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        results = pose_model.process(image_rgb)

        try:
            landmarks = results.pose_landmarks.landmark
            is_crossed = is_cross_pose(landmarks)
            is_equal = is_equal_pose(landmarks)

            if is_crossed:
                temp_state = PoseState.CROSS
            elif is_equal:
                temp_state = PoseState.EQUAL
            else:
                temp_state = PoseState.NEUTRAL

            current_state = pose_fsm.update(temp_state, person_detected=True)

        except:
            current_state = pose_fsm.update(PoseState.NO_PERSON, person_detected=False)

        # Durum yazısı
        cv2.putText(image, f"STATE: {current_state.name}", (50, 50),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 0), 4)

        # İskelet çizimi
        if results.pose_landmarks:
            mp_drawing.draw_landmarks(
                image, results.pose_landmarks, mp_pose.POSE_CONNECTIONS,
                mp_drawing.DrawingSpec(color=(255, 255, 0), thickness=2, circle_radius=2),
                mp_drawing.DrawingSpec(color=(0, 0, 255), thickness=2, circle_radius=2)
            )

        cv2.imshow("FSM Pose Detection", image)
        if cv2.waitKey(wait_time) & 0xFF == 27:
            break

cap.release()
cv2.destroyAllWindows()
