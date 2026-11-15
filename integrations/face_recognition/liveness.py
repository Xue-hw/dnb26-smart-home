"""
认人 + 眨眼活体检测
流程:认出是授权者(绿框) → 检测到眨眼 → 判定真人 → PASS开门
照片:能认出脸但不会眨眼 → 判定FAKE → 拒绝
按 q 退出。
"""
import face_recognition
import cv2
import dlib
import pickle
import numpy as np
from scipy.spatial import distance as dist

# ---------- 配置 ----------
DB_FILE = "known_faces.pkl"
PREDICTOR_PATH = "shape_predictor_68_face_landmarks.dat"
TOLERANCE = 0.45          # 认人松紧度
EAR_THRESHOLD = 0.23      # 低于此值算"闭眼"(可调)
EAR_CONSEC_FRAMES = 2     # 连续几帧闭眼才算一次有效眨眼

# ---------- 加载已注册人脸 ----------
with open(DB_FILE, "rb") as f:
    data = pickle.load(f)
known_encodings = data["encodings"]
known_names = data["names"]
print(f"已加载授权者: {known_names}")

# ---------- 加载关键点检测器 ----------
detector = dlib.get_frontal_face_detector()
predictor = dlib.shape_predictor(PREDICTOR_PATH)

# 68点里,左右眼各6个点的编号
LEFT_EYE = list(range(42, 48))
RIGHT_EYE = list(range(36, 42))

def eye_aspect_ratio(eye):
    """计算眼睛纵横比 EAR:睁眼时大,闭眼时小"""
    A = dist.euclidean(eye[1], eye[5])
    B = dist.euclidean(eye[2], eye[4])
    C = dist.euclidean(eye[0], eye[3])
    return (A + B) / (2.0 * C)

# ---------- 状态变量 ----------
blink_counter = 0        # 连续闭眼帧计数
total_blinks = 0         # 累计眨眼次数
is_live = False          # 是否已确认为真人

cap = cv2.VideoCapture(0)
print("摄像头已开启。请对着镜头眨眨眼。按 q 退出。")

while True:
    ret, frame = cap.read()
    if not ret:
        break

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

    # 用 dlib 找脸(用于眨眼关键点)
    faces = detector(gray, 0)

    for face in faces:
        # --- 1. 认这个人是谁 ---
        top, right, bottom, left = face.top(), face.right(), face.bottom(), face.left()
        name = "Unknown"
        encs = face_recognition.face_encodings(rgb, [(top, right, bottom, left)])
        if encs and known_encodings:
            distances = face_recognition.face_distance(known_encodings, encs[0])
            best = np.argmin(distances)
            if distances[best] < TOLERANCE:
                name = known_names[best]

        # --- 2. 眨眼检测 ---
        shape = predictor(gray, face)
        coords = np.array([[shape.part(i).x, shape.part(i).y] for i in range(68)])
        left_eye = coords[LEFT_EYE]
        right_eye = coords[RIGHT_EYE]
        ear = (eye_aspect_ratio(left_eye) + eye_aspect_ratio(right_eye)) / 2.0

        if ear < EAR_THRESHOLD:
            blink_counter += 1
        else:
            if blink_counter >= EAR_CONSEC_FRAMES:
                total_blinks += 1
                is_live = True     # 眨过眼,确认真人
            blink_counter = 0

        # --- 3. 判定与显示 ---
        if name != "Unknown" and is_live:
            color, label = (0, 255, 0), f"{name} PASS (real)"
        elif name != "Unknown" and not is_live:
            color, label = (0, 165, 255), f"{name}? blink to verify"
        else:
            color, label = (0, 0, 255), "Unknown DENY"

        cv2.rectangle(frame, (left, top), (right, bottom), color, 2)
        cv2.putText(frame, label, (left, top - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
        cv2.putText(frame, f"EAR:{ear:.2f} blinks:{total_blinks}",
                    (left, bottom + 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)

    cv2.imshow("Liveness - press q to quit", frame)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()