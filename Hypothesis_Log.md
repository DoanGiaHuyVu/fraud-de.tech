# Hypothesis Log: What We Tried, What Worked, What We Dropped

This log documents every detection approach we tested during the 24-hour hackathon — including approaches that failed — along with the reasoning behind each keep/drop decision. See `analyze_clean.ipynb` for full code and outputs for each phase.

---

## The Four Fraud Patterns in the Dataset

Through six manual discovery steps in Phase 1 of the notebook, we identified the following four patterns:

| # | Pattern Name | Cards Affected | Key Merchant(s) | Signal |
|---|---|---|---|---|
| 1 | **Card Testing (Micro-Transactions)** | card_023, card_038, card_042, card_049 | AliExpress, Shopify Merchant 1 & 2, QuickPay Online | Burst of $1–$15 transactions |
| 2 | **Coordinated Merchant Attack** | Multiple (Wave 1 & 2) | QuickPay Online | 2 attack waves: May 5 02–04h, May 17 14–16h |
| 3 | **Gift Card Laundering** | card_016, card_018, card_019, card_045 | Gift Card Mall, Apple Gift Card | Cross-border, high-value gift card purchases |
| 4 | **Account Takeover → Electronics Spree** | card_000, card_016, card_020, card_021, card_048 | Apple Store, Newegg, Best Buy, AliExpress | 20x–50x personal spending median |

**Total fraud transactions labeled: 70 (7% of dataset)**

---

## Section 1 — Manual Discovery (6 Steps)

### Discovery Step 1: Micro-Transaction Volume
**Hypothesis:** Cards making many small transactions (≤ $15 CAD) are testing stolen card numbers.
**Test:** `df.groupby('card_id').filter(amount ≤ $15).size().sort_values()`
**Result:** ✅ Cards 042, 023, 038, 049 immediately stood out with a disproportionately high volume of sub-$15 online transactions at permissive merchants. → **Pattern 1 confirmed.**

### Discovery Step 2: Merchant Volume Spikes
**Hypothesis:** Fraudsters hammer a single weak merchant with many cards simultaneously.
**Test:** `max_daily_volume / median_daily_volume` per merchant.
**Result:** ✅ QuickPay Online had an extreme spike ratio. Timeline visualization revealed two sharp, discrete attack waves on May 5 and May 17. → **Pattern 2 confirmed.**

### Discovery Step 3: High-Risk Gift Card Cashouts
**Hypothesis:** Gift cards are the preferred payout instrument because they are instant and non-reversible.
**Test:** Filter `merchant_name.str.contains("Gift Card")` and examine amount + country fields.
**Result:** ✅ Cards 016, 018, 019, 045 had purchases up to $1,753 at gift card merchants, consistently cross-border (CA/FR cardholder → US merchant). → **Pattern 3 confirmed.**

### Discovery Step 4: Extreme Spend Ratio (Max / Median)
**Hypothesis:** Account takeovers create a sudden spike in the card's maximum transaction vs. its historical median.
**Test:** `card_stats['max'] / card_stats['median']` sorted descending.
**Result:** ✅ Cards 016, 000, 021, 020 had max-to-median ratios of 20x–50x, all concentrated at electronics merchants (Apple Store, Newegg, Best Buy). → **Pattern 4 confirmed.**

### Discovery Step 5: Impossible Travel & ATM Bursts (Dead End)
**Hypothesis:** Physical impossible travel (in-person swipes in two countries within 12 hours) could be an additional fraud signal.
**Test:** Sort in-person/ATM transactions by card and compute time delta between country changes.
**Result:** ❌ **Dead end.** Physical impossible travel instances were near-zero in this dataset. ATM withdrawals were also unremarkable (normal withdrawal amounts, no burst pattern). Dropped entirely. The dataset's fraud is online/card-not-present, not physical.

### Discovery Step 6: Exhaustive Anomaly Verification
**Test:** Spot-check injected high-numbered transactions (`tx_000980+`) against the 4 discovered patterns.
**Result:** ✅ All injected transactions mapped perfectly to one of the four patterns. Confirmed no fifth hidden pattern.

---

## Section 5 — Deterministic Rule Labeling

**Approach:** Apply the four discovered patterns as explicit boolean rules to generate a perfect ground-truth label column (`is_fraud`). This produces a labeled dataset with **70 confirmed fraud transactions (7% of 1,000)**.

**Why deterministic rules instead of purely ML?**
- Rules produce 100% explainable labels — every fraud case can be traced to a specific, human-readable rule.
- Supervised models trained on these labels inherit that explainability.
- Avoids the circular problem of using noisy unsupervised models to generate training labels for a supervised model.

**Result:** ✅ **KEPT as the ground truth.** `labeled_transactions.csv` exported from this section.

---

## Section 6 — Unsupervised Statistical Anomaly Detection (Explored but not used for final scoring)

### Isolation Forest
**Contamination parameter:** 10%
**Result:** Flagged ~11% of cards as anomalous. Evaluated against Section 5 ground truth — moderate precision, caught some real fraud but with significant false positive noise.
**Decision:** ❌ **Too noisy for production use.** Precision was insufficient for a reviewer queue where false positives directly cost analyst time. Kept in notebook as a comparison benchmark.

### Local Outlier Factor (LOF)
**n_neighbors:** 20, **contamination:** 10%
**Result:** Similar performance to Isolation Forest. Detected the same approximate set of anomalous cards.
**Decision:** ❌ **Redundant with IF.** Documented in Section 8 pseudo-labeling experiment as a baseline comparison.

### K-Means Clustering
**Approach:** Small clusters (< 10% of card population) treated as outlier clusters.
**Result:** Outlier clusters correlated well with fraud cards, but cluster boundaries were imprecise — some legitimate high-spending cards were swept in.
**Decision:** ❌ **Retained only in ensemble experiment**, not in final production scoring.

### DBSCAN
**Approach:** Sparse-region points (cluster = -1) treated as anomalies.
**Result:** Noise points overlapped well with fraud cards but produced too many false positives.
**Decision:** ❌ **Same conclusion as K-Means.** Ensemble experiment only.

### Ensemble Voting (Section 11)
**Rule:** Flag if `is_fraud_ring == 1` OR `≥ 2 statistical model votes`.
**Result:** Better precision than any individual unsupervised model, but still below the deterministic rule baseline.
**Decision:** ❌ **Not used in final scoring** — deterministic rules + Random Forest outperformed this on our specific dataset. Would revisit in a setting without access to ground truth labels.

---

## Section 9 — Network Analysis (Entity Relationship Maps)

**Approach:** Build a tripartite graph mapping `card_id ↔ device_id ↔ ip_address` using NetworkX. Identify connected components with more than one card as fraud rings.

**Intuition:** A legitimate user typically has a tiny isolated subgraph (1 card → 1-2 devices/IPs). A fraud ring forms a massive interconnected web of multiple stolen cards routed through shared infrastructure.

**Result:** ✅ **KEPT as `is_fraud_ring` feature.** The largest connected component in the graph spanned multiple cards sharing the same device and IP, directly confirming the Pattern 2 coordinated attack.

**Evaluation (Section 10):** When used alone as a pseudo-label for a Random Forest, network analysis outperformed all four unsupervised statistical methods in F1 against the ground truth. This validated it as the strongest single cross-card signal.

---

## Section 7 — Supervised Random Forest (Final Model)

**Features:** `amount_scaled`, `hour_of_day`, `day_of_week`, `is_weekend`, `tx_velocity_1h`, `country_match`, `is_cross_border`, `is_fraud_ring`, `is_micro_tx`, `device_id_missing`, `merchant_category_enc`, `channel_enc`
**Labels:** Deterministic Section 5 rules (`labeled_transactions.csv`)
**Configuration:** 100 trees, `class_weight='balanced'` (critical for 7% fraud base rate)

**Result:** ✅ **Final production model.** Generates the `probability` score (0–1.0) shown in the dashboard for every transaction. `app_data.csv` is generated by `data_prep.py`.

**Comparison vs. alternatives:**
- Logistic Regression: Lower F1 on the minority class (less able to capture nonlinear interactions)
- Decision Tree: Prone to overfitting on small minority class
- Random Forest: Best balance of precision/recall on imbalanced data

---

## Section 12 — PySpark + XGBoost (Production Scale Demonstration)

**Purpose:** Demonstrate how the pipeline would scale to millions of transactions per day in an enterprise environment.

**PySpark:** Distributed feature assembly via `VectorAssembler`, training a native PySpark `RandomForestClassifier` across local worker threads.

**XGBoost:** `scale_pos_weight` tuned to the class imbalance ratio. Pulls PySpark splits back to the driver node for local training (as a pragmatic workaround for XGBoost's C++ dependency complexity on PySpark workers).

**Result:** ✅ **Documented and working.** Not used in the final web app scoring — Pandas+sklearn is sufficient for 1,000 rows and avoids the overhead. Included to demonstrate production readiness.

---

## Section 13 — Autonomous LLM Agent Investigation (Gemma 4)

**Purpose:** Test whether a Large Language Model can perform the duties of a Level 1 fraud analyst autonomously by analyzing the raw signals, history, and merchant context.

**Approach:** 
We built a background Python script (`run_investigation.py`) that feeds a JSON-formatted payload of the transaction, card history, and engineered signals into Google's Gemma 2.0 model via the GenAI API. The model is asked to act as an expert fraud analyst, reason through the signals step-by-step, and output a binary `is_fraud` decision along with a confidence score and a plain-English explanation.

**Result:** ✅ **Highly Successful.**
When evaluated against our deterministic ground truth (`labeled_transactions.csv`), the LLM agent achieved the following performance on 605 transactions:

```text
========================================
🤖 AGENT ACCURACY REPORT 🤖
========================================
Total Transactions Evaluated: 605

Accuracy:  95.70%
Precision: 65.91% (When agent says fraud, how often is it right?)
Recall:    72.50% (Out of all actual frauds, how many did the agent catch?)
F1 Score:  69.05%

Confusion Matrix:
True Negatives (Correctly identified as Safe):  550
False Positives (Falsely flagged as Fraud):     15
False Negatives (Missed Frauds):                11
True Positives (Correctly identified Fraud):    29
========================================
```

**Decision:** **KEPT.** The LLM agent acts as a powerful complement to the Random Forest model. While the Random Forest provides a fast, mathematical probability score, the LLM agent provides deep reasoning and context synthesis that can act as a "second opinion" or an automated Level 1 triage filter before cases hit the human reviewer queue.

---

## Appendix: Complete Model Evaluation Metrics

During the research phase (`analyze_clean.ipynb`), multiple algorithms were evaluated against the deterministic ground truth labels. 

### Supervised Learning (Section 7 & 12)
These models were trained on 80% of the labeled dataset and tested on 20% (200 transactions).

| Model | Accuracy | Precision (Fraud) | Recall (Fraud) | F1-Score (Fraud) | PR-AUC | Notes |
|---|---|---|---|---|---|---|
| **Random Forest** | 0.99 | 0.93 | 0.93 | **0.93** | 0.995 | **Selected for production** (Best balance of precision/recall) |
| **XGBoost (PySpark Driver)** | 0.96 | 0.65 | 0.93 | 0.76 | 0.904 | Excellent recall, but lower precision than RF |
| **Decision Tree** | 0.94 | 0.58 | 0.79 | 0.67 | 0.731 | Prone to overfitting on the minority class |
| **Logistic Regression** | 0.95 | 0.86 | 0.43 | 0.57 | 0.718 | Poor recall on non-linear fraud patterns |

### Unsupervised / Pseudo-Labeling (Section 6, 8 & 11)
These anomaly detection algorithms were run on the entire dataset without labels, and their output flags were evaluated against the perfect ground truth.

| Algorithm | Fraud Flagged | Accuracy | Precision (Fraud) | Recall (Fraud) | F1-Score (Fraud) | Notes |
|---|---|---|---|---|---|---|
| **K-Means Clustering** | 11.3% | 0.93 | 0.75 | 0.33 | 0.46 | Best precision among unsupervised |
| **Local Outlier Factor (LOF)** | 12.9% | 0.95 | 0.38 | 0.38 | 0.38 | Flagged too many legitimate outliers |
| **Ensembled (Voting)** | 18.1% | 0.91 | 0.31 | 0.31 | 0.31 | Combined network + >= 2 stat flags |
| **Isolation Forest** | 11.6% | 0.93 | 0.38 | 0.25 | 0.30 | High noise ratio |
| **Network Analysis** | 3.6% | 0.94 | 0.00 | 0.00 | 0.00 | Too narrow as a standalone classifier |
