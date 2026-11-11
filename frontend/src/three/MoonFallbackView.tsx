export interface MoonFallbackViewProps {
  label?: string;
  dimmed?: boolean;
  compact?: boolean;
}

export function MoonFallbackView({
  label = "NASA SVS CGI Moon Kit (LROC / LOLA)",
  dimmed = false,
  compact = false,
}: MoonFallbackViewProps) {
  return (
    <div
      style={{
        width: "100%",
        height: "100%",
        minHeight: compact ? "240px" : "360px",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        opacity: dimmed ? 0.36 : 1,
        position: "relative",
        overflow: "hidden",
      }}
      aria-label={label}
    >
      <div
        style={{
          width: compact ? "210px" : "min(54vh, 420px)",
          height: compact ? "210px" : "min(54vh, 420px)",
          borderRadius: "50%",
          overflow: "hidden",
          position: "relative",
          boxShadow:
            "inset -28px -18px 46px rgba(0, 0, 0, 0.78), 0 0 64px rgba(90, 210, 230, 0.08)",
          border: "1px solid rgba(255, 255, 255, 0.14)",
          background: "#1c212b",
        }}
      >
        <img
          src="/assets/moon/moon_albedo_2k.webp"
          alt="Lunar globe surface map from NASA SVS CGI Moon Kit"
          style={{
            width: "200%",
            height: "100%",
            objectFit: "cover",
            objectPosition: "50% 50%",
            display: "block",
            filter: "contrast(1.08) brightness(0.88)",
          }}
        />
      </div>
    </div>
  );
}

