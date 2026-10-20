"""按官方模板（BEAUTY TECHATHON）重做初赛 PPT。

模板：白底 + 底部紫色渐变条 + 思源黑体（Title 44pt Bold / 正文 14pt Light，色值 #3F3F3F）。
四大板块：作品背景 / 技术实现方式 / 作品使用场景 / 未来完善方向。
用法：python scripts/build_ppt_tpl.py
"""
from __future__ import annotations

import os
from copy import deepcopy

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Emu, Inches, Pt

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TPL = r"D:\桌面\AI creation\Production\template.pptx"
if not os.path.isfile(TPL):
    TPL = os.path.join(BASE, "template.pptx")
OUT = os.path.join(BASE, "deliverables", "信任守护师_赛题2_初赛PPT.pptx")
SHOT = os.path.join(BASE, "deliverables", "screenshots")

INK = RGBColor(0x3F, 0x3F, 0x3F)
MUTED = RGBColor(0x80, 0x80, 0x88)
PURPLE = RGBColor(0x7A, 0x2E, 0x9B)
PURPLE_D = RGBColor(0x53, 0x13, 0x6E)
LILAC = RGBColor(0xF6, 0xF0, 0xFA)
LINE = RGBColor(0xE2, 0xD8, 0xEA)
RED = RGBColor(0xB0, 0x2E, 0x2E)
GREEN = RGBColor(0x1B, 0x6E, 0x4A)
AMBER = RGBColor(0x9A, 0x62, 0x13)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)

FONT_B = "思源黑体 CN Bold"
FONT_L = "思源黑体 CN Light"

W, H = 13.33, 7.5


def set_font(run, cjk=None, latin="Arial"):
    """西文用 Arial（任何机器都有），中文用思源黑体。

    只设 a:latin 的话，缺字体时 LibreOffice/PowerPoint 会把西文也交给中文字体，
    部分环境下 A-Z 会被替换成希腊字母（ELA 变成 EAA）。分开设置就不会了。
    """
    rPr = run._r.get_or_add_rPr()
    latin_el = rPr.find(qn("a:latin"))
    if latin_el is None:
        latin_el = rPr.makeelement(qn("a:latin"), {})
        rPr.append(latin_el)
    latin_el.set("typeface", latin)
    ea_el = rPr.find(qn("a:ea"))
    if ea_el is None:
        ea_el = rPr.makeelement(qn("a:ea"), {})
        latin_el.addnext(ea_el)
    ea_el.set("typeface", cjk or FONT_L)


def tb(slide, x, y, w, h, paragraphs, size=14, color=INK, bold=False,
       font=None, align=PP_ALIGN.LEFT, spacing=1.35, anchor=MSO_ANCHOR.TOP):
    """paragraphs: str | list[str] | list[list[(text, size, color, bold)]]"""
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = box.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = anchor
    if isinstance(paragraphs, str):
        paragraphs = [paragraphs]
    for i, para in enumerate(paragraphs):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        p.line_spacing = spacing
        runs = para if isinstance(para, list) else [(para, size, color, bold)]
        for item in runs:
            if isinstance(item, tuple):
                text, s, c, b = item
            else:
                text, s, c, b = item, size, color, bold
            r = p.add_run()
            r.text = text
            r.font.size = Pt(s)
            r.font.bold = b
            r.font.color.rgb = c
            set_font(r, font or (FONT_B if b else FONT_L))
    return box


def panel(slide, x, y, w, h, fill=LILAC, line=None, radius=0.06):
    shp = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h))
    shp.adjustments[0] = radius
    shp.fill.solid()
    shp.fill.fore_color.rgb = fill
    if line is None:
        shp.line.fill.background()
    else:
        shp.line.color.rgb = line
        shp.line.width = Pt(0.9)
    shp.shadow.inherit = False
    shp.text_frame.text = ""
    return shp


def bar(slide, x, y, w, h, color=PURPLE):
    shp = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h))
    shp.fill.solid()
    shp.fill.fore_color.rgb = color
    shp.line.fill.background()
    shp.shadow.inherit = False
    return shp


def pic(slide, name, x, y, w, h):
    path = os.path.join(SHOT, name)
    p = slide.shapes.add_picture(path, Inches(x), Inches(y), Inches(w), Inches(h))
    p.line.color.rgb = LINE
    p.line.width = Pt(0.75)
    return p


def fit_size(text, max_w=11.45, base=34, floor=21):
    """按字数估宽度自动缩字号，避免标题折行压住副标题。"""
    def width_in(size):
        w = 0.0
        for ch in text:
            w += (0.56 if ord(ch) < 128 else 1.0) * size / 72
        return w
    size = base
    while size > floor and width_in(size) > max_w:
        size -= 1
    return size


def page(prs, kicker, title, sub=""):
    s = prs.slides.add_slide(prs.slide_layouts[1])
    if kicker:
        tb(s, 0.91, 0.52, 6.0, 0.3, kicker, size=12, color=PURPLE, bold=True)
    size = fit_size(title)
    tb(s, 0.91, 0.86, 11.5, 0.8, title, size=size, color=INK, bold=True, spacing=1.1)
    if sub:
        tb(s, 0.91, 1.62, 11.5, 0.4, sub, size=13.5, color=MUTED, spacing=1.2)
    return s


# ---------------------------------------------------------------- 内容页

def p_bg1(prs):
    s = page(prs, "作品背景 · 01", "美妆内容正在变成「最不敢信」的一类内容",
             "功效看不见、对比图最容易修、评论区最容易刷——三件事叠在同一个行业里")
    items = [
        ("文案", "「7 天白 3 个度」", "AI 一分钟能写 20 篇，模板化文案已经是流水线"),
        ("配图", "局部磨皮 + 提亮 + 拼接", "对比图是美妆内容的核心证据，也最容易被改"),
        ("评论", "200 条清一色好评", "12 分钟内投放完毕，账号昵称是批量注册的"),
    ]
    x = 0.91
    for title, big, desc in items:
        panel(s, x, 2.35, 3.75, 2.45)
        bar(s, x, 2.35, 0.09, 2.45)
        tb(s, x + 0.32, 2.55, 3.2, 0.3, title, size=13, color=PURPLE, bold=True)
        tb(s, x + 0.32, 2.9, 3.2, 0.5, big, size=15, color=INK, bold=True, spacing=1.2)
        tb(s, x + 0.32, 3.62, 3.2, 1.0, desc, size=12, color=MUTED, spacing=1.4)
        x += 3.95

    panel(s, 0.91, 5.15, 11.55, 1.15, fill=RGBColor(0xFB, 0xF7, 0xFD), line=LINE)
    tb(s, 1.2, 5.35, 11.0, 0.8,
       [[("平台审核员每天面对这些内容，可用的工具却只有「举报」。", 15, INK, True)],
        [("我们要给的不是一个概率，而是一条能申诉、能复核、能写进工单的证据。", 13, MUTED, False)]],
       spacing=1.5)


def p_bg2(prs):
    s = page(prs, "作品背景 · 02", "平台要的不是「像假的」，而是「凭什么」",
             "常规 AIGC 检测器回答不了申诉，跨生成器还会掉点")
    panel(s, 0.91, 2.3, 5.6, 3.35, fill=RGBColor(0xFA, 0xFA, 0xFB), line=LINE)
    tb(s, 1.2, 2.48, 5.0, 0.4, "常规做法：一个概率", size=14, color=MUTED, bold=True)
    tb(s, 1.2, 2.95, 5.0, 1.9,
       ["· 审核员无法验证，也不敢据此下架",
        "· 创作者无法申诉，只能反复吵架",
        "· 跨生成器泛化差，模型一换就失灵",
        "· 检测器本身在和生成器打军备竞赛"],
       size=13, color=MUTED, spacing=1.7)
    tb(s, 1.2, 4.9, 5.0, 0.5, "「AIGC 概率 87%」", size=20, color=MUTED, bold=True)

    panel(s, 6.85, 2.3, 5.6, 3.35, fill=LILAC, line=RGBColor(0xD8, 0xC4, 0xE6))
    tb(s, 7.14, 2.48, 5.0, 0.4, "我们的做法：一条证据", size=14, color=PURPLE, bold=True)
    tb(s, 7.14, 2.95, 5.0, 1.9,
       ["· 每个结论挂载可核对的数值证据",
        "· 篡改区域可视化，边界能放大看",
        "· 不确定时主动降级，不硬给高分",
        "· 直接输出可写入处置工单的违规条款"],
       size=13, color=INK, spacing=1.7)
    tb(s, 7.14, 4.9, 5.0, 0.5, "「这一块，凭什么」", size=20, color=PURPLE_D, bold=True)

    tb(s, 0.91, 5.95, 11.55, 0.6,
       [[("赛题原文：「可解释性完整度将作为方案可信度的重要评估依据」——这就是我们的技术主线。", 13, PURPLE_D, True)]])


def p_tech1(prs):
    s = page(prs, "技术实现方式 · 01", "五维证据链：像素 → 语义 → 行为 → 一致性 → 规则",
             "单点证据会误报，多层互证才敢下结论")
    cols = [
        ("像素层", "ELA 重压缩误差\n噪声残差\n高频细节缺失\n频域幂律斜率\nSIFT 拷贝-移动", PURPLE),
        ("语义层", "9 项文体特征\n句长变异\n连接词密度\n信息具体度\n模板短语密度", RGBColor(0x5B, 0x3F, 0xA8)),
        ("行为层", "模板簇聚类\n短时爆发比\n情感一致性\n账号画像\n昵称熵", RGBColor(0x1B, 0x6E, 0x8C)),
        ("一致性", "CIELAB 色差\n文案宣称赞数\n夸大倍数\n两图光照方向差", RGBColor(0x1B, 0x6E, 0x4A)),
        ("规则层", "《广告法》第九条\n第二十八条\n《化妆品监督管理条例》\n第十六条、第四十三条", RGBColor(0x9A, 0x62, 0x13)),
    ]
    x = 0.91
    for name, body, color in cols:
        panel(s, x, 2.3, 2.16, 2.75)
        bar(s, x, 2.3, 2.16, 0.06, color)
        tb(s, x + 0.18, 2.5, 1.9, 0.35, name, size=14, color=color, bold=True)
        tb(s, x + 0.18, 2.95, 1.85, 1.9, body.split("\n"), size=10.5, color=MUTED, spacing=1.5)
        x += 2.28

    panel(s, 0.91, 5.2, 11.55, 1.35, fill=RGBColor(0xFB, 0xF7, 0xFD), line=LINE)
    tb(s, 1.2, 5.36, 11.0, 1.0,
       [[("融合规则：", 13, PURPLE_D, True),
         ("加权融合后，≥2 路信号同区互证才定位；命中高危条款可直接抬到中风险；出现两条以上高危证据才升到高风险；覆盖不足则主动降级。", 12.5, INK, False)],
        [("编排方式：", 13, PURPLE_D, True),
         ("固定 DAG（场景识别 → 并行取证 → 融合定级 → 生成结论），不是自由 ReAct——演示现场不会出现循环调用与幻觉工具。", 12.5, INK, False)]],
       spacing=1.55)


def p_tech2(prs):
    s = page(prs, "技术实现方式 · 02", "像素取证：把「修过」变成可以复算的数字",
             "六项经典取证信号，全部 CPU 毫秒级，不需要训练模型")
    stats = [("21.4%", "区域噪声偏离全图"), ("-4.6σ", "高频细节低于周边"),
             ("21%", "ELA 重压缩误差"), ("2–4s", "单次分析耗时")]
    x = 0.91
    for big, label in stats:
        panel(s, x, 2.28, 2.78, 1.35)
        tb(s, x + 0.22, 2.44, 2.4, 0.6, big, size=26, color=PURPLE_D, bold=True)
        tb(s, x + 0.22, 3.12, 2.4, 0.3, label, size=11, color=MUTED)
        x += 2.92

    tb(s, 0.91, 3.95, 5.6, 2.2,
       [[("怎么算的", 13, PURPLE, True)],
        [("ELA：重新压缩后与原图求差，篡改区因压缩历史不同而出现台阶。", 12, INK, False)],
        [("噪声残差：高通滤波后看块级方差，拼接会破坏传感器噪声的一致性。", 12, INK, False)],
        [("磨皮：Laplacian 方差在 log 域做稳健 z 分数，只看「比周边更平滑」。", 12, INK, False)]],
       spacing=1.45)

    panel(s, 6.85, 3.95, 5.6, 2.1, fill=RGBColor(0xFD, 0xF3, 0xF3), line=RGBColor(0xE8, 0xC8, 0xC8))
    tb(s, 7.1, 4.1, 5.1, 0.35, "一个必须说清楚的问题", size=12.5, color=RED, bold=True)
    tb(s, 7.1, 4.45, 5.1, 1.5,
       ["开发中发现 ELA 的稳健 z 分数在中位数退化时会除以 1e-6，",
        "把亚灰阶波动放大成 z=876445，真实照片被误判成「重压缩台阶」。",
        "补上绝对幅度闸门后，指标如实回落——见第 12 页。"],
       size=11.5, color=INK, spacing=1.45)


def p_tech3(prs):
    s = page(prs, "技术实现方式 · 03", "图文一致性：把「白三个度」换算成色差",
             "肤色转到 CIELAB 空间，与文案宣称直接对照")
    cells = [("ΔE = 3.81", "两张图实测色差", GREEN), ("ΔE ≈ 10.5", "文案宣称折算", MUTED), ("2.75 ×", "夸大倍数", RED)]
    x = 0.91
    for big, label, color in cells:
        panel(s, x, 2.3, 3.75, 1.45)
        tb(s, x + 0.3, 2.48, 3.2, 0.6, big, size=28, color=color, bold=True)
        tb(s, x + 0.3, 3.18, 3.2, 0.3, label, size=11.5, color=MUTED)
        x += 3.95

    tb(s, 0.91, 4.0, 11.55, 1.0,
       [[("实测：", 13, PURPLE, True), ("两图皮肤区域（YCbCr 肤色掩膜）平均 L*a*b* 距离。", 12.5, INK, False)],
        [("宣称：", 13, PURPLE, True), ("从文案抽取「白 N 个度」，按 1 个色号 ≈ ΔE 3.5 折算。这个换算系数写在文档里，评委可以自己复算。", 12.5, INK, False)]],
       spacing=1.55)

    panel(s, 0.91, 5.2, 5.6, 1.2, fill=RGBColor(0xF2, 0xF9, 0xF5), line=RGBColor(0xB8, 0xD8, 0xCC))
    tb(s, 1.15, 5.35, 5.1, 0.9,
       [[("对照组 · 真实测评", 12.5, GREEN, True)],
        [("无局部修改、文案无夸大 → 一致性 0.00，整体 低风险 14/100", 11.5, MUTED, False)]], spacing=1.4)

    panel(s, 6.85, 5.2, 5.6, 1.2, fill=RGBColor(0xFD, 0xF3, 0xF3), line=RGBColor(0xE8, 0xC8, 0xC8))
    tb(s, 7.1, 5.35, 5.1, 0.9,
       [[("实验组 · 高仿对比图", 12.5, RED, True)],
        [("局部磨皮 + 提亮 + 拼接，宣称 3 个度 → 整体 高风险 87/100", 11.5, MUTED, False)]], spacing=1.4)


def p_tech4(prs):
    s = page(prs, "技术实现方式 · 04", "评论区：不看单条评论，看「这批账号在做什么」",
             "12 条同一模板的评论，8 分钟内投放完毕")
    stats = [("12 条", "同一模板的评论簇"), ("0.92", "簇内平均相似度"),
             ("67%", "落在同一 10 分钟窗口"), ("6 个", "批量注册形态账号")]
    x = 0.91
    for big, label in stats:
        panel(s, x, 2.3, 2.78, 1.4)
        tb(s, x + 0.22, 2.46, 2.4, 0.6, big, size=26, color=PURPLE_D, bold=True)
        tb(s, x + 0.22, 3.16, 2.4, 0.3, label, size=11, color=MUTED)
        x += 2.92

    tb(s, 0.91, 4.0, 5.7, 2.2,
       [[("三条线索互相印证", 13, PURPLE, True)],
        [("文本：字符 3-gram Jaccard + DBSCAN 聚类，同一模板会被归成一簇。", 12, INK, False)],
        [("节奏：相邻间隔变异系数 + 10 分钟窗口占比，人不会这样发评论。", 12, INK, False)],
        [("账号：昵称字符熵 + 注册时间聚集度，批量注册有稳定形态。", 12, INK, False)]],
       spacing=1.45)

    panel(s, 6.85, 4.0, 5.6, 2.05, fill=LILAC, line=RGBColor(0xD8, 0xC4, 0xE6))
    tb(s, 7.1, 4.16, 5.1, 0.35, "为什么判高风险", size=12.5, color=PURPLE, bold=True)
    tb(s, 7.1, 4.52, 5.1, 1.4,
       ["模板簇 ≥5 条且相似度 ≥0.80，视为确证性证据，直接判高风险。",
        "只满足时间集中或账号异常其中一项时，最多判中风险。",
        "本次模板簇与投放节奏同时成立，且三路证据指向同一批账号。"],
       size=11.5, color=INK, spacing=1.45)


def p_tech5(prs):
    s = page(prs, "技术实现方式 · 05", "合规规则：输出的不是概率，是能写进工单的条款",
             "确定性规则，零算力、零幻觉，却是「落地价值」最直接的论据")
    rows = [
        ("绝对化用语", "「全网最低价」", "《广告法》第九条", "不得使用国家级、最高级、最佳等用语"),
        ("特殊化妆品未标批号", "「美白」「祛斑」", "《化妆品监督管理条例》第十六条", "须标注国妆特字注册编号"),
        ("量化功效承诺缺乏依据", "「7 天白一个度」", "《化妆品功效宣称评价规范》", "功效宣称应有评价依据"),
        ("宣称医疗作用", "「消炎」「药妆」", "《化妆品监督管理条例》第四十三条", "不得明示或暗示医疗作用"),
    ]
    y = 2.32
    for name, sample, clause, note in rows:
        panel(s, 0.91, y, 11.55, 0.92, fill=RGBColor(0xFB, 0xF9, 0xFC), line=LINE)
        tb(s, 1.15, y + 0.14, 2.5, 0.3, name, size=12.5, color=INK, bold=True)
        tb(s, 3.6, y + 0.14, 2.3, 0.3, sample, size=12, color=PURPLE_D, bold=True)
        tb(s, 5.95, y + 0.12, 3.0, 0.45, clause, size=10.5, color=MUTED)
        tb(s, 9.05, y + 0.12, 3.25, 0.6, note, size=10.5, color=MUTED, spacing=1.2)
        y += 1.02

    tb(s, 0.91, 6.45, 11.55, 0.4,
       [[("规则引擎和五维取证是互补的：取证回答「图有没有动过」，规则回答「这话能不能说」。", 12, PURPLE_D, True)]])


def p_use1(prs):
    s = page(prs, "作品使用场景 · 01", "种草图文核验：四维证据同时给出结论",
             "模拟平台审核员视角：上传 → 出证据 → 出等级 → 出处置建议")
    pic(s, "high.png", 0.91, 2.16, 7.35, 4.36)
    tb(s, 8.55, 2.16, 3.9, 0.35, "这一单为什么判 87 分", size=13, color=PURPLE, bold=True)
    tb(s, 8.55, 2.58, 3.9, 3.9,
       [["像素层：", "21% 区域噪声偏离、细节 -4.6σ，", "两项信号同区互证 → 局部重绘"],
        ["一致性：", "宣称 3 个色号（ΔE≈10.5），", "实测仅 3.81，夸大 2.75 倍"],
        ["合规层：", "命中 3 条广告法规", "（绝对化用语、特妆未标批号、量化承诺）"]],
       size=11, color=INK, spacing=1.5)
    tb(s, 8.55, 6.05, 3.9, 0.5, "证据覆盖 100% · 耗时 3.4 秒", size=10.5, color=MUTED)


def p_use2(prs):
    s = page(prs, "作品使用场景 · 02", "评论区核验：把 18 条评论还原成「一次投放」",
             "粘贴评论（或导入 .txt/.md/.docx）→ 聚类 → 看节奏 → 定位账号")
    pic(s, "comments.png", 0.91, 2.16, 7.35, 4.36)
    tb(s, 8.55, 2.16, 3.9, 0.35, "三条线索指向同一批账号", size=13, color=PURPLE, bold=True)
    tb(s, 8.55, 2.58, 3.9, 3.9,
       [["文本：", "12 条评论同一模板，", "平均相似度 0.92"],
        ["节奏：", "67% 挤在同一 10 分钟窗口，", "其余散在随后 14 小时"],
        ["账号：", "6 个昵称呈批量注册形态", "（英文 + 数字后缀）"]],
       size=11, color=INK, spacing=1.5)
    tb(s, 8.55, 6.05, 3.9, 0.5, "结论：高风险 75/100，建议下架复核", size=10.5, color=MUTED)


def p_use3(prs):
    s = page(prs, "作品使用场景 · 03", "AI 素材鉴伪：只有「成块的局部异常」才算证据",
             "整幅均匀的平滑不计入——这条规则把误报压了下来")
    pic(s, "material.png", 0.91, 2.16, 7.35, 4.36)
    tb(s, 8.55, 2.16, 3.9, 0.35, "单图怎么判", size=13, color=PURPLE, bold=True)
    tb(s, 8.55, 2.58, 3.9, 2.5,
       [["局部异常：", "细节缺失 14%、噪声偏离 19%，", "集中在一小块、周边保持原状 → 局部重绘"],
        ["整图均匀：", "平滑但不集中 → 不计入，", "该判低风险就判低风险"]],
       size=11, color=INK, spacing=1.5)

    panel(s, 8.55, 5.25, 3.9, 1.3, fill=RGBColor(0xFD, 0xF3, 0xF3), line=RGBColor(0xE8, 0xC8, 0xC8))
    tb(s, 8.75, 5.38, 3.5, 1.1,
       [[("如实说明", 11.5, RED, True)],
        [("该模块在自建 100 条集上未表现出区分度", 10.5, INK, False)],
        [("（F1=0.00），当前定位为辅助筛查。", 10.5, INK, False)]], spacing=1.35)


def p_data(prs):
    s = page(prs, "测试数据包与评测", "测试数据包：100 条，三场景 × 四档难度",
             "赛题看的不只是跑分，而是这份数据本身经不经得起看")
    rows = [("场景", "种草 40　·　评论 30　·　素材 30"),
            ("真伪", "伪造 56　·　真实 44"),
            ("难度", "easy 17　·　medium 31　·　hard 8　·　real 44"),
            ("标注", "24 张 mask.png（逐像素篡改区域）")]
    y = 2.3
    for k, v in rows:
        tb(s, 0.95, y, 1.0, 0.3, k, size=11, color=MUTED)
        tb(s, 1.85, y, 4.9, 0.3, v, size=11.5, color=INK, bold=True)
        y += 0.52

    tb(s, 0.95, 4.55, 5.8, 1.4,
       [["五类伪造手法：", "大面积磨皮+提亮 / 局部磨皮+拼接 / 轻度磨皮+拼接+重压缩 /", "重度平滑+色彩拉伸（模拟 AIGC 重绘）/ 模板化评论+集中投放"],
        ["每条样本可复现：", "meta.txt 记录场景、真伪、难度、伪造方式；eval/run_eval.py 可重算全部指标。"]],
       size=10.5, color=INK, spacing=1.45)

    panel(s, 7.0, 2.3, 5.45, 1.55, fill=LILAC, line=RGBColor(0xD8, 0xC4, 0xE6))
    tb(s, 7.2, 2.42, 5.1, 0.3, "自建 100 条集上的指标", size=11.5, color=PURPLE, bold=True)
    tb(s, 7.2, 2.75, 5.1, 0.9,
       [[("P 0.84　R 0.46　F1 0.60　定位 IoU 0.32", 14, PURPLE_D, True)],
        [("分场景 F1：图文 0.59　评论 0.97　素材 0.00", 10.5, MUTED, False)]], spacing=1.4)

    panel(s, 7.0, 4.0, 5.45, 1.95, fill=RGBColor(0xFD, 0xF3, 0xF3), line=RGBColor(0xE8, 0xC8, 0xC8))
    tb(s, 7.2, 4.12, 5.1, 0.3, "一次如实记录的修复", size=11.5, color=RED, bold=True)
    tb(s, 7.2, 4.45, 5.1, 1.4,
       ["早期 F1 是 0.69，其中素材场景的检出来自 ELA 的 z 分数退化（z=876445）。",
        "补上绝对幅度闸门后回落到 0.60——数字不好看，但它是真的。",
        "素材场景因此只作辅助筛查，不作为独立结论。"],
       size=10.5, color=INK, spacing=1.4)


def p_future(prs):
    s = page(prs, "未来完善方向", "三条线把这个 Demo 变成平台能用的审核工具",
             "先补检测能力，再扩场景，最后进工作流")
    cols = [
        ("1–3 个月", "检测能力", ["接入开源预训练 AIGC 检测器做集成", "引入 Qwen2.5-VL 做语义复核", "用真实平台数据重新标定阈值"]),
        ("3–6 个月", "场景扩展", ["从美妆扩到母婴、保健品等功效宣称密集品类", "从图文扩到短视频关键帧核验", "接入品牌真实色号库"]),
        ("6–12 个月", "平台化", ["对接内容中台，做成审核工作流插件", "证据包标准化，支持监管报送", "申诉链路：创作者可自助复核"]),
    ]
    x = 0.91
    for period, name, items in cols:
        panel(s, x, 2.3, 3.75, 2.75)
        bar(s, x, 2.3, 3.75, 0.06)
        tb(s, x + 0.25, 2.48, 3.2, 0.3, period, size=11, color=PURPLE, bold=True)
        tb(s, x + 0.25, 2.78, 3.2, 0.4, name, size=16, color=INK, bold=True)
        tb(s, x + 0.25, 3.3, 3.25, 1.6, ["· " + i for i in items], size=11, color=MUTED, spacing=1.5)
        x += 3.95

    panel(s, 0.91, 5.3, 11.55, 1.2, fill=RGBColor(0xFB, 0xF7, 0xFD), line=LINE)
    tb(s, 1.2, 5.45, 11.0, 0.95,
       [[("现在就体验", 12, PURPLE, True)],
        [("在线演示（只读）：", 11.5, MUTED, False), ("https://lulu520-1314.github.io/trust-shield/", 11.5, PURPLE_D, True),
         ("　　完整功能（可上传）：", 11.5, MUTED, False), ("https://trust-shield.onrender.com", 11.5, PURPLE_D, True)],
        [("代码仓库：", 11.5, MUTED, False), ("https://github.com/lulu520-1314/trust-shield", 11.5, PURPLE_D, True)]],
       spacing=1.4)


# ---------------------------------------------------------------- 组装

def clear_cover(slide):
    """把模板封面上的说明文字删掉，换成我们的标题。"""
    keep = None
    for sh in list(slide.shapes):
        if not sh.has_text_frame:
            continue
        t = sh.text_frame.text
        if "主标题" in t:
            keep = sh
        elif "推荐您使用" in t or "思源黑体CN" in t:
            sh._element.getparent().remove(sh._element)
    if keep is None:
        return
    tf = keep.text_frame
    tf.clear()
    p = tf.paragraphs[0]
    r = p.add_run()
    r.text = "信任守护师"
    r.font.size = Pt(54)
    r.font.bold = True
    set_font(r, FONT_B)
    r.font.color.rgb = WHITE

    for text, size, bold in [
        ("让「眼见为实」重新变得可验证", 30, False),
        ("赛题 2 · 美妆内容真实性核验　　队伍：噜噜大王", 20, False),
    ]:
        p2 = tf.add_paragraph()
        p2.space_before = Pt(10)
        r2 = p2.add_run()
        r2.text = text
        r2.font.size = Pt(size)
        r2.font.bold = bold
        set_font(r2, FONT_B if bold else FONT_L)
        r2.font.color.rgb = WHITE


def move_slide(prs, old_index, new_index):
    lst = prs.slides._sldIdLst
    items = list(lst)
    item = items[old_index]
    lst.remove(item)
    lst.insert(new_index, item)


def main():
    prs = Presentation(TPL)
    clear_cover(prs.slides[0])

    # 先加完所有内容页，再删模板示例页——
    # 反过来会让新页复用被释放的 part 编号，和 THANKS 的 slide3 撞名
    for fn in (p_bg1, p_bg2, p_tech1, p_tech2, p_tech3, p_tech4, p_tech5,
               p_use1, p_use2, p_use3, p_data, p_future):
        fn(prs)

    lst = prs.slides._sldIdLst
    victim = list(lst)[1]
    rId = victim.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
    prs.part.drop_rel(rId)
    lst.remove(victim)

    # THANKS 现在在索引 1，移到最后
    move_slide(prs, 1, len(prs.slides._sldIdLst) - 1)

    prs.save(OUT)
    print(f"saved: {OUT}  {len(prs.slides)} 页  {os.path.getsize(OUT)/1024:.0f} KB")


if __name__ == "__main__":
    main()
