"""
实时认人:打开摄像头,认识的人框绿色+名字,陌生人框红色+Unknown。
按 q 退出。
"""
import face_recognition
import cv2
import pickle
import numpy as np

DB_FILE = "known_faces.pkl"
TOLERANCE = 0.45   # 越小越严格(0.4~0.5之间调),太大易认错,太小易认不出

# 加载已注册的人脸
with open(DB_FILE, "rb") as f:
    data = pickle.load(f)
known_encodings = data["encodings"]
known_names = data["names"]
print(f"已加载 {len(known_names)} 个授权者: {known_names}")

cap = cv2.VideoCapture(0)
print("摄像头已开启,按 q 退出")

while True:
    ret, frame = cap.read()
    if not ret:
        break

    # 缩小画面加速处理(缩到 1/4)
    small = cv2.resize(frame, (0, 0), fx=0.25, fy=0.25)
    rgb_small = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)

    # 找脸 + 提取特征
    face_locations = face_recognition.face_locations(rgb_small)
    face_encodings = face_recognition.face_encodings(rgb_small, face_locations)

    for (top, right, bottom, left), face_encoding in zip(face_locations, face_encodings):
        name = "Unknown"
        color = (0, 0, 255)  # 红色

        if known_encodings:
            # 和所有已知脸算距离,取最近的
            distances = face_recognition.face_distance(known_encodings, face_encoding)
            best = np.argmin(distances)
            if distances[best] < TOLERANCE:
                name = known_names[best]
                color = (0, 255, 0)  # 绿色

        # 坐标放大回原尺寸(因为刚才缩了1/4)
        top, right, bottom, left = top*4, right*4, bottom*4, left*4

        cv2.rectangle(frame, (left, top), (right, bottom), color, 2)
        cv2.putText(frame, name, (left, top - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)

    cv2.imshow("Face Recognition - press q to quit", frame)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()