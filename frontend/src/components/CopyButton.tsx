import { useState } from "react";

export interface CopyButtonProps {
  text: string;
  label?: string;
  copiedLabel?: string;
}

export function CopyButton({
  text,
  label = "Copy",
  copiedLabel = "Copied",
}: CopyButtonProps) {
  const [copied, setCopied] = useState(false);

  async function handleCopy() {
    try {
      if (navigator.clipboard && typeof navigator.clipboard.writeText === "function") {
        await navigator.clipboard.writeText(text);
        setCopied(true);
        window.setTimeout(() => setCopied(false), 1800);
      }
    } catch {
      // Clipboard API restricted; ignore cleanly
    }
  }

  return (
    <button
      type="button"
      className="btn"
      onClick={() => {
        void handleCopy();
      }}
      style={{ padding: "0.35rem 0.7rem", fontSize: "0.78rem" }}
    >
      {copied ? copiedLabel : label}
    </button>
  );
}

