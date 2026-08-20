"""Kimi 视觉评审（k2.6）——参数化图片+提示词。"""
import os
import base64
import json
import sys
import time
import urllib.request
from pathlib import Path

KEY = os.environ.get("MOONSHOT_API_KEY", "")
SHOTS = Path(__file__).resolve().parent / "shots"
IMG = sys.argv[1] if len(sys.argv) > 1 else "plan-card-all.png"
PROMPT = sys.argv[2] if len(sys.argv) > 2 else "视觉设计评审：1) 整体质感 2) 信息层级/间距/配色/圆角问题 3) P0/P1 改进建议（问题+改法，中文）"

# 支持绝对路径（E2E 截图在 test-results/）
img_path = Path(IMG)
if not img_path.is_absolute():
    img_path = SHOTS / IMG

b64 = base64.b64encode(img_path.read_bytes()).decode()
ok = False
for attempt in range(3):
    body = json.dumps({
        "model": "kimi-k2.6",
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": PROMPT},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
        ]}],
        "max_tokens": 1500,
    }).encode()
    req = urllib.request.Request("https://api.moonshot.cn/v1/chat/completions", data=body,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {KEY}"})
    try:
        with urllib.request.urlopen(req, timeout=100) as r:
            d = json.load(r)
            msg = d["choices"][0]["message"]
            content = msg.get("content") or ""
            reasoning = msg.get("reasoning_content") or ""
            print((content or reasoning or "（无 content）").strip())
            ok = True
            break
    except Exception as e:
        print(f"尝试{attempt+1}失败: {type(e).__name__} {str(e)[:90]}", file=sys.stderr)
        time.sleep(5)
if not ok:
    print("Kimi 网络不稳", file=sys.stderr)
