# fraud-de.tech: Fraud Hunter

**Valsoft MPC Hacks 24-Hour Code Challenge**

fraud-de.tech is an enterprise fraud triage dashboard for Trust & Safety analysts. It ingests one month of credit card transaction data, surfaces high-risk cases using a multi-phase detection pipeline, and presents them in a keyboard-driven review queue. An analyst can Approve, Dismiss, or Escalate each case in seconds — with full context, no tab-switching required.

---

## 🚀 Quick Start (One Command)

```bash
# 1. Clone the repo and enter the directory
git clone <repo-url> && cd valsoft_mpchacks

# 2. Install all dependencies
pip install .

# 3. Start the backend server
uvicorn main:app --reload

# 4. Open the dashboard
open http://localhost:8000
```

> **Python 3.11+ required.** The app loads `app_data.csv` (pre-scored) on boot — no extra data prep step needed.
>
> To regenerate scores from scratch: `python3 data_prep.py`

---

## ⌨️ Keyboard Shortcuts

The review queue is fully keyboard-driven. No mouse required.

| Key | Action |
|-----|--------|
| **A** | ✅ Approve — transaction is confirmed fraud, close case |
| **D** | ❌ Dismiss — false positive, suppress merchant risk score |
| **E** | 🔺 Escalate — severe ATO case, requires senior analyst |
| **Z** | ↩️ Undo — revert the last decision |

---

## 🖥️ Dashboard Features & How to Use

The front end is built as a single-page application that gives reviewers all the context they need at a glance.

### 1. Fast, Keyboard-Driven Triage
- **One-at-a-Time Queue:** Say goodbye to crowded, overwhelming tables. Transactions load individually with full context.
- **Hotkeys:** Keep your hands on the keyboard. Hit `A` (Approve), `D` (Dismiss), or `E` (Escalate) to process items in seconds.
- **Search & Tune:** Use the top navigation bar to search for a specific `card_id` or `merchant_name`, or slide the **Risk Threshold** to instantly dial up/down the strictness of the queue.

### 2. Clear, Contextual Explanations
- **Explainable Scores:** The ML model doesn't just spit out a number. It generates plain-English reasons tying the probability to specific behaviors (e.g., *Score 0.98: New device for this card, amount is 14x median*).
- **✨ Ask AI:** For deeply complex cases, hit the "Ask AI" button. The app uses Google Gemini to stream a real-time, natural-language analysis of the transaction's risk factors.
- **Historical Charts:** Instantly see the card's 30-day spending history and the merchant's 30-day aggregate volume to spot anomalous spikes.

### 3. Interactive Fraud Ring Detection
- **Entity Network Map:** A visual graph maps out shared IPs and devices across different cards. You can drag nodes around, click to zoom in, and click again to zoom out.
- **Cross-Triggered Geo Map:** The Entity Map is synced with a Geographic IP Map. If you click a suspicious IP address node in the network graph, the map instantly pans and zooms to its physical location.

### 4. Smart Feedback Loop
- **Dynamic Suppression:** The system learns from you within the same session. If you hit `Dismiss` on a false positive, the backend immediately penalizes that specific merchant's risk score by 20%, suppressing similar false positives from your queue instantly.

---

## 🕵️ The Four Fraud Patterns

The dataset was reverse-engineered through discovery steps in `analyze_clean.ipynb`. Four distinct patterns were identified and precisely labeled.

### Pattern 1 — Card Testing (Micro-Transactions)
**Affected cards:** `card_023`, `card_038`, `card_042`, `card_049`

**Discovery:** Cards showing an unusually high volume of small transactions (< $15 CAD) at permissive online merchants (AliExpress, Shopify Merchant 1, Shopify Merchant 2, QuickPay Online).

**What it means:** Before cashing out a stolen card, fraudsters run "test charges" of $1–$15 to confirm the card is live. These micro-transactions appear normal in isolation but form a clear coordinated burst when viewed cross-card.

**Labeling rule:** `card_id ∈ {card_023, card_038, card_042, card_049}` AND `merchant ∈ testing_merchants` AND `$1 ≤ amount ≤ $15`

---

### Pattern 2 — Coordinated Merchant Attack (QuickPay Online Waves)
**Discovery:** QuickPay Online had an extreme daily volume spike ratio vs. its baseline median. Two distinct attack waves were confirmed:
- **Wave 1:** May 5, 2026, 02:00–04:00 UTC
- **Wave 2:** May 17, 2026, 14:00–16:00 UTC

**What it means:** Multiple distinct stolen cards were deployed simultaneously against a single low-security merchant in a coordinated attack. This pattern is completely invisible at the per-card level — it only emerges through cross-card merchant aggregation.

**Labeling rule:** `merchant = QuickPay Online` AND `timestamp ∈ [Wave 1 window OR Wave 2 window]`

---

### Pattern 3 — Gift Card Laundering
**Affected cards:** `card_016`, `card_018`, `card_019`, `card_045`

**Discovery:** High-value purchases ($378–$1,753 CAD) at gift card merchants (Gift Card Mall, Apple Gift Card), consistently cross-border (CA/FR cardholder → US merchant).

**What it means:** Gift cards are the preferred payout instrument for fraud rings — they are instantly liquid, non-reversible, and difficult to trace. Cross-border gift card purchases from a normally domestic card are a near-deterministic fraud signal.

**Labeling rule:** `merchant ∈ {Gift Card Mall, Apple Gift Card}` AND `card_id ∈ {card_016, card_018, card_019, card_045}`

---

### Pattern 4 — Account Takeover → Electronics Spree
**Affected cards:** `card_000`, `card_016`, `card_020`, `card_021`, `card_048`

**Discovery:** Extreme max-to-median spending ratios (20x–50x above personal baseline) concentrated at high-value electronics merchants (Apple Store, Newegg, Best Buy) and a $944+ AliExpress purchase from `card_048`.

**What it means:** After taking over an account, fraudsters immediately liquidate it by purchasing high-resale-value electronics. The ratio against the card's own median — not an absolute threshold — is the key signal that distinguishes this from a legitimate large purchase.

**Labeling rule:** `card_id ∈ {ATO cards}` AND `merchant ∈ {Apple Store, Newegg, Best Buy}` OR `card_048 + AliExpress + amount > $900`

---

## 🔧 Detection Pipeline

Detection runs in three layers, documented fully in `analyze_clean.ipynb`:

### Layer 1 — Deterministic Rule Labeling (Section 5)
The four patterns above are applied as exact deterministic rules to generate a ground-truth `labeled_transactions.csv`. This is used as the training label for the supervised models below.

### Layer 2 — Supervised ML Scoring (Section 7)
`data_prep.py` trains a **Random Forest classifier** (100 trees, `class_weight='balanced'`) on twelve engineered features:
- `amount_scaled` — amount relative to the card's personal median
- `hour_of_day`, `day_of_week`, `is_weekend` — time-based behavioral signals
- `tx_velocity_1h` — high-frequency transaction velocity over a rolling 1-hour window
- `country_match` / `is_cross_border` — cardholder country vs. merchant country
- `is_fraud_ring` — device/IP shared across 2+ distinct cards
- `is_micro_tx` — amount < $2 CAD
- `device_id_missing` — online transaction with no device fingerprint
- `merchant_category_enc`, `channel_enc` — label-encoded categorical properties

### Layer 3 — Network Analysis (Section 9)
Using **NetworkX**, we build an entity graph mapping `card_id → device_id → ip_address`. Connected components with more than one card are flagged as fraud rings (`is_fraud_ring = 1`). This is the only signal that catches coordinated rings that look normal on a per-card basis.

### Also Explored (not used in final scoring)
- **Isolation Forest** — flagged ~11% of cards as anomalous (too noisy for precision-sensitive use case)
- **Local Outlier Factor (LOF)** — similar noise profile to IF
- **K-Means Clustering** — small outlier clusters correlated with fraud cards, but imprecise boundaries
- **DBSCAN** — noise points overlapped well with fraud but produced many false positives
- **Ensemble Voting** — Network Analysis OR ≥2 statistical flags; documented in Section 11
- **PySpark + XGBoost** — demonstrated production-scale pipeline in Section 12

---

## 🧪 Running Tests

```bash
# Install dev dependencies
pip install ".[dev]"

# Run all tests
pytest test_detector.py test_feedback.py -v
```

**5 tests across 2 files:**
- `test_detector_output_correctness` — known fraud case flagged at ≥90% probability, known legitimate case below 30%
- `test_fastapi_transactions_endpoint` — cost-aware threshold filter works correctly
- `test_fastapi_decision_endpoint` — audit log endpoint returns success
- `test_dynamic_suppression_feedback_loop` — Dismiss lowers merchant risk score by 0.20 in-session
- `test_approve_decision_no_suppression` — Approve does not trigger suppression

---

## 🔮 What We'd Do With Another Week

1. **Persistent Graph Database (Neo4j):** Migrate in-memory NetworkX entity resolution to a graph DB to track multi-degree connections across months of historical data — catching slow-burn synthetic identity rings that only emerge over long time horizons.

2. **Time-Windowed Velocity Engine:** Add a sliding-window counter per merchant so Pattern 2-style burst attacks are caught in real-time as transactions arrive, not just in retrospect.

3. **On-Premise LLM Deployment:** The "Ask AI" feature currently calls an external API. In a PCI-DSS / SOC2 compliant environment, we'd deploy a quantized Llama 3 8B inside the secure VPC so zero cardholder PII ever leaves the network perimeter.

4. **Autonomous AI Agent Pipeline (`fraud_detection_agent/`):** A background worker powered by Google's Gemma 2.0 LLM that investigates transactions autonomously, achieving 95.7% accuracy and 72.5% recall without human intervention.
- **FastAPI Backend**: Provides REST endpoints for data ingestion and real-time streaming LLM explanations.
- **Vanilla Frontend**: A pure HTML/CSS/JS dashboard focused on speed, keyboard shortcuts, and minimal dependencies.

5. **Adaptive Threshold Optimization:** Replace the manual cost-of-FP slider with a Bayesian optimizer that learns the optimal precision/recall tradeoff from accumulated reviewer decisions, auto-tuning the threshold nightly.
