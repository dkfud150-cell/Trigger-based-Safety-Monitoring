"""
안전모 전용 모델 학습 — SHWD + Construction-PPE (10/7)

  SHWD (Safety Helmet Wearing Dataset, MIT) — 안전모 9천 · 맨머리 11만 (머리 단위 라벨, 위에서 본 CCTV 사진이 많다)
      https://github.com/njvisionpower/Safety-Helmet-Wearing-Dataset  (구글 드라이브 · 바이두에서 받아 압축을 푼다)
  Construction-PPE (Ultralytics) — 그 가운데 helmet · no_helmet 라벨만 쓴다 (처음 돌릴 때 저절로 받는다)

클래스는 둘 — 0 helmet (안전모) · 1 no_helmet (맨머리). 조끼는 기존 모델 + 색 확인이 맡는다
(SHWD 는 머리에만 라벨이 있어서, 섞어 학습하면 그 사진 속 조끼가 '아무것도 아님'으로 배워진다).

    python train_helmet.py --shwd "C:/Users/gegeg/Downloads/VOC2028"
    python train_helmet.py --shwd ... --epochs 30 --batch 8      # 메모리가 모자라면 batch 를 줄인다
    python train_helmet.py --shwd ... --prepare-only             # 데이터만 만들고 학습은 안 한다

끝나면 models/helmet_shwd.pt 가 생기고, config/detect.json 의 안전모가 이 모델을 쓰도록 바뀐다.
"""
import argparse
import json
import os
import random
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "datasets" / "helmet_head"
SHWD_CLASS = {"hat": 0, "person": 1}          # SHWD: hat = 안전모, person = 맨머리
CPPE_CLASS = {0: 0, 7: 1}                     # Construction-PPE: 0 helmet → 0, 7 no_helmet → 1 (나머지는 버린다)


def put(src: Path, dst: Path):
    """그림 파일은 하드 링크로(디스크를 안 먹는다), 안 되면 복사."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        return
    try:
        os.link(src, dst)
    except OSError:
        shutil.copy(src, dst)


def from_shwd(shwd: Path) -> int:
    ann = next((p for p in [shwd / "Annotations", *shwd.rglob("Annotations")] if p.is_dir()), None)
    if ann is None:
        raise SystemExit(f"SHWD 폴더에서 Annotations 를 못 찾았다: {shwd}")
    img_dir = ann.parent / "JPEGImages"
    files = sorted(ann.glob("*.xml"))
    random.Random(0).shuffle(files)
    n_val = max(1, len(files) // 10)              # 10% 는 검증용
    n = 0
    for k, x in enumerate(files):
        split = "val" if k < n_val else "train"
        root = ET.parse(x).getroot()
        W, H = float(root.find("size/width").text), float(root.find("size/height").text)
        rows = []
        for o in root.iter("object"):
            c = SHWD_CLASS.get(o.find("name").text.strip().lower())
            b = o.find("bndbox")
            if c is None or b is None or W <= 0 or H <= 0:
                continue
            x1, y1, x2, y2 = (float(b.find(t).text) for t in ("xmin", "ymin", "xmax", "ymax"))
            rows.append(f"{c} {(x1 + x2) / 2 / W:.6f} {(y1 + y2) / 2 / H:.6f} {(x2 - x1) / W:.6f} {(y2 - y1) / H:.6f}")
        img = img_dir / (x.stem + ".jpg")
        if not img.exists() or not rows:
            continue
        put(img, OUT / "images" / split / f"shwd_{img.name}")
        (OUT / "labels" / split).mkdir(parents=True, exist_ok=True)
        (OUT / "labels" / split / f"shwd_{x.stem}.txt").write_text("\n".join(rows) + "\n")
        n += 1
    return n


def from_cppe(cppe: Path | None) -> int:
    if cppe is None:
        from ultralytics.data.utils import check_det_dataset
        cppe = Path(check_det_dataset("construction-ppe.yaml")["path"])      # 없으면 받는다
    n = 0
    for split in ("train", "val"):
        for lab in (cppe / "labels" / split).glob("*.txt"):
            rows = []
            for line in lab.read_text().splitlines():
                p = line.split()
                if p and int(p[0]) in CPPE_CLASS:
                    rows.append(" ".join([str(CPPE_CLASS[int(p[0])])] + p[1:]))
            img = next((cppe / "images" / split / (lab.stem + e) for e in (".jpg", ".jpeg", ".png")
                        if (cppe / "images" / split / (lab.stem + e)).exists()), None)
            if img is None or not rows:
                continue
            put(img, OUT / "images" / split / f"cppe_{img.name}")
            (OUT / "labels" / split).mkdir(parents=True, exist_ok=True)
            (OUT / "labels" / split / f"cppe_{lab.name}").write_text("\n".join(rows) + "\n")
            n += 1
    return n


def use_in_config(weights: str):
    """config/detect.json — 안전모(ppe.items.helmet)가 이 모델을 쓰도록 weights 를 넣는다."""
    p = ROOT / "config" / "detect.json"
    if not p.exists():                        # Colab 처럼 이 파일만 따로 돌린 경우 — 받은 모델을 models/ 에 넣으면 된다
        return
    s = p.read_text(encoding="utf-8")
    d = json.loads(s)
    it = d["ppe"]["items"]["helmet"]
    if it.get("weights") == weights:
        return
    key = '"helmet": {"label": "안전모", '
    if key in s and '"weights"' not in s[s.index(key):s.index(key) + 200]:
        s = s.replace(key, key + f'"weights": "{weights}", ', 1)
    else:
        it["weights"] = weights
        s = json.dumps(d, ensure_ascii=False, indent=2)
    json.loads(s)
    p.write_text(s, encoding="utf-8")


ap = argparse.ArgumentParser()
ap.add_argument("--shwd", required=True, help="SHWD 압축을 푼 폴더 (Annotations · JPEGImages 가 있는 곳 또는 그 위)")
ap.add_argument("--cppe", default=None, help="Construction-PPE 폴더 (비우면 저절로 받는다)")
ap.add_argument("--epochs", type=int, default=40)
ap.add_argument("--imgsz", type=int, default=640)
ap.add_argument("--batch", type=int, default=16)
ap.add_argument("--prepare-only", action="store_true")
a = ap.parse_args()

print("SHWD 바꾸는 중 …")
n1 = from_shwd(Path(a.shwd))
print("Construction-PPE (helmet · no_helmet) 더하는 중 …")
n2 = from_cppe(Path(a.cppe) if a.cppe else None)
yaml = OUT / "helmet_head.yaml"
yaml.write_text(f"path: {OUT.as_posix()}\ntrain: images/train\nval: images/val\nnames:\n  0: helmet\n  1: no_helmet\n", encoding="utf-8")
print(f"데이터 준비 — SHWD {n1}장 + Construction-PPE {n2}장 → {OUT}")
if a.prepare_only:
    raise SystemExit

from ultralytics import YOLO

base = ROOT / "models" / "yolo26n.pt"
model = YOLO(str(base) if base.exists() else "yolo26n.pt")        # 없으면(Colab) 저절로 받는다
model.train(data=str(yaml), epochs=a.epochs, imgsz=a.imgsz, batch=a.batch, project=str(ROOT / "runs"), name="helmet", exist_ok=True)
(ROOT / "models").mkdir(exist_ok=True)
shutil.copy(ROOT / "runs" / "helmet" / "weights" / "best.pt", ROOT / "models" / "helmet_shwd.pt")
use_in_config("models/helmet_shwd.pt")
if (ROOT / "config" / "detect.json").exists():
    print("저장: models/helmet_shwd.pt — config/detect.json 의 안전모가 이 모델을 쓴다. 대시보드를 다시 켠다.")
else:
    print("저장: models/helmet_shwd.pt — 이 파일을 프로젝트의 monitor_engine/models/ 에 넣고, config/detect.json 의 ppe.items.helmet 에 "
          '"weights": "models/helmet_shwd.pt" 를 넣는다.')
