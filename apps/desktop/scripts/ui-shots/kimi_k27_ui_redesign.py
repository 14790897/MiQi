"""Kimi k2.7-code 对照拼图重做卡片 UI（5 图拼 1 张 + 4 组件代码）。"""
import os
import base64
import json
import sys
import time
import urllib.request
from pathlib import Path

KEY = os.environ.get("MOONSHOT_API_KEY", "")
BASE = Path(r"D:\Desktop\811\MiQi\apps\desktop\src\renderer\features\chat\components")
CODE = "\n\n".join(
    f"===== {p.name} =====\n{p.read_text(encoding='utf-8')}"
    for p in [BASE / "PlanCard.tsx", BASE / "Timeline.tsx", BASE / "ActionCard.tsx", BASE / "ConfirmCardArea.tsx"]
)
b64 = base64.b64encode(Path(r"D:\Desktop\811\MiQi\docs\workbuddy-5张参考-拼图.png").read_bytes()).decode()

PROMPT = f"""5 张参考截图拼成一张（从左到右）。这是用户认可的参考产品 UI（简洁优雅：大圆角白卡 16-20px、深色近黑主按钮 #1f1f1f、灰色状态小字、彩色小圆点状态、头像在消息上方一行、大量留白、克制少装饰）。用户强烈不满当前实现（'跟参考完全不是一个东西'），要求**对照拼图抄**。

# 当前 MiQi 组件源码（要改造的）：
{CODE}

# 任务：
1. 逐组件给**改造后的完整可替换代码**：PlanCard.tsx / Timeline.tsx / ActionCard.tsx / ConfirmCardArea.tsx
2. 对照拼图视觉全面靠拢：卡片圆角 16-20px、近黑主按钮、灰字状态、彩色小圆点、留白、字重层级
3. **保持现有 props/数据流/事件不变**（不破坏后端接线）——只改视觉与结构
4. **保留 data-testid**（E2E 依赖）：plan-card / timeline / action-card / confirm-card-area
5. 输出：每个文件一段 ```tsx 代码块 + 简短说明（改了什么/为什么）"""

content = [{"type": "text", "text": PROMPT}, {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}]
body = json.dumps({"model": "kimi-k2.7-code", "messages": [{"role": "user", "content": content}], "max_tokens": 12000}).encode()

ok = False
for attempt in range(2):
    req = urllib.request.Request("https://api.moonshot.cn/v1/chat/completions", data=body,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {KEY}"})
    try:
        with urllib.request.urlopen(req, timeout=480) as r:
            d = json.load(r)
            msg = d["choices"][0]["message"]
            text = (msg.get("content") or msg.get("reasoning_content") or "").strip()
            Path(r"D:\Desktop\811\MiQi\docs\kimi-k27-ui-改造.md").write_text(text, encoding="utf-8")
            print(f"OK {len(text)} 字符 → docs/kimi-k27-ui-改造.md")
            ok = True
            break
    except Exception as e:
        print(f"尝试{attempt+1}失败: {type(e).__name__} {str(e)[:120]}", file=sys.stderr)
        time.sleep(8)
if not ok:
    print("Kimi 调用失败", file=sys.stderr)
