"""Kimi 多图设计学习：WorkBuddy 截图 → 设计语言提取 → 对比 MiQi 卡片 → 改造建议。"""
import os
import base64
import json
import sys
import time
import urllib.request
from pathlib import Path

KEY = os.environ.get("MOONSHOT_API_KEY", "")
IMAGES = [
    r"C:\Users\admin\AppData\Roaming\Hermes\composer-images\composer_2026-08-18_06-39-09-916_69f128.png",
    r"C:\Users\admin\AppData\Roaming\Hermes\composer-images\composer_2026-08-18_06-39-30-172_7bb866.png",
    r"C:\Users\admin\AppData\Roaming\Hermes\composer-images\composer_2026-08-18_06-39-45-813_e6ee7f.png",
]

PROMPT = (
    "这是 WorkBuddy（AI 工作助手）的 3 张产品截图。请做「设计语言学习」：\n"
    "1) 逐张描述界面元素（卡片/进度/任务面板/工具调用/确认交互的形态）\n"
    "2) 提取它的设计语言：配色（主色/背景/状态色）、圆角体系、阴影层级、"
    "字体层级、卡片结构、进度/状态的可视化方式（步骤怎么展示、进行中怎么表达）\n"
    "3) 重点：任务执行进度/步骤列表/确认交互长什么样——和传统『审批卡片』有什么区别\n"
    "4) 给 MiQi 的建议：我们的任务计划卡（PlanCard）、执行进度（Timeline）、"
    "操作确认（ActionCard）要往 WorkBuddy 的哪些设计靠拢——逐项「WorkBuddy 做法 → "
    "MiQi 改法」（中文，具体可执行）"
)

content = [{"type": "text", "text": PROMPT}]
for p in IMAGES:
    b64 = base64.b64encode(Path(p).read_bytes()).decode()
    content.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}})

ok = False
for attempt in range(3):
    body = json.dumps({
        "model": "kimi-k2.6",
        "messages": [{"role": "user", "content": content}],
        "max_tokens": 2000,
    }).encode()
    req = urllib.request.Request("https://api.moonshot.cn/v1/chat/completions", data=body,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {KEY}"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            d = json.load(r)
            msg = d["choices"][0]["message"]
            print((msg.get("content") or msg.get("reasoning_content") or "").strip())
            ok = True
            break
    except Exception as e:
        print(f"尝试{attempt+1}失败: {type(e).__name__} {str(e)[:90]}", file=sys.stderr)
        time.sleep(5)
if not ok:
    print("Kimi 网络不稳", file=sys.stderr)
