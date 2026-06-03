import { Link } from "react-router-dom";
import { ArrowRight, CheckCircle2, Globe2, Scale, Target, Users } from "lucide-react";
import { SiteNav } from "../components/SiteNav";

const CONCEPTS = [
  { term: "Case", def: "One known-good scheduling scenario: a natural-language request, the structured context (participants, calendars, timezones, preferences), and the decision a good agent should reach." },
  { term: "Golden set", def: "The 20 seeded cases the harness evaluates against. They cover preference traps, timezone spread, double-booking traps, missing availability, and reschedules." },
  { term: "Run", def: "One pass of the whole suite for a single provider and model. A run produces one result per case plus aggregate scores." },
  { term: "Result", def: "The evaluation of a single case within a run — the agent’s answer and action, every metric, the failure mode (if any), and the rationale." },
  { term: "Action", def: "The decision the agent must choose: propose_times, book_meeting, decline, propose_alternative, request_availability, or escalate_to_human." },
  { term: "BYO Agent", def: "“Bring Your Own Agent.” Instead of calling a model directly, the harness POSTs each case to your webhook and scores the JSON you return on the same rubric." },
];

const AXES = [
  {
    id: "decision-correctness",
    icon: <Target size={20} />,
    title: "Decision Correctness",
    backing: "tool_correct",
    body: "Checks whether the agent chose the right scheduling action. Booking when it should have requested availability is a decision failure, even if the message is perfectly polite.",
    example: "The request needs a follow-up because a calendar is unknown, but the agent books anyway → decision incorrect.",
  },
  {
    id: "constraint-satisfaction",
    icon: <CheckCircle2 size={20} />,
    title: "Constraint Satisfaction",
    backing: "slot_valid + groundedness",
    body: "Checks whether a proposed slot is free for every participant, inside working hours, and supported by the assembled context. This catches double-booking, outside-hours scheduling, and invented availability.",
    example: "The agent proposes 10:00 when one attendee has a busy block at 10:00 → constraint violated.",
  },
  {
    id: "preference-adherence",
    icon: <Scale size={20} />,
    title: "Preference Adherence",
    backing: "preference_score",
    body: "Checks context-sensitive rules. A slot that is perfectly valid on the calendar can still fail if it breaks a stated preference.",
    example: "John will take a 7 AM call with a CEO, but not with a peer. Proposing 7 AM for a peer meeting → preference violation.",
  },
  {
    id: "timezone-accuracy",
    icon: <Globe2 size={20} />,
    title: "Timezone Accuracy",
    backing: "timezone_correct",
    body: "Checks whether the proposed slot represents the expected instant in time. This catches conversion mistakes between regions.",
    example: "“Thursday morning Pacific” interpreted as 9 AM London → timezone error.",
  },
  {
    id: "coordination-coverage",
    icon: <Users size={20} />,
    title: "Coordination Coverage",
    backing: "fact_recall + retrieval_hit",
    body: "Checks whether the agent considered the required participants, preferences, calendars, and follow-ups. A low score usually means it missed a relevant person or constraint.",
    example: "A three-person meeting where the agent only reasons about two attendees → coverage drops.",
  },
];

const OPERATIONAL = [
  { id: "strict-pass-rate", term: "Strict Pass Rate", def: "The share of cases that passed. Passing is strict: a case only counts as a pass if every quality gate passes — right action, valid slot, honored preferences, correct timezone, full coverage, and valid schema. One failed gate fails the case." },
  { id: "latency-cost", term: "Latency & Cost", def: "Latency is the time to run one case, in milliseconds. Cost is estimated from provider token usage where available. These are operational metrics — they never make up for an unsafe scheduling decision." },
  { id: "judge", term: "LLM Judge & Judge Kappa", def: "Optionally, an extra model call scores semantic correctness against the expected decision. Judge Kappa (Cohen’s kappa) reports how closely the automatic evaluator agrees with human labels: 1.0 is perfect agreement, 0 is chance." },
  { id: "pii-recall", term: "PII Recall", def: "Of the sensitive entities that should have been redacted from agent output, the share that actually were. Higher is safer." },
  { id: "schema-validity", term: "Schema Validity", def: "Whether live model or webhook output followed the JSON contract. Invalid JSON, missing fields, or an unsupported action fail this gate before anything else is scored." },
];

const FAILURE_MODES = [
  ["wrong_action", "The agent chose the wrong scheduling decision."],
  ["double_booking", "The proposed slot overlaps a busy block or fails working-hour constraints."],
  ["outside_working_hours", "The proposed slot is outside a participant’s allowed hours."],
  ["preference_violation", "The agent ignored a contextual rule."],
  ["timezone_error", "The proposed instant or conversion is wrong."],
  ["missed_participant", "The agent missed a participant or required consideration."],
  ["premature_booking", "The agent booked before enough availability was known."],
  ["no_followup", "The agent should have requested availability but did not."],
  ["unsupported_availability", "The agent claimed a slot was supported when the context did not support it."],
  ["schema_invalid", "The response was not parseable or used an unsupported action."],
  ["agent_error", "Provider or webhook execution failed."],
  ["low_answer_quality", "The answer did not match the expected decision well enough."],
];

const CHAIN = [
  "Did the agent receive the right context? Check coordination coverage.",
  "Did it choose the right decision? Check decision correctness.",
  "If it proposed a time, is the slot legal? Check constraint satisfaction.",
  "Did it honor preferences? Check preference adherence.",
  "Did it convert timezones correctly? Check timezone accuracy.",
  "Did it explain the relevant considerations? Check coordination coverage again.",
];

export function MetricsPage() {
  return (
    <div className="metricsDoc">
      <SiteNav active="metrics" />

      <header className="docHero">
        <span className="eyebrow">Metrics, explained</span>
        <h1>What every score means</h1>
        <p>
          AgentEval tests an AI coordination agent: it receives a scheduling request, the assembled context, and a list of
          allowed actions, then must make the right call and return a slot that is safe to execute. This page explains every
          score in plain terms — no prior evals experience needed.
        </p>
      </header>

      <section className="docSection">
        <h2>Core concepts</h2>
        <dl className="glossary">
          {CONCEPTS.map((c) => (
            <div key={c.term} className="glossaryRow">
              <dt>{c.term}</dt>
              <dd>{c.def}</dd>
            </div>
          ))}
        </dl>
      </section>

      <section className="docSection">
        <h2>The five quality axes</h2>
        <p className="docLede">Every scheduling decision is scored on these five axes. Read them as a chain — context in, then decision, then whether the decision was safe and respectful of the people involved.</p>
        <div className="axisDocList">
          {AXES.map((axis) => (
            <article key={axis.id} id={axis.id} className="axisDoc">
              <div className="axisDocHead">
                <span className="axisIcon">{axis.icon}</span>
                <div>
                  <h3>{axis.title}</h3>
                  <code className="backingField">{axis.backing}</code>
                </div>
                <span className="axisRange">0–100%</span>
              </div>
              <p>{axis.body}</p>
              <p className="axisExample"><strong>Example:</strong> {axis.example}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="docSection">
        <h2>Operational &amp; safety metrics</h2>
        <p className="docLede">These are the other numbers on the dashboard. They describe cost, speed, and safety — they do not excuse a bad scheduling decision.</p>
        <dl className="glossary">
          {OPERATIONAL.map((m) => (
            <div key={m.id} id={m.id} className="glossaryRow">
              <dt>{m.term}</dt>
              <dd>{m.def}</dd>
            </div>
          ))}
        </dl>
      </section>

      <section className="docSection">
        <h2>Failure modes</h2>
        <p className="docLede">When a case fails, the harness labels it with exactly one scheduling-specific failure mode so you know where to look.</p>
        <dl className="glossary failureGlossary">
          {FAILURE_MODES.map(([mode, def]) => (
            <div key={mode} className="glossaryRow">
              <dt><code>{mode}</code></dt>
              <dd>{def}</dd>
            </div>
          ))}
        </dl>
      </section>

      <section className="docSection">
        <h2>Reading the metrics together</h2>
        <p className="docLede">The scores are most useful as a chain. Walk them in order to pinpoint the root cause of a failure:</p>
        <ol className="chainList">
          {CHAIN.map((step) => (
            <li key={step}>{step}</li>
          ))}
        </ol>
        <p className="docLede">For example: if coverage is high but preference adherence is low, the agent saw the rule and ignored it. If timezone accuracy is low, the issue is conversion or representation. If constraint satisfaction is low, inspect busy blocks and working hours.</p>
      </section>

      <section className="ctaBand">
        <div>
          <h2>Ready to see it on real runs?</h2>
          <p>Open the dashboard and run the Mock provider — then expand a failed case and map what you see back to this guide.</p>
        </div>
        <div className="ctaActions">
          <Link className="primary" to="/dashboard">Open dashboard <ArrowRight size={15} /></Link>
        </div>
      </section>
    </div>
  );
}
