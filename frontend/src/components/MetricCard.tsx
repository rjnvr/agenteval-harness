import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { Info } from "lucide-react";

export function MetricCard({
  label,
  value,
  helper,
  icon,
  info,
  infoHref,
}: {
  label: string;
  value: string;
  helper: string;
  icon: ReactNode;
  info?: string;
  infoHref?: string;
}) {
  return (
    <section className="metric">
      <div className="metricIcon">{icon}</div>
      <div>
        <p>
          {label}
          {info && (
            <span className="metricInfo" tabIndex={0} role="note" aria-label={`${label}: ${info}`}>
              <Info size={13} />
              <span className="metricPopup" role="tooltip">
                {info}
                {infoHref && (
                  <Link className="metricPopupLink" to={infoHref}>
                    Read more
                  </Link>
                )}
              </span>
            </span>
          )}
        </p>
        <strong>{value}</strong>
        <span>{helper}</span>
      </div>
    </section>
  );
}
