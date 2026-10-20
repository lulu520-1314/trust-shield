测试数据包说明
================

本数据包用于评估「信任守护师」内容真实性核验系统，覆盖三个场景：
  1. 种草内容（图文）：post/content.txt + post/image_1.jpg + post/image_2.jpg
  2. 评论区：comments.txt
  3. AI 生成素材：post/image_1.jpg（单图）

样本结构
--------
sample_XXX/
  post/content.txt      正文（标题+正文）
  post/image_1.jpg      使用前 / 待检图片
  post/image_2.jpg      使用后（仅图文场景）
  comments.txt          评论区（仅评论区场景），格式：时间 TAB 账号 TAB 内容
  meta.txt              标注信息（key: value）
  mask.png              篡改区域 ground truth（仅图文篡改样本）

meta.txt 字段
-------------
  sample_id    样本编号
  scene        场景
  is_fake      是否伪造（true / false）
  fake_type    伪造方式说明
  difficulty   难度：easy / medium / hard / real
  has_mask     是否提供 mask
  source       素材来源与加工方式

数据构成（共 100 条）
-------------------
  种草图文   40 条（伪造 24 / 真实 16）
  评论区     30 条（伪造 16 / 真实 14）
  AI 素材    30 条（伪造 16 / 真实 14）

  合计：伪造 56 / 真实 44；难度 easy 17 / medium 31 / hard 8 / real 44
  含 mask.png 的图文篡改样本 24 条（可直接算定位 IoU）

为什么真伪都放
--------------
只含伪造样本的测试集无法衡量误报。真实样本用于检验系统是否会"见谁都像假的"。

如何评测
--------
把系统对每个样本的风险分与 meta.txt 里的 is_fake 对照，即可计算：
  - 样本级 Precision / Recall / F1（阈值 0.5）
  - 图文篡改样本的定位 IoU（把系统输出的可疑区域二值化后与 mask.png 对比）
详见同目录 eval.py。

许可与合规
----------
图片素材来自 Wikimedia Commons 的公开皮肤特写照片，经程序二次编辑用于方法验证；
不包含任何可识别的真人面部，不涉及真实商品的虚假宣传。
