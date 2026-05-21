import { pct } from "../utils";

export function QualitySignal({ label, value, helper }: { label: string; value: number; helper: string }) {
  return (
    <div className="qualitySignal">
      <div><span>{label}</span><b>{pct(value)}</b></div>
      <div className="signalTrack"><div style={{ width: `${Math.max(value * 100, 4)}%` }} /></div>
      <em>{helper}</em>
    </div>
  );
}
