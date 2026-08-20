"""Kimi k2.7-code 逐组件改造（一次一个组件——避免长响应超时）。"""
import os
import base64
import json
import sys
import urllib.request
from pathlib import Path

KEY = os.environ.get("MOONSHOT_API_KEY", "")
COMPONENT = sys.argv[1]  # PlanCard | Timeline | ActionCard | ConfirmCardArea
BASE = Path(r"D:\Desktop\811\MiQi\apps\desktop\src\renderer\features\chat\components")
CODE = (BASE / f"{COMPONENT}.tsx").read_text(encoding="utf-8")
b64 = base64.b64encode(Path(r"D:\Desktop\811\MiQi\docs\workbuddy-5张参考-拼图.png").read_bytes()).decode()

PROMPT = f"""参考图（拼图，从左到右 5 张）是用户认可的简洁优雅 UI：大圆角白卡 16-20px、深色近黑主按钮 #1f1f1f、灰色状态小字、彩色小圆点、大量留白、克制。用户要求对照抄。

只改造这一个组件（保持 props/data-testid 不变——plan-card）：

```tsx
{CODE}
```

输出：改造后的完整 ```tsx 代码（不要解释，只要代码）。"""

content = [{"type": "text", "text": PROMPT}, {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}]
body = json.dumps({"model": "kimi-k2.7-code", "messages": [{"role": "user", "content": content}], "max_tokens": 4000}).encode()
req = urllib.request.Request("https://api.moonshot.cn/v1/chat/completions", data=body,
    headers={"Content-Type": "application/json", "Authorization": f"Bearer {KEY}"})
try:
    with urllib.request.urlopen(req, timeout=300) as r:
        d = json.load(r)
        msg = d["choices"][0]["message"]
        text = (msg.get("content") or msg.get("reasoning_content") or "").strip()
        out = Path(rf"D:\Desktop\811\MiQi\docs\kimi-{COMPONENT}.tsx")
        out.write_text(text, encoding="utf-8")
        print(f"OK {len(text)} 字符 → docs/kimi-{COMPONENT}.tsx")
except Exception as e:
    print(f"失败: {type(e).__name__} {str(e)[:150]}")
