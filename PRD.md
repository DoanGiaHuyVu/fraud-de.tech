# Product Requirements Document (PRD): Sentinel

**Version:** 1.0 | **Event:** Valsoft MPC Hacks 24-Hour Challenge

---

## 1. The User

**Primary User: Level 1 Fraud Analyst / Trust & Safety Reviewer**

This analyst reviews flagged transactions as their core job function. Their day-to-day reality:
- They process hundreds of alerts per shift and are judged on two conflicting KPIs: **Handle Time** (seconds per case) and **Decision Accuracy** (minimizing both false positives and missed fraud).
- Today's tooling forces them to jump between 5+ tabs: a raw alert table, a card history database, an IP lookup tool, a geo-map, and a CRM — just to understand one transaction.
- Alert fatigue is real. When every row looks the same, reviewers start making pattern-matching errors.

**Secondary User: Senior Analyst / Fraud Investigator (Escalation Target)**

This person receives escalated cases (likely Account Takeovers) and needs the full audit trail of what the L1 analyst saw and why they escalated. They are not the primary UI user but consume the `audit_log.json` output.

---

## 2. The Problem We're Solving

**Alert fatigue caused by context switching and a lack of pre-correlated intelligence.**

Current fraud tools present alerts as a flat table of database rows. The analyst has to manually connect the dots across multiple systems to understand *why* a transaction is suspicious. This makes each decision slow, expensive, and error-prone.

The specific problems we are solving:

1. **Missing context:** A reviewer sees `$1,753 at Apple Gift Card` but has no instant view of the card's history, the merchant's recent volume pattern, or whether the IP is shared with other cards. All of this context lives in separate tools.
2. **No queue flow:** Static tables require the analyst to manually pick the next case. There is no natural forward momentum through the workload.
3. **No feedback loop:** When a reviewer dismisses a false positive, that signal dies. The same merchant triggers another alert 10 minutes later.
4. **No explainability:** A black-box score of "0.87" tells the reviewer nothing. They need to know *which specific signal* triggered the flag.

---

## 3. What We're Building

A single-pane-of-glass fraud review dashboard that:

- **Presents one case at a time** with all relevant context pre-loaded and pre-correlated: card spending history, entity relationship map, geographic IP mapping, merchant volume timeline, and an AI-generated narrative.
- **Accepts keyboard-driven decisions** (A = Approve, D = Dismiss, E = Escalate, Z = Undo) so the analyst never has to touch the mouse.
- **Explains every flag in plain English** (e.g., *"Amount is 36x this card's median; cardholder country CA does not match merchant country US"*).
- **Learns from dismissals in-session** — when the reviewer dismisses a false positive, the merchant's risk score is suppressed for the rest of the session, preventing repeat noise.
- **Writes a full audit trail** (`audit_log.json`) for every decision including timestamp, transaction ID, decision type, escalation reason, and analyst notes — for compliance and senior analyst handoff.

---

## 4. What Success Looks Like

- **Speed:** An analyst can make a confident decision on a flagged transaction in under 15 seconds.
- **Explainability:** No analyst should ever have to wonder why a case is in their queue. The reason is always present, specific, and in plain English.
- **Recall:** The detection engine catches all four fraud patterns present in the dataset without being overwhelmed by false positives.
- **Reproducibility:** A judge can clone the repo, run one command, and have the full dashboard running within 2 minutes.

---

## 5. What We Are Explicitly NOT Building

- **An auto-decline engine.** Every decision requires a human in the loop. The system flags and explains; the analyst decides.
- **A customer-facing application.** This is an internal enterprise tool. UX is optimized for expert analysts, not casual users.
- **A persistent database backend.** For a 1,000-row dataset, in-memory Pandas gives sub-millisecond query times with zero infrastructure overhead. We are optimizing for demo speed, not production scale.
- **Real-time transaction ingestion.** The tool operates on a pre-loaded CSV snapshot. A streaming Kafka pipeline is documented as a future extension in the README.
- **Multi-analyst collaboration / case assignment.** Out of scope for 24 hours. The audit log is designed to support this extension.
