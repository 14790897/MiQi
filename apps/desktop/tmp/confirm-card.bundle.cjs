var __defProp = Object.defineProperty;
var __getOwnPropDesc = Object.getOwnPropertyDescriptor;
var __getOwnPropNames = Object.getOwnPropertyNames;
var __hasOwnProp = Object.prototype.hasOwnProperty;
var __export = (target, all) => {
  for (var name in all)
    __defProp(target, name, { get: all[name], enumerable: true });
};
var __copyProps = (to, from, except, desc) => {
  if (from && typeof from === "object" || typeof from === "function") {
    for (let key of __getOwnPropNames(from))
      if (!__hasOwnProp.call(to, key) && key !== except)
        __defProp(to, key, { get: () => from[key], enumerable: !(desc = __getOwnPropDesc(from, key)) || desc.enumerable });
  }
  return to;
};
var __toCommonJS = (mod) => __copyProps(__defProp({}, "__esModule", { value: true }), mod);

// src/renderer/features/chat/components/ConfirmCard.tsx
var ConfirmCard_exports = {};
__export(ConfirmCard_exports, {
  ConfirmCard: () => ConfirmCard
});
module.exports = __toCommonJS(ConfirmCard_exports);
var import_react = require("react");
function ConfirmCard({
  entry,
  onResolve,
  nowFn = () => (/* @__PURE__ */ new Date()).toLocaleTimeString("zh-CN", { hour12: false })
}) {
  const req = entry.request;
  const state = entry.state;
  const isWaiting = state === "pending";
  const choices = req.choices && req.choices.length > 0 ? req.choices : DEFAULT_CHOICES;
  const steps = req.steps ?? [];
  const timeout = req.timeout_seconds ?? 120;
  const [remaining, setRemaining] = (0, import_react.useState)(timeout);
  const [countdownDone, setCountdownDone] = (0, import_react.useState)(false);
  const timerRef = (0, import_react.useRef)(null);
  (0, import_react.useEffect)(() => {
    if (!isWaiting) return;
    setRemaining(timeout);
    setCountdownDone(false);
    timerRef.current = setInterval(() => {
      setRemaining((r) => {
        const next = Math.max(0, r - 1);
        if (next <= 0) {
          if (timerRef.current) clearInterval(timerRef.current);
          setCountdownDone(true);
        }
        return next;
      });
    }, 1e3);
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [isWaiting, timeout]);
  const [remember, setRemember] = (0, import_react.useState)(false);
  const badgeStyle = state === "pending" ? { background: "var(--accent-soft)", color: "var(--accent-hover)" } : state === "confirmed" ? { background: "var(--success-bg)", color: "var(--success-text)" } : { background: "var(--surface-3)", color: "var(--text-muted)" };
  const borderClass = isWaiting ? { borderColor: "var(--accent)", boxShadow: "0 0 0 3px rgba(51,156,255,.16)" } : state === "confirmed" ? { borderColor: "var(--border-subtle)", boxShadow: "none" } : { borderColor: "var(--border-subtle)", boxShadow: "none", background: "var(--surface-muted)", opacity: 0.9 };
  return /* @__PURE__ */ React.createElement(
    "div",
    {
      className: "rounded-xl p-4 max-w-[600px] relative overflow-hidden",
      style: { border: "1px solid var(--border-subtle)", ...borderClass, transition: "all .35s cubic-bezier(.22,.8,.32,1)" }
    },
    /* @__PURE__ */ React.createElement(
      "div",
      {
        className: "absolute top-0 left-0 right-0",
        style: {
          height: 3,
          background: state === "pending" ? "linear-gradient(90deg, var(--accent), transparent)" : state === "confirmed" ? "linear-gradient(90deg, var(--success), transparent)" : "none"
        }
      }
    ),
    /* @__PURE__ */ React.createElement("div", { className: "flex items-center gap-2.5 mb-2.5" }, /* @__PURE__ */ React.createElement(
      "span",
      {
        className: "w-[26px] h-[26px] rounded-lg flex items-center justify-center text-sm shrink-0",
        style: {
          background: isWaiting ? "var(--accent-soft)" : state === "confirmed" ? "var(--success-bg)" : "var(--surface-3)",
          color: isWaiting ? "var(--accent-hover)" : state === "confirmed" ? "var(--success-text)" : "var(--text-faint)"
        }
      },
      req.title?.includes("\u4E0A\u4F20") ? "\u{1F4E4}" : req.title?.includes("\u8865\u5145") ? "\u2753" : "\u{1F4CB}"
    ), /* @__PURE__ */ React.createElement("span", { className: "text-[14.5px] font-semibold tracking-[.01em]" }, req.title), /* @__PURE__ */ React.createElement("span", { className: "ml-auto text-[11px] font-semibold rounded-full px-2.5 py-0.5 whitespace-nowrap", style: badgeStyle }, state === "pending" ? "\u7B49\u5F85\u4F60\u7684\u9009\u62E9" : state === "confirmed" ? "\u2713 \u5DF2\u786E\u8BA4" : "\u5DF2\u53D6\u6D88")),
    /* @__PURE__ */ React.createElement("div", { className: "text-[13px] mb-3", style: { color: "var(--text-muted)" } }, req.message),
    steps.length > 0 && /* @__PURE__ */ React.createElement("div", { className: "flex flex-col gap-1.5 mb-3" }, steps.map((s, i) => /* @__PURE__ */ React.createElement("div", { key: s.id, className: "flex gap-2.5 items-baseline text-[13px] py-0.5" }, /* @__PURE__ */ React.createElement(
      "span",
      {
        className: "w-[18px] h-[18px] rounded-full flex items-center justify-center text-[10.5px] font-semibold shrink-0",
        style: { background: "var(--surface-3)", color: "var(--text-faint)" }
      },
      i + 1
    ), /* @__PURE__ */ React.createElement("span", { className: "flex-1" }, s.title)))),
    isWaiting && /* @__PURE__ */ React.createElement("div", { className: "flex gap-2 flex-wrap" }, choices.map((c) => /* @__PURE__ */ React.createElement(
      "button",
      {
        key: c.id,
        onClick: () => onResolve(c.id, c.label),
        className: "text-[13px] font-medium rounded-lg px-4 py-1.5 cursor-pointer transition-all",
        style: c.id === "cancel" ? { border: "1px solid var(--border)", background: "var(--surface)", color: "var(--danger)" } : { border: "1px solid var(--accent)", background: "var(--accent)", color: "#fff", boxShadow: "0 2px 8px rgba(51,156,255,.35)" },
        onMouseEnter: (e) => {
          if (c.id === "cancel") e.currentTarget.style.background = "var(--danger-bg)";
          else e.currentTarget.style.background = "var(--accent-hover)";
        },
        onMouseLeave: (e) => {
          if (c.id === "cancel") e.currentTarget.style.background = "var(--surface)";
          else e.currentTarget.style.background = "var(--accent)";
        }
      },
      c.label
    ))),
    isWaiting && /* @__PURE__ */ React.createElement("div", { className: "flex items-center gap-3.5 mt-3 text-xs flex-wrap", style: { color: "var(--text-faint)" } }, req.allow_remember_choice && /* @__PURE__ */ React.createElement("label", { className: "flex items-center gap-1.5 cursor-pointer select-none", style: { color: "var(--text-muted)" } }, /* @__PURE__ */ React.createElement("input", { type: "checkbox", checked: remember, onChange: (e) => setRemember(e.target.checked) }), "\u672C\u6B21\u4F1A\u8BDD\u4E0D\u518D\u8BE2\u95EE"), /* @__PURE__ */ React.createElement("div", { className: "flex items-center gap-2 flex-1 min-w-[140px]" }, /* @__PURE__ */ React.createElement("div", { className: "flex-1 h-1 rounded-sm overflow-hidden", style: { background: "var(--surface-3)" } }, /* @__PURE__ */ React.createElement(
      "div",
      {
        className: "h-full rounded-sm",
        style: {
          width: `${remaining / timeout * 100}%`,
          background: remaining <= 5 ? "var(--danger)" : "var(--accent)",
          transition: "width 1s linear"
        }
      }
    )), /* @__PURE__ */ React.createElement("span", { className: "text-[11px] tabular-nums w-[30px] text-right", style: { color: remaining <= 5 ? "var(--danger)" : "var(--text-muted)" } }, remaining, "s"))),
    !isWaiting && /* @__PURE__ */ React.createElement(
      "div",
      {
        className: "flex items-center gap-2 text-[12.5px] mt-3 pt-3",
        style: { borderTop: "1px dashed var(--border-subtle)", animation: "msgIn .3s cubic-bezier(.22,.8,.32,1)" }
      },
      /* @__PURE__ */ React.createElement("span", { className: "font-semibold", style: { color: state === "confirmed" ? "var(--success-text)" : "var(--text-muted)" } }, "\u5DF2\u9009\u62E9\u300C", entry.choiceLabel ?? (state === "cancelled" ? "\u53D6\u6D88" : "\u786E\u8BA4"), "\u300D"),
      /* @__PURE__ */ React.createElement("span", { className: "text-[11.5px] tabular-nums", style: { color: "var(--text-faint)" } }, "\xB7 ", entry.resolvedAt ? new Date(entry.resolvedAt).toLocaleTimeString("zh-CN", { hour12: false }) : nowFn())
    )
  );
}
var DEFAULT_CHOICES = [
  { id: "confirm", label: "\u786E\u8BA4\u6267\u884C" },
  { id: "adjust", label: "\u8C03\u6574\u65B9\u6848" },
  { id: "cancel", label: "\u53D6\u6D88" }
];
// Annotate the CommonJS export names for ESM import in node:
0 && (module.exports = {
  ConfirmCard
});
