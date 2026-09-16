import { useEffect, useRef, useState } from "react";
import { inr, inrShort, monthName } from "../lib/format";

type Pt = { day: number; amount: number; cumulative: number };

/** Four round steps that cover v: 36k -> 0,10k,20k,30k,40k */
function niceScale(v: number) {
  const raw = Math.max(v, 1) / 4;
  const p = 10 ** Math.floor(Math.log10(raw));
  const n = raw / p;
  const step = (n <= 1 ? 1 : n <= 2 ? 2 : n <= 5 ? 5 : 10) * p;
  const max = Math.ceil(Math.max(v, 1) / step) * step;
  return { max, ticks: Array.from({ length: Math.round(max / step) + 1 }, (_, i) => i * step) };
}

/** Cumulative spend this month vs last month - shows pace, not daily noise. */
export function SpendLine({ month, prevMonth, current, previous, uptoDay }: {
  month: string; prevMonth: string; current: Pt[]; previous: Pt[]; uptoDay: number;
}) {
  const wrap = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(640);
  const [hover, setHover] = useState<number | null>(null);

  useEffect(() => {
    const el = wrap.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => setWidth(Math.max(280, Math.round(e.contentRect.width))));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const height = width < 500 ? 220 : 260;
  const m = { top: 12, right: width < 500 ? 64 : 92, bottom: 26, left: 48 };
  const iw = width - m.left - m.right;
  const ih = height - m.top - m.bottom;
  const cur = current.slice(0, uptoDay);
  const days = Math.max(current.length, previous.length);
  const { max: maxV, ticks } = niceScale(Math.max(...cur.map((p) => p.cumulative), ...previous.map((p) => p.cumulative), 1));
  const x = (d: number) => m.left + ((d - 1) / (days - 1)) * iw;
  const y = (v: number) => m.top + ih - (v / maxV) * ih;
  const path = (pts: Pt[]) => pts.map((p, i) => `${i ? "L" : "M"}${x(p.day).toFixed(1)},${y(p.cumulative).toFixed(1)}`).join("");
  const xt = [1, 8, 15, 22, 29].filter((d) => d <= days);

  const lastCur = cur[cur.length - 1];
  const lastPrev = previous[previous.length - 1];
  // keep the two end labels from colliding
  let yCur = lastCur ? y(lastCur.cumulative) : 0;
  let yPrev = lastPrev ? y(lastPrev.cumulative) : 0;
  if (lastCur && lastPrev && Math.abs(yCur - yPrev) < 30) {
    const mid = (yCur + yPrev) / 2;
    const up = yCur <= yPrev;
    yCur = mid + (up ? -15 : 15);
    yPrev = mid + (up ? 15 : -15);
  }

  function onMove(e: React.PointerEvent<SVGRectElement>) {
    const r = e.currentTarget.getBoundingClientRect();
    const d = Math.round(((e.clientX - r.left) / r.width) * (days - 1)) + 1;
    setHover(Math.min(days, Math.max(1, d)));
  }

  const hc = hover ? cur.find((p) => p.day === hover) : undefined;
  const hp = hover ? previous.find((p) => p.day === hover) : undefined;
  const curLabel = monthName(month);
  const prevLabel = monthName(prevMonth);

  return (
    <div className="chart-wrap" ref={wrap}>
      <div className="chart-legend">
        <span className="key"><span className="swatch" />{curLabel}</span>
        <span className="key"><span className="swatch dashed" />{prevLabel}</span>
      </div>
      <svg width={width} height={height} role="img"
        aria-label={`Cumulative spending: ${curLabel} ${inr(lastCur?.cumulative ?? 0)} by day ${uptoDay}; ${prevLabel} ${inr(lastPrev?.cumulative ?? 0)} in total`}>
        {ticks.map((t) => (
          <g key={t}>
            <line x1={m.left} x2={m.left + iw} y1={y(t)} y2={y(t)} stroke={t === 0 ? "#4a4f49" : "#e4dccb"} strokeWidth={1} />
            <text x={m.left - 8} y={y(t)} dy="0.32em" textAnchor="end" fontSize={11} fill="#6f6a5d" style={{ fontVariantNumeric: "tabular-nums" }}>
              {inrShort(t)}
            </text>
          </g>
        ))}
        {xt.map((d) => (
          <text key={d} x={x(d)} y={height - 6} textAnchor="middle" fontSize={11} fill="#6f6a5d">{d}</text>
        ))}
        <path d={path(previous)} fill="none" stroke="#8a8272" strokeWidth={2} strokeDasharray="5 4" strokeLinejoin="round" />
        {cur.length > 0 && (
          <>
            <path d={`${path(cur)}L${x(cur[cur.length - 1].day)},${y(0)}L${x(1)},${y(0)}Z`} fill="#2a6a4c" opacity={0.07} />
            <path d={path(cur)} fill="none" stroke="#2a6a4c" strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
          </>
        )}
        {lastPrev && (
          <text x={x(lastPrev.day) + 8} y={yPrev} dy="0.32em" fontSize={12} fill="#4a4f49">
            <tspan fontWeight={600}>{prevLabel.slice(0, 3)}</tspan> {inrShort(lastPrev.cumulative)}
          </text>
        )}
        {lastCur && (
          <>
            <circle cx={x(lastCur.day)} cy={y(lastCur.cumulative)} r={4} fill="#2a6a4c" stroke="#fbf8f1" strokeWidth={2} />
            <text x={Math.max(x(lastCur.day), x(lastPrev?.day ?? 1)) + 8} y={yCur} dy="0.32em" fontSize={12} fill="#1d2420">
              <tspan fontWeight={600}>{curLabel.slice(0, 3)}</tspan> {inrShort(lastCur.cumulative)}
            </text>
          </>
        )}
        {hover && (
          <g pointerEvents="none">
            <line x1={x(hover)} x2={x(hover)} y1={m.top} y2={m.top + ih} stroke="#1d2420" strokeOpacity={0.35} />
            {hp && <circle cx={x(hover)} cy={y(hp.cumulative)} r={4} fill="#8a8272" stroke="#fbf8f1" strokeWidth={2} />}
            {hc && <circle cx={x(hover)} cy={y(hc.cumulative)} r={4} fill="#2a6a4c" stroke="#fbf8f1" strokeWidth={2} />}
          </g>
        )}
        <rect x={m.left} y={m.top} width={iw} height={ih} fill="transparent"
          onPointerMove={onMove} onPointerLeave={() => setHover(null)} />
      </svg>
      {hover && (
        <div className="tooltip" style={{ left: Math.min(Math.max(x(hover), 90), width - 90), top: m.top + 30 }}>
          Day {hover}<br />
          {hc ? <>{curLabel}: <b>{inr(hc.cumulative)}</b> (+{inr(hc.amount)})</> : <>{curLabel}: —</>}<br />
          {hp && <>{prevLabel}: <b>{inr(hp.cumulative)}</b></>}
        </div>
      )}
    </div>
  );
}
