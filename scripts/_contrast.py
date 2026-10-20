import io, os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
p = os.path.join(ROOT, "app/web/style.css")
s = io.open(p, encoding="utf-8").read()

pairs = [
    # 全局调色：dim 从 3.5:1 提到 ~5.7:1，muted 微调更亮
    ("--muted: #8ea3c4;", "--muted: #a3b8d6;"),
    ("--dim: #5f7395;", "--dim: #8098bd;"),
    ("--border: #223252;", "--border: #2b3d61;"),

    # 提示、图例、字段标签：提亮 + 放大
    (".hint { margin-top: -4px; padding: 0 14px 10px; font-size: 11px; color: #5f7395; line-height: 1.65; }",
     ".hint { margin-top: -4px; padding: 0 14px 10px; font-size: 12px; color: var(--dim); line-height: 1.7; }"),
    (".bar-legend { font-size: 10.5px; color: #5f7395; margin: -2px 0 8px; }",
     ".bar-legend { font-size: 11px; color: var(--dim); margin: -2px 0 8px; }"),
    (".field-label { padding: 0 14px 6px; font-size: 11px; color: #6f86a8; }",
     ".field-label { padding: 0 14px 6px; font-size: 11.5px; color: #93a9c9; }"),

    # 维度条下面的实测说明
    (".bar-sub { font-size: 10.5px; color: #5f7395; line-height: 1.5; margin: 3px 0 2px; }",
     ".bar-sub { font-size: 11px; color: #9db2d0; line-height: 1.55; margin: 3px 0 2px; }"),

    # 图表说明
    (".chart-cap b { font-size: 12px; color: #c9d8ef; font-weight: 600; }",
     ".chart-cap b { font-size: 12.5px; color: #e2ecfb; font-weight: 600; }"),
    (".chart-cap span { font-size: 10.5px; color: #6f86a8; line-height: 1.5; }",
     ".chart-cap span { font-size: 11px; color: #9db2d0; line-height: 1.55; }"),

    # 判定依据正文
    (".narrative { padding: 0 14px 6px; font-size: 11.5px; line-height: 1.55; color: #c9d8ef; }",
     ".narrative { padding: 0 14px 6px; font-size: 12px; line-height: 1.6; color: #d6e3f7; }"),

    # 证据卡正文
    (".ev .detail", ".ev .detail"),
]

n = 0
for old, new in pairs:
    if old == new:
        continue
    if old in s:
        s = s.replace(old, new, 1)
        n += 1
    else:
        print("[miss]", old[:50])

# 证据卡 body / 其他偏暗的文字统一走变量
s = s.replace("color: #5f7395", "color: var(--dim)")
s = s.replace("color: #6f86a8", "color: #93a9c9")

io.open(p, "w", encoding="utf-8", newline="\n").write(s)
print(f"[OK] 替换 {n} 组，另做了全局 dim 替换")

# 图表里的取色也一起提亮
p2 = os.path.join(ROOT, "app/web/app.js")
s2 = io.open(p2, encoding="utf-8").read()
before = s2
s2 = s2.replace("'#5f7395'", "'#9db2d0'").replace("'#8ea3c4'", "'#a3b8d6'")
s2 = s2.replace("color: '#8ea3c4'", "color: '#a3b8d6'")
io.open(p2, "w", encoding="utf-8", newline="\n").write(s2)
print("[OK] 图表配色", "有变化" if s2 != before else "无变化")
