"""接口边界测试：空输入、超短文本、无时间戳评论、坏文件。"""
import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

from app.core import analyze


def show(name, rep):
    r = rep["risk"]
    dims = ",".join(f'{d["key"]}={d.get("score")}' for d in rep["dimensions"])
    print(f"{name:26} -> {r['label']} {r['score']} coverage={r['coverage']} dims=[{dims}] findings={len(rep['findings'])}")


cases = []

# 1 完全空输入
cases.append(("空输入(post)", analyze("post", text="", image_paths=[])))
# 2 只有一句话
cases.append(("超短文本", analyze("post", text="好用。", image_paths=[])))
# 3 只有图片无文案
base = "data/samples/post_001/before.jpg"
cases.append(("只有图片无文案", analyze("material", text="", image_paths=[base])))
# 4 评论不足 5 条
cases.append(("评论太少", analyze("comments", text="", comments_text="好用\n不错\n还行")))
# 5 评论无时间戳
cases.append(("评论无时间戳", analyze("comments", text="", comments_text="\n".join(["很好用，回购了"] * 8))))
# 6 文案含大量否定（不应误判夸大）
neg = "用了三周，提亮效果没看出来，质地也一般，不会回购。价格偏高，包装还行，客服回复慢。"
cases.append(("否定语境文案", analyze("material", text=neg, image_paths=[base])))
# 7 只有一张图冒充对比图
cases.append(("单图当对比图", analyze("post", text="七天白三个度", image_paths=[base])))

print(f"\n共 {len(cases)} 个边界用例，全部返回结构完整：",
      all(c[1] and c[1].get("risk") for c in cases))

# 检查空输入不会崩、也不会给高风险
empty = cases[0][1]
assert empty["risk"]["level"] == "low", "空输入不该给高风险"
print("空输入判定：", empty["risk"]["label"], "（应为低风险）")

# 评论无时间戳时，时间维度应标为不可用
c5 = cases[4][1]
b = [d for d in c5["dimensions"] if d["key"] == "behavior"][0]
print("无时间戳评论：模板比例", b.get("template_ratio"), "| timing available =", b["timing"].get("available"))
