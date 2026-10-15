"""
보호구(PPE) 탐지 모델 학습 — Ultralytics Construction-PPE 데이터셋 (10/7)
https://docs.ultralytics.com/datasets/detect/construction-ppe/

    python train_ppe.py                 # GPU 가 있으면 GPU 로, 없으면 CPU 로 (CPU 는 한 에폭에 수 분)
    python train_ppe.py --epochs 50

데이터셋은 처음 돌릴 때 저절로 받는다(약 180MB, 이미지 1,416장, 클래스 11개 — helmet · vest · no_helmet …).
학습이 끝나면 가장 좋은 가중치를 models/ppe_cppe.pt 로 복사한다. config/detect.json 의 ppe.weights 가 이 파일을 쓴다.
"""
import argparse
import shutil
from pathlib import Path

from ultralytics import YOLO

ROOT = Path(__file__).resolve().parent

ap = argparse.ArgumentParser()
ap.add_argument("--epochs", type=int, default=50)
ap.add_argument("--imgsz", type=int, default=640)
ap.add_argument("--batch", type=int, default=16)
a = ap.parse_args()

model = YOLO(str(ROOT / "models" / "yolo26n.pt"))          # 사람 탐지에 쓰는 것과 같은 모델에서 이어 학습한다
model.train(data="construction-ppe.yaml", epochs=a.epochs, imgsz=a.imgsz, batch=a.batch,
            project=str(ROOT / "runs"), name="ppe", exist_ok=True)

best = ROOT / "runs" / "ppe" / "weights" / "best.pt"
shutil.copy(best, ROOT / "models" / "ppe_cppe.pt")
print("저장:", ROOT / "models" / "ppe_cppe.pt")
