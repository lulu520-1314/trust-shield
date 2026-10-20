import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.core import analyze

cases = [
    ("post_001 双图 篡改", "post", "data/samples/post_001/content.txt",
     ["data/samples/post_001/before.jpg", "data/samples/post_001/after.jpg"]),
    ("post_002 双图 对照", "post", "data/samples/post_002/content.txt",
     ["data/samples/post_002/before.jpg", "data/samples/post_002/after.jpg"]),
    ("post_002 单图", "post", "data/samples/post_002/content.txt",
     ["data/samples/post_002/before.jpg"]),
]

for name, scene, text_file, imgs in cases:
    text = open(text_file, encoding="utf-8").read()
    r = analyze(scene, text=text, image_paths=imgs)
    label = r["risk"]["label"]
    score = round(r["risk"]["score"] * 100)
    finding = [(f["severity"], f["title"]) for f in r["findings"]]
    print(f"{name:16} {label} {score:>3} | {finding}")
