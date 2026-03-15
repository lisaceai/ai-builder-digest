"""Generate a horizontal workflow PNG diagram for the daily digest pipeline."""

from PIL import Image, ImageDraw, ImageFont

# --- Config ---
WIDTH, HEIGHT = 2200, 920
BG = "#FFFFFF"
CJK_FONT = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
LATIN_FONT = "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"
BOLD_FONT = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"

font_title = ImageFont.truetype(CJK_FONT, 28)
font_header = ImageFont.truetype(CJK_FONT, 20)
font_body = ImageFont.truetype(CJK_FONT, 16)
font_small = ImageFont.truetype(CJK_FONT, 14)

# Colors for each phase
PHASES = [
    {
        "title": "触发",
        "color": "#2196F3",
        "bg": "#e8f4f8",
        "steps": [
            ("定时任务", "UTC 1:20 每日"),
            ("手动触发", "workflow_dispatch"),
        ],
    },
    {
        "title": "数据采集",
        "color": "#FF9800",
        "bg": "#fff3e0",
        "steps": [
            ("加载配置", "config/users.json"),
            ("计算时间范围", "昨日 24h"),
            ("Apify 请求", "Twitter Scraper"),
            ("轮询等待", "每10s/最长600s"),
            ("下载数据", "raw_tweets.json"),
        ],
    },
    {
        "title": "AI 摘要",
        "color": "#9C27B0",
        "bg": "#f3e5f5",
        "steps": [
            ("解析推文", "转推/引用/线程"),
            ("智谱 GLM-4.7", "逐条生成摘要"),
            ("输出文件", "summarized_tweets.json"),
        ],
    },
    {
        "title": "RAG 入库",
        "color": "#4CAF50",
        "bg": "#e8f5e9",
        "steps": [
            ("生成唯一 ID", "合并摘要+原文"),
            ("本地 JSON", "tweets_store.json"),
            ("Embedding", "智谱 embedding-3"),
            ("Pinecone", "向量数据库"),
        ],
    },
    {
        "title": "通知 & 归档",
        "color": "#E91E63",
        "bg": "#fce4ec",
        "steps": [
            ("HTML 邮件", "按作者分组"),
            ("SMTP 发送", "Gmail TLS"),
            ("GitHub Artifacts", "保留 7 天"),
        ],
    },
]

img = Image.new("RGB", (WIDTH, HEIGHT), BG)
draw = ImageDraw.Draw(img)

# Title
draw.text((WIDTH // 2, 30), "AI Builder Daily Digest - 主工作流", fill="#333333", font=font_title, anchor="mt")

# Layout constants
TOP_Y = 80
PHASE_GAP = 16
MARGIN_X = 30
usable_w = WIDTH - 2 * MARGIN_X - (len(PHASES) - 1) * PHASE_GAP
phase_w = usable_w // len(PHASES)
BOX_H = 60
BOX_GAP = 12
HEADER_H = 44
PADDING = 14
CORNER = 12


def hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))


def draw_rounded_rect(draw, xy, fill, outline=None, radius=10, width=2):
    x0, y0, x1, y1 = xy
    draw.rounded_rectangle(xy, radius=radius, fill=fill, outline=outline, width=width)


def draw_arrow(draw, x1, y1, x2, y2, color="#888888", w=2):
    draw.line([(x1, y1), (x2, y2)], fill=color, width=w)
    # arrowhead
    arrow_size = 8
    draw.polygon(
        [(x2, y2), (x2 - arrow_size, y2 - arrow_size // 2), (x2 - arrow_size, y2 + arrow_size // 2)],
        fill=color,
    )


# Draw phases
phase_boxes = []  # list of list of (cx, cy) for each step box center
phase_rects = []  # (x0, y0, x1, y1) for each phase group

for i, phase in enumerate(PHASES):
    x0 = MARGIN_X + i * (phase_w + PHASE_GAP)
    n_steps = len(phase["steps"])
    content_h = HEADER_H + n_steps * (BOX_H + BOX_GAP) + PADDING
    y0 = TOP_Y
    x1 = x0 + phase_w
    y1 = y0 + content_h

    # Phase background
    draw_rounded_rect(draw, (x0, y0, x1, y1), fill=phase["bg"], outline=phase["color"], radius=CORNER, width=2)

    # Phase header
    hdr_y = y0 + 6
    draw.text(
        ((x0 + x1) // 2, hdr_y + HEADER_H // 2),
        phase["title"],
        fill=phase["color"],
        font=font_header,
        anchor="mm",
    )
    # Divider line
    draw.line([(x0 + 10, y0 + HEADER_H), (x1 - 10, y0 + HEADER_H)], fill=phase["color"], width=1)

    boxes = []
    for j, (label, sub) in enumerate(phase["steps"]):
        bx0 = x0 + PADDING
        by0 = y0 + HEADER_H + BOX_GAP + j * (BOX_H + BOX_GAP)
        bx1 = x1 - PADDING
        by1 = by0 + BOX_H

        draw_rounded_rect(draw, (bx0, by0, bx1, by1), fill="#FFFFFF", outline="#CCCCCC", radius=8, width=1)

        cx = (bx0 + bx1) // 2
        draw.text((cx, by0 + 16), label, fill="#333333", font=font_body, anchor="mt")
        draw.text((cx, by0 + 38), sub, fill="#888888", font=font_small, anchor="mt")

        boxes.append(((bx0, by0, bx1, by1), cx, (by0 + by1) // 2))

    phase_boxes.append(boxes)
    phase_rects.append((x0, y0, x1, y1))

# Draw arrows WITHIN each phase (vertical, between consecutive steps)
for i, boxes in enumerate(phase_boxes):
    color = PHASES[i]["color"]
    for j in range(len(boxes) - 1):
        _, cx1, _ = boxes[j]
        (_, _, _, by1_prev), _, _ = boxes[j]
        (_, by0_next, _, _), _, _ = boxes[j + 1]
        # vertical arrow from bottom of box j to top of box j+1
        draw.line([(cx1, by1_prev), (cx1, by0_next)], fill=color, width=2)
        # arrowhead down
        a = 6
        draw.polygon(
            [(cx1, by0_next), (cx1 - a, by0_next - a), (cx1 + a, by0_next - a)],
            fill=color,
        )

# Draw arrows BETWEEN phases (horizontal, from last step of phase i to first step of phase i+1)
ARROW_Y_OFFSET = 0
for i in range(len(PHASES) - 1):
    # from last box of phase i
    src_boxes = phase_boxes[i]
    dst_boxes = phase_boxes[i + 1]

    # Connect last step of current phase to first step of next phase
    (_, _, src_bx1, _), _, src_cy = src_boxes[-1]
    (dst_bx0, _, _, _), _, dst_cy = dst_boxes[0]

    mid_y = (src_cy + dst_cy) // 2
    mid_x = (src_bx1 + dst_bx0) // 2

    color = "#666666"
    lw = 2

    if src_cy == dst_cy:
        # straight horizontal
        draw.line([(src_bx1, src_cy), (dst_bx0, dst_cy)], fill=color, width=lw)
        a = 7
        draw.polygon(
            [(dst_bx0, dst_cy), (dst_bx0 - a, dst_cy - a), (dst_bx0 - a, dst_cy + a)],
            fill=color,
        )
    else:
        # L-shaped connector
        draw.line([(src_bx1, src_cy), (mid_x, src_cy)], fill=color, width=lw)
        draw.line([(mid_x, src_cy), (mid_x, dst_cy)], fill=color, width=lw)
        draw.line([(mid_x, dst_cy), (dst_bx0, dst_cy)], fill=color, width=lw)
        a = 7
        draw.polygon(
            [(dst_bx0, dst_cy), (dst_bx0 - a, dst_cy - a), (dst_bx0 - a, dst_cy + a)],
            fill=color,
        )

# Special: phase 3 (AI摘要) last step also connects to phase 5 (通知&归档) first step
# This represents the fork: summarized_tweets.json -> both RAG and Notification
src_boxes_3 = phase_boxes[2]  # AI摘要
dst_boxes_5 = phase_boxes[4]  # 通知&归档

(_, _, src_bx1_3, src_by1_3), src_cx_3, src_cy_3 = src_boxes_3[-1]  # last step of AI摘要
(dst_bx0_5, dst_by0_5, _, _), _, dst_cy_5 = dst_boxes_5[0]  # first step of 通知

# Draw a curved path going below the boxes
fork_y = max(r[3] for r in phase_rects) + 30  # below all phase boxes

draw.line([(src_cx_3, src_by1_3), (src_cx_3, fork_y)], fill="#E91E63", width=2)
draw.line([(src_cx_3, fork_y), (dst_bx0_5 - 20, fork_y)], fill="#E91E63", width=2)
draw.line([(dst_bx0_5 - 20, fork_y), (dst_bx0_5 - 20, dst_cy_5)], fill="#E91E63", width=2)
draw.line([(dst_bx0_5 - 20, dst_cy_5), (dst_bx0_5, dst_cy_5)], fill="#E91E63", width=2)
a = 7
draw.polygon(
    [(dst_bx0_5, dst_cy_5), (dst_bx0_5 - a, dst_cy_5 - a), (dst_bx0_5 - a, dst_cy_5 + a)],
    fill="#E91E63",
)

# Label the fork
draw.text(
    ((src_cx_3 + dst_bx0_5 - 20) // 2, fork_y - 16),
    "summarized_tweets.json (分叉)",
    fill="#E91E63",
    font=font_small,
    anchor="mt",
)

# Legend at bottom
legend_y = HEIGHT - 50
legend_items = [
    ("#666666", "顺序流程"),
    ("#E91E63", "分叉路径 (摘要同时送入 RAG 和通知)"),
]
lx = MARGIN_X + 20
for color, label in legend_items:
    draw.rectangle([(lx, legend_y), (lx + 30, legend_y + 16)], fill=color)
    draw.text((lx + 38, legend_y + 8), label, fill="#333333", font=font_small, anchor="lm")
    lx += 350

# Save
out_path = "/home/user/ai-builder-digest/docs/workflow-main.png"
img.save(out_path, "PNG")
print(f"Saved to {out_path} ({img.size[0]}x{img.size[1]})")
