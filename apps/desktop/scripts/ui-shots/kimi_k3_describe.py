"""Kimi k3 分析单张参考图（短输出——避免卡死）。"""
import os
import base64
import json
import sys
import urllib.request
from pathlib import Path

KEY = os.environ.get("MOONSHOT_API_KEY", "")
IMG = Path(sys.argv[1])
b64 = base64.b64encode(IMG.read_bytes()).decode()

PROMPT = """这是用户认可的参考产品 UI 截图。请精确描述（中文，300 字内）：
1) AI 消息布局（头像位置大小/名字/正文有无框）
2) 卡片形态（圆角/边框/阴影/与消息的嵌套关系）
3) 按钮样式（跳过按钮等——颜色/圆角/位置）
4) 配色（主色/背景/文字层级）
5) 间距与留白特征
只描述看到的，不要建议。"""

content = [{"type": "text", "text": PROMPT}, {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}]
body = json.dumps({"model": "kimi-k2.7-code", "messages": [{"role": "user", "content": content}], "max_tokens": 600}).encode()
req = urllib.request.Request("https://api.moonshot.cn/v1/chat/completions", data=body,
    headers={"Content-Type": "application/json", "Authorization": f"Bearer {KEY}"})
try:
    with urllib.request.urlopen(req, timeout=180) as r:
        d = json.load(r)
        msg = d["choices"][0]["message"]
        print((msg.get("content") or msg.get("reasoning_content") or "").strip())
except Exception as e:
    print(f"失败: {type(e).__name__} {str(e)[:150]}")
