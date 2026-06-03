import { Link } from "react-router-dom";
import { pct } from "../utils";

export function QualitySignal({ label, value, helper, href }: { label: string; value: number; helper: string; href?: string }) {
  return (
    <div className="qualitySignal">
      <div>
        {href ? (
          <Link className="signalLabel" to={href}>{label}</Link>
        ) : (
          <span>{label}</span>
        )}
        <b>{pct(value)}</b>
      </div>
      <div className="signalTrack"><div style={{ width: `${Math.max(value * 100, 4)}%` }} /></div>
      <em>{helper}</em>
    </div>
  );
}
