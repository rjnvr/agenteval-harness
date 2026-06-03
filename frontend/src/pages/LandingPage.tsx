import { Link } from "react-router-dom";
import { ArrowRight, CalendarClock, CheckCircle2, Clock3, GitCompare, Globe2, Play, PlugZap, Scale, Target, Users } from "lucide-react";
import { SiteNav } from "../components/SiteNav";

const AXES = [
  {
    icon: <Target size={20} />,
    title: "Decision Correctness",
    body: "Did the agent pick the right move — propose times, book, decline, reschedule, or ask for availability?",
    anchor: "/metrics#decision-correctness",
  },
  {
    icon: <CheckCircle2 size={20} />,
    title: "Constraint Satisfaction",
    body: "Is the proposed slot actually free for everyone, inside working hours, and grounded in the calendar context?",
    anchor: "/metrics#constraint-satisfaction",
  },
  {
    icon: <Scale size={20} />,
    title: "Preference Adherence",
    body: "Did it honor context-sensitive rules — like “John takes 7 AM calls with CEOs, but not with peers”?",
    anchor: "/metrics#preference-adherence",
  },
  {
    icon: <Globe2 size={20} />,
    title: "Timezone Accuracy",
    body: "Does the slot land on the right instant — not 9 AM London when the request meant 9 AM Pacific?",
    anchor: "/metrics#timezone-accuracy",
  },
  {
    icon: <Users size={20} />,
    title: "Coordination Coverage",
    body: "Did it account for every participant, calendar, preference, and follow-up the case required?",
    anchor: "/metrics#coordination-coverage",
  },
];

const VALUE_PROPS = [
  {
    icon: <CalendarClock size={20} />,
    title: "20 golden scheduling scenarios",
    body: "Preference traps, timezone spread, double-booking traps, missing availability, reschedules, and hard declines — each with a known-correct decision.",
  },
  {
    icon: <CheckCircle2 size={20} />,
    title: "Catch failures before users do",
    body: "Surface double-bookings, ignored preferences, and timezone slips as specific, inspectable failures instead of vague “it felt off.”",
  },
  {
    icon: <GitCompare size={20} />,
    title: "Compare models side by side",
    body: "Run the same suite against Claude, GPT, Gemini, or Llama and compare pass rates, latency, and cost in one table.",
  },
  {
    icon: <PlugZap size={20} />,
    title: "Bring your own agent",
    body: "Point the harness at your own scheduling agent over a webhook and score it on the exact same rubric.",
  },
];

const STEPS = [
  {
    title: "Pick a provider",
    body: "Start with the built-in Mock agent — no API key needed — or plug in Claude, GPT, Gemini, Llama, or your own webhook.",
  },
  {
    title: "Run the suite",
    body: "The harness sends each scenario’s request, context, and allowed actions to the agent and collects its decisions.",
  },
  {
    title: "Inspect failures",
    body: "Read pass rate and the five quality signals, then expand any failed case to see exactly what went wrong and why.",
  },
];

export function LandingPage() {
  return (
    <div className="marketing">
      <SiteNav active="home" />

      <header className="hero">
        <div className="heroCopy">
          <span className="eyebrow">Evaluation for coordination agents</span>
          <h1>Catch scheduling-agent failures before your users do.</h1>
          <p>
            AgentEval Harness runs golden coordination scenarios against your AI scheduling agent, checks whether it chose the
            right action, validates every proposed slot against calendars and preferences, and reports failures in a dashboard.
          </p>
          <div className="heroActions">
            <Link className="primary" to="/dashboard"><Play size={16} />Open dashboard</Link>
            <Link className="secondary" to="/metrics">See the metrics <ArrowRight size={15} /></Link>
          </div>
          <p className="heroNote">No signup. The Mock provider runs locally with no API key.</p>
        </div>
        <div className="heroVisual">
          <img src="/dashboard-summary.png" alt="AgentEval dashboard showing pass rate and quality signals" loading="lazy" />
        </div>
      </header>

      <section className="marketingSection">
        <div className="sectionHead">
          <span className="eyebrow">Why it exists</span>
          <h2>Turn vague scheduling behavior into specific failures</h2>
          <p>Built for assistants that are CC&apos;d on email, SMS, WhatsApp, or Slack and must coordinate meetings from natural language while respecting context-specific preferences.</p>
        </div>
        <div className="valueGrid">
          {VALUE_PROPS.map((item) => (
            <article key={item.title} className="valueCard">
              <div className="valueIcon">{item.icon}</div>
              <h3>{item.title}</h3>
              <p>{item.body}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="marketingSection">
        <div className="sectionHead">
          <span className="eyebrow">What we measure</span>
          <h2>Five things every scheduling decision is scored on</h2>
          <p>Each axis maps to concrete checks in the harness. Click any card for the plain-English definition and examples.</p>
        </div>
        <div className="axisGrid">
          {AXES.map((axis) => (
            <Link key={axis.title} className="axisCard" to={axis.anchor}>
              <div className="axisIcon">{axis.icon}</div>
              <h3>{axis.title}</h3>
              <p>{axis.body}</p>
              <span className="axisLink">Learn more <ArrowRight size={14} /></span>
            </Link>
          ))}
        </div>
      </section>

      <section className="marketingSection">
        <div className="sectionHead">
          <span className="eyebrow">How it works</span>
          <h2>From request to inspectable failure in three steps</h2>
        </div>
        <div className="stepGrid">
          {STEPS.map((step, index) => (
            <article key={step.title} className="stepCard">
              <div className="stepNumber">{index + 1}</div>
              <h3>{step.title}</h3>
              <p>{step.body}</p>
            </article>
          ))}
        </div>
        <div className="detailVisual">
          <img src="/dashboard-case-detail.png" alt="Expanded failed case showing metrics and failure rationale" loading="lazy" />
        </div>
      </section>

      <section className="ctaBand">
        <div>
          <h2>Start with the Mock provider — no API key needed.</h2>
          <p>See how the dashboard scores a competent agent, then swap in your own model or webhook.</p>
        </div>
        <div className="ctaActions">
          <Link className="primary" to="/dashboard"><Play size={16} />Open dashboard</Link>
          <Link className="ctaSecondary" to="/metrics">Read the metrics guide <ArrowRight size={15} /></Link>
        </div>
      </section>

      <footer className="marketingFooter">
        <div className="siteBrand">
          <span className="siteBrandMark"><Clock3 size={16} /></span>
          AgentEval Harness
        </div>
        <div className="marketingFooterLinks">
          <Link to="/dashboard">Dashboard</Link>
          <Link to="/metrics">Metrics</Link>
        </div>
      </footer>
    </div>
  );
}
