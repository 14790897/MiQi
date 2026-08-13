"""调用 Kimi (moonshot) 视觉模型评审确认卡 UI 截图。
用法: python scripts/ui_shots/review_kimi.py
"""
import base64
import json
import sys
import urllib.request

API_KEY = "sk-c7u56lz6g4oa1KOwg5neGmNdm0ajrKOGRZrwYQwLpdBUQWBV"
ENDPOINT = "https://api.moonshot.cn/v1/chat/completions"
MODEL = "kimi-latest"

SHOTS_DIR = r"D:\Desktop\811\MiQi\apps\desktop\scripts\ui-shots\shots"
SCENES = [
    ("card-pending.png", "等待确认态：AI 想访问外部网页的确认卡"),
    ("card-steps.png", "多步骤方案确认卡（4 步 + 调整按钮）"),
    ("card-confirmed.png", "已确认态（绿色 badge）"),
    ("card-cancelled.png", "已取消态（中性灰）"),
    ("card-timedout.png", "超时态（⏱ 已超时）"),
]

def img_data_url(path: str) -> str:
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    return f"data:image/png;base64,{b64}"

def review() -> str:
    content = [{
        "type": "text",
        "text": (
            "你是资深 UI/UX 设计师。这是 MiQi（AI 桌面助手）的「确认卡片」界面截图，"
            "共 5 个状态场景。请逐张评审，重点：\n"
            "1. 视觉层次与信息密度（标题/内容/按钮是否清晰）\n"
            "2. 状态表达（等待/确认/取消/超时是否一眼可辨）\n"
            "3. 与 ChatGPT/Claude/DeepSeek 等现代 AI 产品卡片对比，哪里不够精致\n"
            "4. 具体、可执行的修改建议（颜色/间距/字号/布局/文案），按优先级 P0/P1/P2 列出\n"
            "5. 最终打分（1-10）\n"
            "用中文回答。"
        ),
    }]
    for fname, desc in SCENES:
        content.append({"type": "image_url", "image_url": {"url": img_data_url(f"{SHOTS_DIR}\\{fname}")}})
        content.append({"type": "text", "text": f"↑ 场景：{desc}"})

    body = json.dumps({
        "model": MODEL,
        "messages": [{"role": "user", "content": content}],
        "temperature": 0.3,
        "max_tokens": 3000,
    }).encode()

    req = urllib.request.Request(
        ENDPOINT, data=body,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {API_KEY}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            data = json.load(r)
        return data["choices"][0]["message"]["content"]
    except urllib.error.HTTPError as e:
        return f"HTTP {e.code}: {e.read().decode()[:800]}"
    except Exception as e:
        return f"ERROR: {e}"

if __name__ == "__main__":
    print(review())
