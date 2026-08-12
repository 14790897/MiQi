"""Mock OpenAI-compatible server for desktop E2E (issue #646) — full flow.

State machine driven by tool results already in the request history:

  Round 1: tool_call → ask_user_confirm_card #1 (确认执行方案?, 4 steps)
  Round 2: confirmed → tool_call → web_search (real tool, actually runs)
  Round 3: web_search done → tool_call → write_file (WorkflowDefinition JSON)
  Round 4: file written → tool_call → ask_user_confirm_card #2 (是否上传到 Qraft?)
  Round 5: confirmed → final text (uploaded + project link)

Run:  PYTHONPATH=. .venv/Scripts/python.exe scripts/mock_openai.py
"""
from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, HTTPServer

EXEC_TITLE = "确认执行方案？"
EXEC_MESSAGE = "我将执行 4 个步骤（涉及外网论文下载与价格查询），开始前需要你确认。"
EXEC_STEPS = [
    {"id": "search_papers", "title": "搜索并下载相关论文"},
    {"id": "extract_info", "title": "提取 MOF-5 合成路线与成本信息"},
    {"id": "query_price", "title": "查询供应商价格（国内）"},
    {"id": "generate_report", "title": "生成最终报告"},
]
EXEC_CHOICES = [
    {"id": "confirm", "label": "确认执行"},
    {"id": "adjust", "label": "调整方案"},
    {"id": "cancel", "label": "取消"},
]

UPLOAD_TITLE = "方案已完成，是否上传到 Qraft？"
UPLOAD_MESSAGE = "工作流方案已生成并通过校验，上传后将作为 WorkflowDefinition 发布到 Qraft 平台。"
UPLOAD_CHOICES = [
    {"id": "confirm", "label": "确认上传"},
    {"id": "cancel", "label": "取消"},
]

def _build_steps(text: str) -> list[dict]:
    """动态生成步骤：解析用户调整要求（步数/市场/复杂度），模拟 LLM 理解。"""
    import re

    n = 3
    m = re.search(r"(\d+)\s*步", text)
    if m:
        n = max(3, min(int(m.group(1)), 10))
    market = "海外" if ("海外" in text or "国外" in text or "全球" in text) else ("国内" if "国内" in text else "市场")
    complex_ = any(k in text for k in ("复杂", "足够", "完整", "详细", "全面"))
    if complex_ and n < 5:
        n = 5  # 要求"复杂/完整"时至少 5 步

    steps = [
        {"id": "search_lit", "title": f"搜索{market}文献（MOF-5 合成）"},
        {"id": "extract", "title": f"提取{market}合成路线与成本"},
    ]
    if n >= 4:
        steps.append({"id": "benchmark", "title": f"对比{market}主流合成工艺（溶剂/温度/产率）"})
    if n >= 5:
        steps.append({"id": "sensitivity", "title": "成本敏感性分析（原料价格波动影响）"})
    if complex_ and n >= 6:
        steps.append({"id": "validate", "title": "交叉验证数据来源与精度"})
    steps.append({"id": "report", "title": "生成最终报告"})
    extras = ["供应商报价", "纯度与等级", "供应链风险", "政策与环保影响"]
    while len(steps) < n:
        steps.append({"id": f"step_extra_{len(steps)}", "title": f"补充分析：{extras[len(steps) % len(extras)]}"})
    return steps[:max(n, 3)]


WORKFLOW_JSON = {
    "spec_version": "1.0.0",
    "document_kind": "workflow_definition",
    "metadata": {
        "id": "com.acme.mof-price-report",
        "name": "mof-price-report",
        "title": "MOF-5 市场合成价格报告",
        "version": "1.0.0",
        "description": "查询 MOF-5 合成成本与市场价格并生成报告",
    },
    "interface": {},
    "activation": {"policy": "explicit"},
    "inputs": [],
    "parameters": [],
    "execution": {
        "default_mode": "full",
        "entrypoints": [{"id": "run", "mode": "full", "executor": {"type": "shell"}}],
        "backend_policy": {"strategy": "fixed", "backends": [{"id": "local", "kind": "local"}]},
    },
    "graph": {
        "nodes": [
            {"id": "step1", "title": "步骤一", "kind": "task", "executor": {"type": "shell"},
             "presentation": {"data_view": {}, "action_view": {}}},
            {"id": "step2", "title": "步骤二", "kind": "task", "executor": {"type": "shell"},
             "presentation": {"data_view": {}, "action_view": {}}},
            {"id": "step3", "title": "步骤三", "kind": "task", "executor": {"type": "shell"},
             "presentation": {"data_view": {}, "action_view": {}}},
            {"id": "step4", "title": "步骤四", "kind": "task", "executor": {"type": "shell"},
             "presentation": {"data_view": {}, "action_view": {}}},
        ],
        "edges": [],
    },
    "completion": [{"id": "done", "description": "完成", "severity": "success"}],
}


def _tool_result(messages):
    """Collect (tool_name, output) of the LAST ask_user_confirm_card result."""
    results = []
    for m in messages:
        if m.get("role") == "tool":
            try:
                results.append(json.loads(m.get("content", "{}")))
            except Exception:
                results.append({})
    return results


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def _send(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.startswith("/v1/models"):
            self._send(200, {"object": "list", "data": [{"id": "mock-model", "object": "model"}]})
        else:
            self._send(404, {"error": {"message": "not found"}})

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length)
        try:
            req = json.loads(raw)
        except Exception:
            self._send(400, {"error": {"message": "bad json"}})
            return
        if not self.path.startswith("/v1/chat/completions"):
            self._send(404, {"error": {"message": "not found"}})
            return

        messages = req.get("messages", [])
        results = _tool_result(messages)

        # 用 assistant 消息里的 tool_call 序列判断流程进度（可靠，不看结果内容）
        calls_seen: list[str] = []
        for m in messages:
            if m.get("role") == "assistant" and m.get("tool_calls"):
                for tc in m["tool_calls"]:
                    name = (tc.get("function") or {}).get("name", "")
                    if name:
                        calls_seen.append(name)
        n_search = calls_seen.count("web_search")
        n_write = calls_seen.count("write_file")
        n_confirm_cards = sum(1 for r in results if r.get("status") == "confirmed")

        def tc(name, args, cid="call_x"):
            return {
                "id": cid,
                "object": "chat.completion",
                "created": 0,
                "model": "mock-model",
                "choices": [{
                    "index": 0,
                    "message": {"role": "assistant", "content": None, "tool_calls": [{
                        "id": cid, "type": "function",
                        "function": {"name": name, "arguments": json.dumps(args, ensure_ascii=False)},
                    }]},
                    "finish_reason": "tool_calls",
                }],
                "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20},
            }

        def text(content):
            return {
                "id": "mock-final", "object": "chat.completion", "created": 0, "model": "mock-model",
                "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30},
            }

        # ── state machine（按工具调用序列推进） ──
        if not results:
            print("  [mock] R1 → 确认执行方案卡（4 步骤）")
            self._send(200, tc("ask_user_confirm_card", {
                "title": EXEC_TITLE, "message": EXEC_MESSAGE,
                "steps": EXEC_STEPS, "choices": EXEC_CHOICES,
                "timeout_seconds": 60, "allow_remember_choice": True,
            }, "call_exec_confirm"))
            return

        last = results[-1] if results else {}
        last_role = messages[-1].get("role") if messages else ""
        had_adjust = any(r.get("choice_id") == "adjust" for r in results)

        # 调整闭环：用户已点"调整方案"并输入了调整内容 → 弹调整后方案卡
        if had_adjust and last_role == "user":
            user_text = str(messages[-1].get("content", "")).strip()
            print(f"  [mock] 收到调整输入「{user_text[:30]}」→ 动态生成方案")
            steps = _build_steps(user_text)
            self._send(200, tc("ask_user_confirm_card", {
                "title": EXEC_TITLE,
                "message": f"已按你的要求调整（{user_text[:60]}），请再次确认。",
                "steps": steps, "choices": EXEC_CHOICES,
                "timeout_seconds": 60,
            }, "call_exec_confirm_2"))
            return

        # 刚点了"调整方案" → 引导用户输入调整内容（卡片不承担 controller）
        if last.get("choice_id") == "adjust":
            print("  [mock] 用户选择调整 → 引导输入")
            self._send(200, text(
                "好的，请告诉我如何调整方案。\n"
                "例如：市场改为海外、文献限定 2 篇、只保留前 3 步……"
            ))
            return

        if last.get("status") == "cancelled":
            print(f"  [mock] 用户取消（{last.get('reason','')}）→ 结束")
            self._send(200, text("好的，已取消。需要调整方案随时告诉我。"))
            return

        # confirmed 流程推进（按已发生的工具调用）
        if n_confirm_cards == 1 and n_search == 0:
            print("  [mock] R2 → 真实执行 web_search（MOF-5 合成价格）")
            self._send(200, tc("web_search", {"query": "MOF-5 metal-organic framework synthesis cost price", "max_results": 3}, "call_search"))
            return
        if n_confirm_cards == 1 and n_write == 0:
            print("  [mock] R3 → 真实执行 write_file（生成 WorkflowDefinition JSON）")
            self._send(200, tc("write_file", {
                "path": "mof-price-report.workflow.json",
                "content": json.dumps(WORKFLOW_JSON, ensure_ascii=False, indent=2),
            }, "call_write"))
            return
        if n_confirm_cards == 1:
            print("  [mock] R4 → 上传确认卡")
            self._send(200, tc("ask_user_confirm_card", {
                "title": UPLOAD_TITLE, "message": UPLOAD_MESSAGE,
                "choices": UPLOAD_CHOICES, "timeout_seconds": 60,
            }, "call_upload_confirm"))
            return

        print(f"  [mock] R5 → 上传确认收到 confirmed，输出最终结果")
        self._send(200, text(
            "✅ 已完成并上传：\n"
            "- 工作流：MOF-5 市场合成价格报告（4 节点）\n"
            "- 文件：mof-price-report.workflow.json（已生成在工作区）\n"
            "- 校验：WorkflowSpec v1.0.0 通过\n"
            "- 项目入口：forge.miqroera.com/projects/mof-price-report"
        ))


if __name__ == "__main__":
    port = 8899
    print(f"Mock OpenAI server on http://127.0.0.1:{port}/v1")
    HTTPServer(("127.0.0.1", port), Handler).serve_forever()
