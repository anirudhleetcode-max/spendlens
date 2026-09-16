import { useEffect, useState } from "react";
import { apiBlob } from "../lib/api";

/** <img> can't send the bearer token, so fetch the image and show it from an object URL. */
export function ReceiptImage({ id, alt, fallback }: { id: string; alt: string; fallback?: string | null }) {
  const [url, setUrl] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let revoke: string | null = null;
    let live = true;
    apiBlob(`/api/receipts/${id}/image`)
      .then(({ blob }) => {
        if (!live) return;
        revoke = URL.createObjectURL(blob);
        setUrl(revoke);
      })
      .catch(() => live && setFailed(true));
    return () => { live = false; if (revoke) URL.revokeObjectURL(revoke); };
  }, [id]);
  const src = url ?? fallback;
  if (failed && !fallback) return <p className="muted small">Couldn't load the receipt image.</p>;
  if (!src) return <p className="muted small">Loading image…</p>;
  return <img src={src} alt={alt} />;
}
