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
  onTimeout,
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
  const timedOutNotified = (0, import_react.useRef)(false);
  (0, import_react.useEffect)(() => {
    if (countdownDone && !timedOutNotified.current) {
      timedOutNotified.current = true;
      onTimeout?.(req.input_id);
    }
  }, [countdownDone, onTimeout, req.input_id]);
  const timedOut = isWaiting && countdownDone;
  const effectiveState = timedOut ? "cancelled" : state;
  const effectiveWaiting = isWaiting && !timedOut;
  const [remember, setRemember] = (0, import_react.useState)(false);
  const MAX_VISIBLE_STEPS = 5;
  const [stepsExpanded, setStepsExpanded] = (0, import_react.useState)(false);
  const stepsCollapsed = steps.length > MAX_VISIBLE_STEPS && !stepsExpanded;
  const visibleSteps = stepsCollapsed ? steps.slice(0, MAX_VISIBLE_STEPS) : steps;
  const badgeStyle = effectiveState === "pending" ? { background: "var(--accent-soft)", color: "var(--accent-hover)" } : effectiveState === "confirmed" ? { background: "var(--success-bg)", color: "var(--success-text)" } : { background: "var(--surface-3)", color: "var(--text-muted)" };
  const borderClass = effectiveWaiting ? { borderColor: "var(--accent)", boxShadow: "0 2px 14px rgba(51,156,255,.10)" } : effectiveState === "confirmed" ? { borderColor: "var(--border-subtle)", boxShadow: "none" } : { borderColor: "var(--border-subtle)", boxShadow: "none", background: "var(--surface-muted)", opacity: 0.85 };
  const doneCount = steps.filter((x) => entry.stepsStatus?.[x.id]?.status === "success").length;
  const progressPct = steps.length > 0 ? Math.round(doneCount / steps.length * 100) : 0;
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
          height: 2,
          background: effectiveState === "pending" ? "linear-gradient(90deg, var(--accent), transparent)" : effectiveState === "confirmed" ? "linear-gradient(90deg, var(--success), transparent)" : "none",
          animation: effectiveWaiting ? "accentPulse 1.8s ease-in-out infinite" : "none"
        }
      }
    ),
    /* @__PURE__ */ React.createElement("div", { className: "flex items-center gap-2.5 mb-2" }, /* @__PURE__ */ React.createElement(
      "span",
      {
        className: "w-[26px] h-[26px] rounded-lg flex items-center justify-center text-sm shrink-0",
        style: {
          background: effectiveWaiting ? "var(--accent-soft)" : effectiveState === "confirmed" ? "var(--success-bg)" : "var(--surface-3)",
          color: effectiveWaiting ? "var(--accent-hover)" : effectiveState === "confirmed" ? "var(--success-text)" : "var(--text-faint)"
        }
      },
      req.title?.includes("\u4E0A\u4F20") ? "\u{1F4E4}" : req.title?.includes("\u8865\u5145") ? "\u2753" : "\u{1F4CB}"
    ), /* @__PURE__ */ React.createElement(
      "span",
      {
        className: "text-[14.5px] font-semibold tracking-[.01em]",
        style: { color: effectiveState === "cancelled" || timedOut ? "var(--text-muted)" : "inherit" }
      },
      req.title
    ), /* @__PURE__ */ React.createElement("span", { className: "ml-auto text-[11px] font-semibold rounded-full px-2.5 py-0.5 whitespace-nowrap inline-flex items-center gap-1.5", style: badgeStyle }, effectiveWaiting && /* @__PURE__ */ React.createElement(
      "span",
      {
        className: "w-[6px] h-[6px] rounded-full inline-block",
        style: { background: "var(--accent)", animation: "turnPulse 1.1s ease-in-out infinite" }
      }
    ), timedOut ? "\u23F1 \u5DF2\u8D85\u65F6" : effectiveState === "pending" ? "\u7B49\u5F85\u4F60\u7684\u9009\u62E9" : effectiveState === "confirmed" ? "\u2713 \u5DF2\u786E\u8BA4" : "\u5DF2\u53D6\u6D88")),
    /* @__PURE__ */ React.createElement("div", { className: "text-[13px] mb-3", style: { color: "var(--text-muted)" } }, req.message),
    steps.length > 0 && effectiveState === "pending" && /* @__PURE__ */ React.createElement("div", { className: "flex flex-col gap-1.5 mb-3" }, visibleSteps.map((s, i) => /* @__PURE__ */ React.createElement("div", { key: s.id, className: "flex gap-2.5 items-baseline text-[13px] py-0.5" }, /* @__PURE__ */ React.createElement(
      "span",
      {
        className: "w-[18px] h-[18px] rounded-full flex items-center justify-center text-[10.5px] font-semibold shrink-0",
        style: { background: "var(--surface-3)", color: "var(--text-faint)" }
      },
      i + 1
    ), /* @__PURE__ */ React.createElement("span", { className: "flex-1" }, s.title))), stepsCollapsed && /* @__PURE__ */ React.createElement(
      "button",
      {
        onClick: () => setStepsExpanded(true),
        className: "text-[11.5px] cursor-pointer hover:underline self-center mt-1",
        style: { color: "var(--accent-hover)", background: "none", border: "none", fontFamily: "inherit" }
      },
      "\u5C55\u5F00\u5168\u90E8 ",
      steps.length,
      " \u4E2A\u6B65\u9AA4"
    )),
    steps.length > 0 && effectiveState === "confirmed" && !timedOut && /* @__PURE__ */ React.createElement("div", { className: "flex flex-col gap-1.5 mb-3", "data-testid": "steps-live" }, /* @__PURE__ */ React.createElement(
      "div",
      {
        className: "h-[3px] rounded-full overflow-hidden mb-1.5",
        style: { background: "var(--surface-3)" }
      },
      /* @__PURE__ */ React.createElement(
        "div",
        {
          className: "h-full rounded-full",
          style: {
            width: `${progressPct}%`,
            background: "var(--accent)",
            transition: "width .5s cubic-bezier(.22,.8,.32,1)"
          }
        }
      )
    ), steps.map((s, i) => {
      const st = entry.stepsStatus?.[s.id] ?? { status: "pending" };
      const ico = st.status === "running" ? "\u27F3" : st.status === "success" ? "\u2713" : st.status === "failed" ? "!" : "\u25CB";
      const sub = st.status === "running" ? /* @__PURE__ */ React.createElement("span", { className: "text-[11px]", style: { color: "var(--accent-hover)" } }, "\u6B63\u5728\u6267\u884C\u2026") : st.status === "success" ? /* @__PURE__ */ React.createElement("span", { className: "text-[11px]", style: { color: "var(--success-text)" } }, /* @__PURE__ */ React.createElement("span", { style: { color: "var(--success)" } }, "\u2713"), " ", st.result ?? "\u5DF2\u5B8C\u6210", st.dur ? /* @__PURE__ */ React.createElement("span", { style: { color: "var(--text-faint)" } }, " \xB7 \u23F1 ", st.dur) : null) : st.status === "failed" ? /* @__PURE__ */ React.createElement("span", { className: "text-[11px]", style: { color: "var(--danger)" } }, "\u6267\u884C\u5931\u8D25") : /* @__PURE__ */ React.createElement("span", { className: "text-[11px]", style: { color: "var(--text-faint)" } }, "\u7B49\u5F85\u6267\u884C");
      return /* @__PURE__ */ React.createElement(StepLiveRow, { key: s.id, index: i, step: s, st, sub, ico });
    }), /* @__PURE__ */ React.createElement("span", { className: "text-[11px] tabular-nums mt-0.5", style: { color: "var(--text-faint)" } }, "\u5DF2\u5B8C\u6210 ", steps.filter((x) => entry.stepsStatus?.[x.id]?.status === "success").length, " / ", steps.length)),
    effectiveWaiting && /* @__PURE__ */ React.createElement("div", { className: "flex gap-2 flex-wrap items-center" }, choices.map((c) => {
      if (c.id === "cancel") {
        return /* @__PURE__ */ React.createElement(
          "button",
          {
            key: c.id,
            onClick: () => onResolve(c.id, c.label),
            className: "text-[12.5px] font-medium px-2.5 py-1.5 cursor-pointer transition-all rounded-lg",
            style: { background: "none", border: "none", color: "var(--text-faint)", fontFamily: "inherit" },
            onMouseEnter: (e) => {
              e.currentTarget.style.color = "var(--text-muted)";
            },
            onMouseLeave: (e) => {
              e.currentTarget.style.color = "var(--text-faint)";
            }
          },
          c.label
        );
      }
      if (c.id === "adjust") {
        return /* @__PURE__ */ React.createElement(
          "button",
          {
            key: c.id,
            onClick: () => onResolve(c.id, c.label),
            className: "text-[12.5px] font-medium rounded-lg px-3.5 py-1.5 cursor-pointer transition-all",
            style: { border: "1px solid var(--border)", background: "var(--surface)", color: "var(--text-muted)", fontFamily: "inherit" },
            onMouseEnter: (e) => {
              e.currentTarget.style.borderColor = "var(--accent)";
              e.currentTarget.style.color = "var(--accent-hover)";
            },
            onMouseLeave: (e) => {
              e.currentTarget.style.borderColor = "var(--border)";
              e.currentTarget.style.color = "var(--text-muted)";
            }
          },
          c.label
        );
      }
      return /* @__PURE__ */ React.createElement(
        "button",
        {
          key: c.id,
          onClick: () => onResolve(c.id, c.label),
          className: "text-[13px] font-semibold rounded-lg px-4 py-1.5 cursor-pointer transition-all",
          style: { border: "1px solid var(--accent)", background: "var(--accent)", color: "#fff", fontFamily: "inherit" },
          onMouseEnter: (e) => {
            e.currentTarget.style.background = "var(--accent-hover)";
          },
          onMouseLeave: (e) => {
            e.currentTarget.style.background = "var(--accent)";
          }
        },
        c.label
      );
    })),
    effectiveWaiting && /* @__PURE__ */ React.createElement("div", { className: "flex items-center gap-3.5 mt-3 text-xs flex-wrap", style: { color: "var(--text-faint)" } }, req.allow_remember_choice && /* @__PURE__ */ React.createElement("label", { className: "flex items-center gap-1.5 cursor-pointer select-none", style: { color: "var(--text-muted)" } }, /* @__PURE__ */ React.createElement("input", { type: "checkbox", checked: remember, onChange: (e) => setRemember(e.target.checked) }), "\u4EE5\u540E\u81EA\u52A8\u5904\u7406\u7C7B\u4F3C\u64CD\u4F5C"), /* @__PURE__ */ React.createElement("div", { className: "flex items-center gap-2 flex-1 min-w-[140px]" }, /* @__PURE__ */ React.createElement("div", { className: "flex-1 h-1 rounded-sm overflow-hidden", style: { background: "var(--surface-3)" } }, /* @__PURE__ */ React.createElement(
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
    !effectiveWaiting && /* @__PURE__ */ React.createElement(
      "div",
      {
        className: "flex items-center gap-2.5 mt-3 pt-3",
        style: { borderTop: "1px dashed var(--border-subtle)", animation: "msgIn .3s cubic-bezier(.22,.8,.32,1)" }
      },
      timedOut ? /* @__PURE__ */ React.createElement(
        "span",
        {
          className: "inline-flex items-center gap-1.5 rounded-lg px-3 py-1 text-[12px] font-semibold",
          style: { background: "var(--surface-3)", color: "var(--text-muted)" }
        },
        /* @__PURE__ */ React.createElement("span", { style: { fontSize: 11 } }, "\u23F1"),
        "\u7B49\u5F85\u8D85\u65F6\uFF0C\u5DF2\u81EA\u52A8\u53D6\u6D88"
      ) : /* @__PURE__ */ React.createElement(
        "span",
        {
          className: "inline-flex items-center gap-1.5 rounded-lg px-3 py-1 text-[12px] font-semibold",
          style: {
            background: state === "confirmed" ? "var(--success-bg)" : "var(--surface-3)",
            color: state === "confirmed" ? "var(--success-text)" : "var(--text-muted)"
          }
        },
        /* @__PURE__ */ React.createElement("span", { style: { fontSize: 11 } }, state === "confirmed" ? "\u2713" : "\u25CB"),
        "\u5DF2\u9009\u62E9\u300C",
        entry.choiceLabel ?? (state === "cancelled" ? "\u53D6\u6D88" : "\u786E\u8BA4"),
        "\u300D"
      ),
      /* @__PURE__ */ React.createElement("span", { className: "text-[11px] tabular-nums", style: { color: "var(--text-faint)" } }, entry.resolvedAt ? new Date(entry.resolvedAt).toLocaleTimeString("zh-CN", { hour12: false }) : nowFn())
    ),
    !effectiveWaiting && /* @__PURE__ */ React.createElement("div", { className: "mt-2 text-[10.5px]", style: { color: "var(--text-faint)" } }, "\u{1F512} \u5DF2\u5B8C\u6210 \xB7 \u672C\u6B21\u9009\u62E9\u5DF2\u8BB0\u5F55")
  );
}
function StepLiveRow({
  index,
  step,
  st,
  sub,
  ico
}) {
  const [open, setOpen] = (0, import_react.useState)(false);
  return /* @__PURE__ */ React.createElement("div", { className: "flex gap-2.5 text-[13px] py-0.5" }, /* @__PURE__ */ React.createElement(
    "span",
    {
      className: "w-[18px] h-[18px] rounded-full flex items-center justify-center text-[10.5px] font-semibold shrink-0 mt-0.5",
      style: {
        background: st.status === "success" ? "var(--success-bg)" : st.status === "failed" ? "var(--danger-bg)" : "var(--surface-3)",
        color: st.status === "success" ? "var(--success-text)" : st.status === "failed" ? "var(--danger)" : st.status === "running" ? "var(--accent-hover)" : "var(--text-faint)"
      }
    },
    ico
  ), /* @__PURE__ */ React.createElement("div", { className: "flex-1 min-w-0" }, /* @__PURE__ */ React.createElement("div", { className: "font-medium" }, index + 1, ". ", step.title), sub, st.status !== "pending" && /* @__PURE__ */ React.createElement("div", { className: "mt-0.5" }, /* @__PURE__ */ React.createElement(
    "button",
    {
      onClick: () => setOpen(!open),
      className: "text-[10.5px] cursor-pointer hover:underline",
      style: { color: "var(--text-faint)", background: "none", border: "none", fontFamily: "inherit" }
    },
    /* @__PURE__ */ React.createElement("span", { style: { display: "inline-block", transform: open ? "rotate(90deg)" : "none", transition: "transform .2s" } }, "\u25B8"),
    " ",
    "\u6280\u672F\u8BE6\u60C5"
  ), open && /* @__PURE__ */ React.createElement(
    "div",
    {
      className: "mt-1 rounded-md p-2 text-[11px] flex flex-col gap-1",
      style: { background: "var(--surface-3)" }
    },
    /* @__PURE__ */ React.createElement("div", null, /* @__PURE__ */ React.createElement("span", { className: "font-semibold mr-2", style: { color: "var(--text-faint)" } }, "Tool"), /* @__PURE__ */ React.createElement("span", { className: "font-mono" }, st.tool ?? "-")),
    /* @__PURE__ */ React.createElement("div", null, /* @__PURE__ */ React.createElement("span", { className: "font-semibold mr-2", style: { color: "var(--text-faint)" } }, "\u53C2\u6570"), /* @__PURE__ */ React.createElement("span", { className: "font-mono break-all" }, st.param ?? "-")),
    /* @__PURE__ */ React.createElement("div", null, /* @__PURE__ */ React.createElement("span", { className: "font-semibold mr-2", style: { color: "var(--text-faint)" } }, "\u7ED3\u679C"), /* @__PURE__ */ React.createElement("span", { className: "break-all" }, st.result ?? "-")),
    st.dur ? /* @__PURE__ */ React.createElement("div", null, /* @__PURE__ */ React.createElement("span", { className: "font-semibold mr-2", style: { color: "var(--text-faint)" } }, "\u8017\u65F6"), /* @__PURE__ */ React.createElement("span", null, st.dur)) : null
  ))));
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
