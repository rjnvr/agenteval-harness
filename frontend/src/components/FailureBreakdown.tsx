export function FailureBreakdown({ counts }: { counts: Record<string, number> }) {
  const entries = Object.entries(counts);
  if (!entries.length) return <div className="emptyBand">No failures in the latest run.</div>;
  const total = entries.reduce((sum, [, value]) => sum + value, 0);
  return (
    <div className="breakdown">
      {entries.map(([label, value]) => (
        <div className="barRow" key={label}>
          <span>{label.replaceAll("_", " ")}</span>
          <div className="barTrack"><div style={{ width: `${Math.max((value / total) * 100, 8)}%` }} /></div>
          <b>{value}</b>
        </div>
      ))}
    </div>
  );
}
