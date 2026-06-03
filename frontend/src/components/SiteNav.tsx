import { Link, NavLink } from "react-router-dom";
import { Gauge } from "lucide-react";

type NavTarget = "home" | "metrics" | "dashboard";

export function SiteNav({ active }: { active?: NavTarget }) {
  return (
    <nav className="siteNav" aria-label="Primary">
      <Link className="siteBrand" to="/">
        <span className="siteBrandMark"><Gauge size={18} /></span>
        AgentEval Harness
      </Link>
      <div className="siteNavLinks">
        <NavLink to="/" className={({ isActive }) => (isActive || active === "home" ? "active" : "")} end>
          Home
        </NavLink>
        <NavLink to="/metrics" className={({ isActive }) => (isActive || active === "metrics" ? "active" : "")}>
          Metrics
        </NavLink>
        <Link className="siteNavCta" to="/dashboard">
          Open dashboard
        </Link>
      </div>
    </nav>
  );
}
