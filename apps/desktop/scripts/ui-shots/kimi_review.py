import base64, json, urllib.request, time, sys
from pathlib import Path
KEY = "sk-c7u56lz6g4oa1KOwg5neGmNdm0ajrKOGRZrwYQwLpdBUQWBV"
b64 = base64.b64encode(
    (Path(__file__).resolve().parent / "shots" / "plan-card-all.png").read_bytes()
).decode()
ok = False
for attempt in range(3):
    body = json.dumps({
        "model": "kimi-k2.6",
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": "这是 AI 桌面助手「任务计划卡」UI 三态截图（等待确认/执行中/已完成）。视觉设计评审：1) 整体质感问题 2) 信息层级/间距/配色/圆角问题 3) P0/P1 改进建议（问题+改法，中文）。"},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
        ]}],
        "max_tokens": 1200,
    }).encode()
    req = urllib.request.Request("https://api.moonshot.cn/v1/chat/completions", data=body,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {KEY}"})
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            d = json.load(r)
            msg = d["choices"][0]["message"]
            content = msg.get("content") or ""
            reasoning = msg.get("reasoning_content") or ""
            # k2.6 是 reasoning 模型——正文可能在 reasoning_content
            print((content or reasoning or "（无 content）").strip())
            if content and reasoning:
                print("\n--- 附加 reasoning（前 500 字）---\n", reasoning[:500])
            ok = True
            break
    except Exception as e:
        print(f"尝试{attempt+1}失败: {type(e).__name__} {str(e)[:90]}", file=sys.stderr)
        time.sleep(4)
if not ok:
    print("Kimi 网络持续不稳", file=sys.stderr)
