import type { OcrPreview } from "../lib/types";

/** The image Tesseract actually read (after cleanup) with a box per word; low-confidence words stand out. */
export function OcrOverlay({ preview, threshold = 60 }: { preview: OcrPreview; threshold?: number }) {
  const low = preview.boxes.filter((b) => b.conf < threshold).length;
  return (
    <figure className="ocr-overlay" data-testid="ocr-overlay">
      <div className="ocr-canvas" style={{ aspectRatio: `${preview.width} / ${preview.height}` }}>
        <img src={preview.image} alt="Cleaned-up receipt as read by OCR" />
        <svg viewBox="0 0 1 1" preserveAspectRatio="none" aria-hidden>
          {preview.boxes.map((b, i) => (
            <rect key={i} x={b.x} y={b.y} width={b.w} height={b.h}
              className={b.conf < threshold ? "box low" : "box"}>
              <title>{`${b.text} (${b.conf}%)`}</title>
            </rect>
          ))}
        </svg>
      </div>
      <figcaption className="small muted">
        {preview.boxes.length} words read · {low} below {threshold}% confidence (orange)
      </figcaption>
    </figure>
  );
}
