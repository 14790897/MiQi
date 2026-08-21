"""Kimi 主导改造：任务列表（Sidebar）——给代码让它设计改法。"""
import json
import sys
import time
import urllib.request
from pathlib import Path

KEY = os.environ.get("MOONSHOT_API_KEY", "")

SIDEBAR_CODE = Path(
    r"D:\Desktop\811\MiQi\apps\desktop\src\renderer\components\Sidebar.tsx"
).read_text(encoding="utf-8")

PROMPT = f"""你是资深前端 UI 设计师。下面是 MiQi 桌面应用的左侧任务列表组件代码（React + Tailwind + inline style）。

# 参考设计（WorkBuddy 风格，用户指定要学的）：
1. 任务条目：彩色小圆点状态（青=运行中/绿=完成/灰=等待）——不占空间、一眼识别
2. 分组标题灰色小字（任务(2)/空间(1)），细分割线，大量留白
3. 一行一任务，信息密度适中：标题 + 右侧时间，不堆砌
4. 活跃任务（进行中）有呼吸/闪烁动画点
5. 简洁优雅：少装饰、少阴影、靠留白和字重区分

# 当前代码（会话列表部分）：

{SIDEBAR_CODE}

# 任务：
给 MiQi 的任务列表（会话列表区）一个**最小改动**的重设计方案：
1. 具体改哪些 JSX/style（给出修改后的代码块，直接可替换）
2. 保持现有功能（ContextMenu/状态右键/懒加载/重命名）不动
3. 状态点设计：4 种状态（PENDING/IN-PROGRESS/REVIEW/COMPLETED）各用什么色点
4. 克制：只改样式不改结构，避免大重写
输出：修改后的关键 JSX 代码 + 简短说明。"""

ok = False
for attempt in range(3):
    body = json.dumps({
        "model": "kimi-k2.6",
        "messages": [{"role": "user", "content": PROMPT}],
        "max_tokens": 3000,
    }).encode()
    req = urllib.request.Request("https://api.moonshot.cn/v1/chat/completions", data=body,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {KEY}"})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
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
