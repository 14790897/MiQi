"""Kimi 多图学习（第二轮）：参考产品 3 张截图——任务列表/卡片形态/对话流布局。"""
import os
import base64
import json
import sys
import time
import urllib.request
from pathlib import Path

KEY = os.environ.get("MOONSHOT_API_KEY", "")
IMAGES = [
    r"C:\Users\admin\AppData\Roaming\Hermes\composer-images\composer_2026-08-18_07-01-52-122_a838dc.png",
    r"C:\Users\admin\AppData\Roaming\Hermes\composer-images\composer_2026-08-18_07-03-38-431_6a05b1.png",
    r"C:\Users\admin\AppData\Roaming\Hermes\composer-images\composer_2026-08-18_07-03-59-950_ada138.png",
]

PROMPT = (
    "这是 3 张 AI 助手产品截图。请做「设计语言学习」（第二轮）：\n"
    "1) 逐张描述：任务列表长什么样（条目结构/状态表达/分组）、AI 消息/卡片形态"
    "（有没有对话框气泡？头像怎么处理？卡片是嵌在对话流还是独立浮层？）\n"
    "2) 提取设计语言：任务列表的简洁优雅体现在哪（间距/字重/状态点/信息密度）、"
    "卡片与对话流的关系、整体留白\n"
    "3) 关键问题：如果「AI 消息不带头像不带头像框（对话框）」，信息层级怎么建立？"
    "（用户提议 MiQi 去掉头像/对话框，把头像信息放上面——评估这个方案）\n"
    "4) 给 MiQi 的任务列表 + 卡片 UI 逐项建议（中文，具体可执行）"
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
