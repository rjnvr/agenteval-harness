export function FactChips({ facts, variant }: { facts: string[]; variant: "matched" | "missed" | "unsupported" }) {
  if (!facts.length) return <p className="muted">None</p>;
  return <div className={`chips ${variant}`}>{facts.map((fact) => <span key={fact}>{fact}</span>)}</div>;
}
