import { useEffect, useState } from "react";

export function shortHash(hash: string): string {
  const digest = hash.slice(hash.lastIndexOf(":") + 1);
  return digest.length <= 12 ? digest : `${digest.slice(0, 8)}…${digest.slice(-4)}`;
}

function CopyButton({ text, label }: { text: string; label: string }) {
  const [state, setState] = useState<"idle" | "copied" | "failed">("idle");
  useEffect(() => {
    if (state === "idle") return;
    const timer = window.setTimeout(() => setState("idle"), 1500);
    return () => window.clearTimeout(timer);
  }, [state]);

  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
      setState("copied");
    } catch {
      setState("failed");
    }
  }

  return (
    <>
      <button type="button" className="tl-copy" onClick={copy} aria-label={label}>⧉</button>
      <span className="tl-copy__status" role="status">
        {state === "copied" ? "Copied" : state === "failed" ? "Copy failed" : ""}
      </span>
    </>
  );
}

export function HashBadge({ hash, label = "hash" }: { hash: string | null | undefined; label?: string }) {
  if (!hash) return <span className="tl-hash tl-hash--none">— not recorded</span>;
  const colon = hash.lastIndexOf(":");
  const algo = colon > 0 ? hash.slice(0, colon) : null;
  return (
    <span className="tl-hash">
      <code title={hash} aria-label={`${label} ${hash}`}>
        {algo && <span className="tl-hash__algo" aria-hidden="true">{algo}:</span>}
        <span aria-hidden="true">{shortHash(hash)}</span>
      </code>
      <CopyButton text={hash} label={`Copy ${label}`} />
    </span>
  );
}
