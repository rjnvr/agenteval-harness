export function ScorePill({ label, value }: { label: string; value: string }) {
  return <div className="scorePill"><span>{label}</span><b>{value}</b></div>;
}
