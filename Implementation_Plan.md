# Implementation Plan: Sentinel

**Version:** 1.0 | **Event:** Valsoft MPC Hacks 24-Hour Challenge

---

## 1. Architecture Overview

Sentinel is a two-process application: a **Python FastAPI backend** (data engine + REST API) and a **Vanilla HTML/CSS/JS frontend** (review dashboard). They communicate over HTTP on `localhost:8000`.

```
transactions.csv
      │
      ▼
 data_prep.py  ──────────────────────────────────────────┐
 (offline preprocessing)                                 │
  • Per-card median baselines                            │
  • Feature engineering (12 features)                    │
  • Random Forest training + probability scoring         │
  • Plain-English explanation generation                 │
      │                                                  │
      ▼                                                  │
 app_data.csv  ◄──────────────────────────────────────── ┘
      │
      ▼
 main.py (FastAPI)              static/
 • Loads app_data.csv           • index.html
   into memory on boot          • style.css
 • REST endpoints:              • app.js
   /api/transactions              ├── Review queue
   /api/card_history              ├── Chart.js (card history, merchant volume)
   /api/fraud_ring                ├── Vis.js (entity relationship map)
   /api/fraud_ring_map            └── Leaflet.js (geographic IP map)
   /api/merchant_volume
   /api/risk_factors
   /api/analyze_tx (AI)
   /api/decision (audit)
```

---

## 2. Tech Stack Decisions

| Layer | Choice | Why |
|---|---|---|
| **Backend** | Python + FastAPI | Native async, automatic OpenAPI docs, minimal boilerplate |
| **Data engine** | Pandas (in-memory) | 1,000 rows loads in milliseconds; no DB migration overhead; vectorized cross-card aggregations are instant |
| **ML** | Scikit-learn Random Forest | Best precision/recall tradeoff on imbalanced data; `class_weight='balanced'` handles the 7% fraud base rate without SMOTE |
| **Network analysis** | NetworkX | Native Python graph library; connected-component extraction is trivially fast at this scale |
| **Frontend** | Vanilla HTML/CSS/JS | Zero build step; judges can verify the UI source directly; no framework black boxes |
| **Charts** | Chart.js | Lightweight, no bundler required |
| **Entity map** | Vis.js | Best-in-class for interactive node-edge graphs in pure browser |
| **Geo map** | Leaflet.js + CartoDB dark tiles | Dark tile layer matches the dashboard aesthetic; OpenStreetMap-compatible; offline-safe |
| **AI narrative** | External LLM API | Streaming text generation for the "Ask AI" button; output prefixed as `[Sentinel AI Analysis]` |

**Explicitly avoided:**
- React / Next.js — adds build complexity with no benefit at this scale
- PostgreSQL / SQLite — zero benefit for a 1,000-row in-memory workload; adds setup friction for judges
- Docker — adds setup complexity; `pip install . && uvicorn main:app` is simpler and more reproducible

---

## 3. Analysis Pipeline (analyze_clean.ipynb → data_prep.py)

The notebook (`analyze_clean.ipynb`) documents the full 13-section research process:

| Section | What Happened |
|---|---|
| **Section 1-3** | Manual discovery steps, pattern consolidation, and dataset overview |
| **Section 4** | Formal preprocessing pipeline (cleaning, feature engineering, normalization) |
| **Section 5** | Deterministic rule labeling → `labeled_transactions.csv` (70 fraud, 930 legitimate) |
| **Section 6** | Unsupervised anomaly detection (Isolation Forest, LOF, K-Means, DBSCAN) — explored but not used for final scoring due to noise |
| **Section 7** | Supervised ML (Logistic Regression, Decision Tree, Random Forest) — Random Forest selected |
| **Section 8** | Pseudo-labeling experiment: tested if unsupervised flags can replace ground truth labels |
| **Section 9** | Network analysis with NetworkX — entity graph extraction, connected component analysis |
| **Section 10 & 11** | Evaluated network analysis + ensemble pseudo-labeling against ground truth |
| **Section 12** | PySpark + XGBoost: production-scale pipeline demonstration |
| **Section 13** | Export `labeled_transactions.csv` |

`data_prep.py` is the production-distilled version of Section 4 → Section 7, producing `app_data.csv` which the web app reads at boot.

---

## 4. How the Web App Works at Runtime

1. **Boot:** `main.py` reads `app_data.csv` into a global Pandas DataFrame. All API queries run as vectorized DataFrame operations — no SQL, no ORM.
2. **Queue fetch:** Frontend calls `/api/transactions?min_probability=<threshold>`. Backend filters the DataFrame, sorts by probability descending, and returns the queue. The threshold is set by the analyst's Risk Tolerance slider.
3. **Case rendering:** Frontend receives the top transaction and simultaneously fires 4 async fetch calls for its enrichment data: card history, fraud ring graph, geo-IP map, and merchant volume.
4. **Decision:** Analyst presses A/D/E or clicks a button. Frontend POSTs to `/api/decision`. Backend:
   - Appends to `audit_log.json` (timestamp, tx_id, decision, escalation reason, analyst notes)
   - If `decision == "Dismiss"`: adds merchant to `dismissed_merchants` set, which lowers that merchant's risk score by 0.20 on subsequent queue fetches (in-session feedback loop)
5. **Next case:** Frontend auto-loads the next transaction from the queue.

---

## 5. What We Decided to Skip and Why

| Skipped | Reason |
|---|---|
| **XGBoost / LightGBM in production** | Random Forest with ground-truth deterministic labels already achieves high F1. Adding gradient boosting would marginally improve scores but add `xgboost` dependency complexity for judges. |
| **Streaming ingestion (Kafka)** | Out of scope for 24 hours. Documented as a "next week" item in README. The architecture is designed to support it (the FastAPI backend could subscribe to a Kafka topic with minimal changes). |
| **User authentication** | The app is assumed to run behind a corporate SSO/VPN layer in production. Out of scope for the hackathon. |
| **Per-decision probability re-training** | In-session feedback loop updates scores by a fixed delta (−0.20 per dismissed merchant). Full model retraining from analyst feedback would require collecting enough labeled decisions to avoid catastrophic forgetting — a multi-week engineering effort. |
| **SMOTE / oversampling** | Handled by `class_weight='balanced'` in the Random Forest, which is equivalent and avoids synthetic data artifacts. |

---

## 6. Repository Structure

```
valsoft_mpchacks/
├── analyze_clean.ipynb    # Full research notebook (13 sections of analysis)
├── data_prep.py           # Production preprocessing + model training script
├── main.py                # FastAPI backend (9 REST endpoints)
├── app_data.csv           # Pre-scored dataset (loaded by web app at boot)
├── labeled_transactions.csv  # Ground truth labels (output of Phase 2.75)
├── transactions.csv       # Original raw dataset
├── audit_log.json         # Persistent audit trail (grows as analysts make decisions)
├── static/
│   ├── index.html         # Dashboard UI
│   ├── style.css          # CSS design system (dark theme, CSS Grid layout)
│   └── app.js             # Frontend logic (queue, charts, keyboard shortcuts)
├── test_detector.py       # Tests: detection correctness + API endpoints
├── test_feedback.py       # Tests: in-session feedback loop correctness
├── pyproject.toml         # Dependencies (runtime + dev)
├── README.md              # Setup, keyboard shortcuts, fraud patterns, strategy
├── PRD.md                 # Product requirements document
├── Implementation_Plan.md # This file
└── Hypothesis_Log.md      # Every detection rule tried, with outcomes
```
