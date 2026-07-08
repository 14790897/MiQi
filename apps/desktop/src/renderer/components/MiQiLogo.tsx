/**
 * MiQi Logo — glitch M on dark navy rounded square.
 * RGB chromatic aberration + soft blur + outer glow shadow.
 */
export function MiQiLogo({ size = 28 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 64 64"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
    >
      <defs>
        {/* Outer glow shadow */}
        <filter id="logoGlow" x="-20%" y="-20%" width="140%" height="140%">
          <feGaussianBlur in="SourceAlpha" stdDeviation="3" result="blur" />
          <feOffset dx="0" dy="0" />
          <feMerge>
            <feMergeNode in="blur" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>

        {/* Letter blur — shared across all color layers */}
        <filter id="letterBlur">
          <feGaussianBlur stdDeviation="0.4" />
        </filter>
      </defs>

      {/* Outer rounded square — dark navy with glow */}
      <rect
        x="4"
        y="4"
        width="56"
        height="56"
        rx="9"
        ry="9"
        fill="#272c40"
        filter="url(#logoGlow)"
      />

      {/* ── Glitch M layers (RGB chromatic aberration) ── */}

      {/* Red channel — slight left offset */}
      <text
        x="32"
        y="43"
        text-anchor="middle"
        font-family="'Inter', 'Segoe UI', system-ui, sans-serif"
        font-size="30"
        font-weight="900"
        fill="#ff4050"
        filter="url(#letterBlur)"
        opacity="0.55"
        style={{ transform: 'translateX(-1.5px)' }}
      >
        M
      </text>

      {/* Green channel — slight right offset */}
      <text
        x="32"
        y="43"
        text-anchor="middle"
        font-family="'Inter', 'Segoe UI', system-ui, sans-serif"
        font-size="30"
        font-weight="900"
        fill="#40ff60"
        filter="url(#letterBlur)"
        opacity="0.55"
        style={{ transform: 'translateX(1.5px)' }}
      >
        M
      </text>

      {/* Blue base — gold #ffd058, centered */}
      <text
        x="32"
        y="43"
        text-anchor="middle"
        font-family="'Inter', 'Segoe UI', system-ui, sans-serif"
        font-size="30"
        font-weight="900"
        fill="#ffd058"
        filter="url(#letterBlur)"
        opacity="0.85"
      >
        M
      </text>

      {/* White highlight — center bright overlay */}
      <text
        x="32"
        y="43"
        text-anchor="middle"
        font-family="'Inter', 'Segoe UI', system-ui, sans-serif"
        font-size="30"
        font-weight="900"
        fill="#ffd058"
        opacity="0.4"
      >
        M
      </text>
    </svg>
  );
}
