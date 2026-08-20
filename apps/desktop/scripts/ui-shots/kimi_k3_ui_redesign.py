"""Kimi k3 对照 WorkBuddy 参考图重做 MiQi 卡片 UI（用户特别批准）。

输入：5 张参考截图 + 4 个组件源码。输出：可直接替换的改造代码。
"""
import os
import base64
import json
import sys
import time
import urllib.request
from pathlib import Path

KEY = os.environ.get("MOONSHOT_API_KEY", "")
IMAGES = [
    r"C:\Users\admin\AppData\Roaming\Hermes\composer-images\composer_2026-08-19_09-02-13-119_ae01e0.png",
    r"C:\Users\admin\AppData\Roaming\Hermes\composer-images\composer_2026-08-19_09-03-35-014_0a55d1.png",
    r"C:\Users\admin\AppData\Roaming\Hermes\composer-images\composer_2026-08-19_09-04-10-955_f0ec9c.png",
    r"C:\Users\admin\AppData\Roaming\Hermes\composer-images\composer_2026-08-19_09-04-22-656_9b8f27.png",
    r"C:\Users\admin\AppData\Roaming\Hermes\composer-images\composer_2026-08-19_09-04-51-347_66719b.png",
]
BASE = Path(r"D:\Desktop\811\MiQi\apps\desktop\src\renderer\features\chat\components")

CODE = "\n\n".join(
    f"===== {p.name} =====\n{p.read_text(encoding='utf-8')}"
    for p in [BASE / "PlanCard.tsx", BASE / "Timeline.tsx", BASE / "ActionCard.tsx", BASE / "ConfirmCardArea.tsx"]
)

PROMPT = f"""你是顶级 UI 设计师。5 张截图是用户认可的参考产品界面（WorkBuddy 风格——简洁优雅）。
用户强烈不满当前实现（'跟参考完全不是一个东西'），要求**对照截图抄**——要有 UI 设计美感。

# 参考图要点（请仔细看每张图）：
- 卡片：纯白/极浅灰背景、大圆角（16-20px）、细边框、轻微阴影、大量留白
- 主按钮：深色近黑（#1f1f1f 系）、圆角 8-12px、不花哨
- 状态：灰色小字、彩色小圆点（青=运行/绿=完成）、无高饱和色块
- 消息：头像在消息上方一行（小圆头像+名字，正文全宽无气泡）
- 进度：简洁文本步骤（'第 2 步：渲染卡片'）+ 工具灰色小字
- 整体：克制、留白、字重区分、少装饰

# 当前 MiQi 组件源码（要改造的）：

{CODE}

# 任务：
1. 逐组件给出**改造后的完整可替换代码**（PlanCard.tsx / Timeline.tsx / ActionCard.tsx / ConfirmCardArea.tsx）
2. 对照参考图：布局/间距/圆角/颜色/按钮/状态表达全面靠拢 WorkBuddy
3. 保持现有 props/数据流/事件不变（不破坏后端接线）——只改视觉与结构
4. 保留 data-testid（E2E 依赖）：plan-card / timeline / action-card / confirm-card-area
5. 输出格式：每个文件一段 ```tsx 代码块 + 简短说明（改了什么/为什么）"""

content = [{"type": "text", "text": PROMPT}]
for p in IMAGES:
    b64 = base64.b64encode(Path(p).read_bytes()).decode()
    content.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}})

ok = False
for attempt in range(2):
    body = json.dumps({
        "model": "kimi-k3",
        "messages": [{"role": "user", "content": content}],
        "max_tokens": 12000,
    }).encode()
    req = urllib.request.Request("https://api.moonshot.cn/v1/chat/completions", data=body,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {KEY}"})
    try:
        with urllib.request.urlopen(req, timeout=600) as r:
            d = json.load(r)
            msg = d["choices"][0]["message"]
            text = (msg.get("content") or msg.get("reasoning_content") or "").strip()
            Path(r"D:\Desktop\811\MiQi\docs\kimi-k3-ui-改造.md").write_text(text, encoding="utf-8")
            print(f"OK {len(text)} 字符 → docs/kimi-k3-ui-改造.md")
            ok = True
            break
    except Exception as e:
        print(f"尝试{attempt+1}失败: {type(e).__name__} {str(e)[:120]}", file=sys.stderr)
        time.sleep(8)
if not ok:
    print("Kimi k3 调用失败", file=sys.stderr)
