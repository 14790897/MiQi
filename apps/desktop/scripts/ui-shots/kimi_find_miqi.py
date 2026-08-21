"""Kimi k2.7-code 分析用户截图：定位"大的 A"头像和"下面的 miqi"残留。"""
import os
import base64
import json
import sys
import time
import urllib.request
from pathlib import Path

KEY = os.environ.get("MOONSHOT_API_KEY", "")
IMAGES = [
    r"C:\Users\admin\AppData\Roaming\Hermes\composer-images\composer_2026-08-18_07-58-46-163_4095ac.png",
    r"C:\Users\admin\AppData\Roaming\Hermes\composer-images\composer_2026-08-18_07-59-36-986_11afbf.png",
]

PROMPT = (
    "这是 MiQi 桌面应用的两张截图。用户抱怨：'上面的大的 A 取缔掉了，给下面的 miqi 反倒留下来了'"
    "——即大的 A 头像（可能 AI 或用户头像）没了，但某处还有个小的 miqi 标识残留。\n"
    "请：1) 逐张详细描述界面（顶部栏/消息区/卡片区，所有头像、字母标识、文字的位置和样子）\n"
    "2) 指出：'大的 A'原来可能在哪（现在没了）？'下面的 miqi'现在在哪（什么样子：文字/图标/大小/位置）？\n"
    "3) 整体视觉问题（简约美观角度：什么多余、什么突兀、间距/层级问题）\n"
    "4) 给修改建议（中文，具体）"
)

content = [{"type": "text", "text": PROMPT}]
for p in IMAGES:
    b64 = base64.b64encode(Path(p).read_bytes()).decode()
    content.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}})

ok = False
for attempt in range(3):
    body = json.dumps({
        "model": "kimi-k2.7-code",
        "messages": [{"role": "user", "content": content}],
        "max_tokens": 2000,
    }).encode()
    req = urllib.request.Request("https://api.moonshot.cn/v1/chat/completions", data=body,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {KEY}"})
    try:
        with urllib.request.urlopen(req, timeout=150) as r:
            d = json.load(r)
            msg = d["choices"][0]["message"]
            print((msg.get("content") or msg.get("reasoning_content") or "").strip())
            ok = True
            break
    except Exception as e:
        print(f"尝试{attempt+1}失败: {type(e).__name__} {str(e)[:100]}", file=sys.stderr)
        time.sleep(5)
if not ok:
    print("Kimi 网络不稳", file=sys.stderr)
