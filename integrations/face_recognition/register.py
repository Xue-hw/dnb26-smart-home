"""
注册程序:把照片里的脸转成"特征",存进一个文件。
用法:把照片放进 photos/ 文件夹,运行本程序。
"""
import face_recognition
import os
import pickle  # Python 自带,用来把数据存成文件

PHOTOS_DIR = "photos"          # 存照片的文件夹
DB_FILE = "known_faces.pkl"    # 存特征的文件(相当于你的"数据库")

def register_all():
    known_encodings = []
    known_names = []

    if not os.path.exists(PHOTOS_DIR):
        print(f"找不到 {PHOTOS_DIR} 文件夹,请先创建并放入照片")
        return

    for fname in os.listdir(PHOTOS_DIR):
        if not fname.lower().endswith((".jpg", ".jpeg", ".png")):
            continue
        path = os.path.join(PHOTOS_DIR, fname)
        name = os.path.splitext(fname)[0]   # 文件名(去掉后缀)当作人名

        print(f"正在处理 {fname} ...")
        image = face_recognition.load_image_file(path)
        encodings = face_recognition.face_encodings(image)

        if len(encodings) == 0:
            print(f"  ⚠️ {fname} 里没检测到人脸,跳过")
            continue
        known_encodings.append(encodings[0])
        known_names.append(name)
        print(f"  ✓ 已注册: {name}")

    # 存进文件
    with open(DB_FILE, "wb") as f:
        pickle.dump({"encodings": known_encodings, "names": known_names}, f)

    print(f"\n完成!共注册 {len(known_names)} 人: {known_names}")
    print(f"特征已保存到 {DB_FILE}")

if __name__ == "__main__":
    register_all()