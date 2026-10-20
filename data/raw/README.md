# 原始素材来源与许可

本目录下的图片用于生成示例样本与测试数据包，**不含任何可识别的真人面部**。

| 文件 | 来源 | 许可 |
|---|---|---|
| `skin2.jpg` | Wikimedia Commons — [Hand skin close up.jpg](https://commons.wikimedia.org/wiki/File:Hand_skin_close_up.jpg) | 见原始页面（CC BY-SA / 公有领域，以页面声明为准） |
| `skin1.jpg` | Wikimedia Commons — [Human skin close-up.jpg](https://commons.wikimedia.org/wiki/File:Human_skin_close-up.jpg) | 同上 |

## 加工方式

所有样本均为**程序化二次编辑**，过程可复现（`scripts/build_samples.py`、`scripts/build_package.py`）：

- **局部磨皮**：指定椭圆区域做双边滤波 + 中值滤波，模拟美颜修图
- **局部提亮**：区域内叠加亮度，模拟「变白」对比图
- **拼接**：把图内一块纹理复制到另一处，制造不自然的边界
- **局部重绘**：区域内重画并用羽化蒙版合成，模拟 AI 局部修改

每条伪造样本都记录了 ground-truth mask（`mask.png`），用于计算定位 IoU。

## 使用边界

- 这些图片**仅用于方法验证与演示**，不针对任何真实人物或商品
- 若你二次分发，请保留原始许可声明；代码部分的许可见仓库根目录 `LICENSE`
