import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report
from sklearn.preprocessing import LabelEncoder

print("Loading labeled_transactions.csv...")
df = pd.read_csv('labeled_transactions.csv')

# 1. Feature Engineering (matching the notebook's Section 4 / ml_df_encoded)
df['timestamp'] = pd.to_datetime(df['timestamp'])

# --- Time-based features ---
df['hour_of_day'] = df['timestamp'].dt.hour
df['day_of_week'] = df['timestamp'].dt.dayofweek
df['is_weekend'] = (df['day_of_week'] >= 5).astype(int)
# --- Transaction velocity: # of transactions from this card in the past hour ---
# Requires timestamp as the index for the offset-based rolling window
df_sorted = df.sort_values(['card_id', 'timestamp'])
df_sorted = df_sorted.set_index('timestamp')
df['tx_velocity_1h'] = (
        df_sorted.groupby('card_id')['amount']
        .rolling('1h', closed='both')
        .count()
        .values - 1  # subtract 1 to exclude the transaction itself
)
df['tx_velocity_1h'] = df['tx_velocity_1h'].fillna(0).astype(int)
# --- Per-card amount baseline ---
card_medians = df.groupby('card_id')['amount'].median()
df['amount_scaled'] = df.apply(
    lambda row: row['amount'] / card_medians[row['card_id']] if card_medians[row['card_id']] > 0 else 1.0, axis=1)

# --- Country signals ---
df['country_match'] = (df['cardholder_country'] == df['merchant_country']).astype(int)
df['is_cross_border'] = 1 - df['country_match']
# --- Network / device signals ---
ip_card_count = df.groupby('ip_address')['card_id'].nunique()
device_card_count = df.groupby('device_id')['card_id'].nunique()
df['is_fraud_ring'] = df.apply(
    lambda x: 1 if (pd.notna(x['ip_address']) and ip_card_count.get(x['ip_address'], 0) > 1) or
                   (pd.notna(x['device_id']) and device_card_count.get(x['device_id'], 0) > 1) else 0,
    axis=1
)
df['is_micro_tx'] = (df['amount'] < 2.0).astype(int)
df['device_id_missing'] = df['device_id'].isna().astype(int)
# --- Label-encode categoricals (same columns encoded in the notebook) ---
le = LabelEncoder()
df['merchant_category_enc'] = le.fit_transform(df['merchant_category'].astype(str))
le2 = LabelEncoder()
df['channel_enc'] = le2.fit_transform(df['channel'].astype(str))
features = [
    'amount_scaled',
    'hour_of_day', 'day_of_week', 'is_weekend',
    'tx_velocity_1h',
    'country_match', 'is_cross_border',
    'is_fraud_ring', 'is_micro_tx', 'device_id_missing',
    'merchant_category_enc', 'channel_enc',
]
X = df[features].fillna(0)
y = df['is_fraud']
# 2. Train Model & Score
print("Training Random Forest to generate probability scores...")
# 2. Train / Evaluate / Score
print("Training Random Forest...")
# 2a. Hold out 20% for honest evaluation (stratified to preserve 7% fraud ratio)
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42, stratify=y
)
rf_eval = RandomForestClassifier(n_estimators=100, random_state=42, class_weight='balanced')
rf_eval.fit(X_train, y_train)
y_pred = rf_eval.predict(X_test)
print("\n=== Held-out Test Set Performance (80/20 stratified split) ===")
print(classification_report(y_test, y_pred, target_names=['Legitimate', 'Fraud'], zero_division=0))
# 2b. Re-train on the full dataset so every row gets a probability for the dashboard
#     This is intentional: we validate first (2a), then score everything (2b).
rf = RandomForestClassifier(n_estimators=100, random_state=42, class_weight='balanced')
rf.fit(X, y)
df['probability'] = rf.predict_proba(X)[:, 1]
# 3. Generate Human-Readable Explanations
# Pre-compute per-card typical devices and categories for "new device" and "atypical category" signals
card_typical_devices = df[df['is_fraud'] == 0].groupby('card_id')['device_id'].apply(
    lambda x: set(x.dropna())).to_dict()
card_typical_categories = df[df['is_fraud'] == 0].groupby('card_id')['merchant_category'].apply(
    lambda x: set(x.dropna())).to_dict()


def generate_explanation(row):
    reasons = []
    if row['is_fraud_ring'] == 1:
        reasons.append("Network Analysis Flag: Device/IP reused across multiple distinct cards")
    if row['amount_scaled'] > 5:
        reasons.append(f"Amount is {round(row['amount_scaled'], 1)}x the cardholder's typical median")
    if row['is_cross_border'] == 1:
        reasons.append("Cardholder country does not match merchant country")
    if row['is_micro_tx'] == 1:
        reasons.append("Micro-transaction detected (possible card testing)")
    if row['device_id_missing'] == 1 and row['channel'] == 'online':
        reasons.append("Online transaction missing device signature")

    if row['device_id_missing'] == 1 and row['channel'] == 'online':
        reasons.append("Online transaction missing device signature")
    # New device for this card
    if pd.notna(row.get('device_id')):
        typical = card_typical_devices.get(row['card_id'], set())
        if typical and row['device_id'] not in typical:
            reasons.append(f"New device for this card ({row['device_id']})")
    # Atypical merchant category for this card
    typical_cats = card_typical_categories.get(row['card_id'], set())
    if typical_cats and row['merchant_category'] not in typical_cats:
        reasons.append(f"Atypical category for this card ({row['merchant_category']})")
    if not reasons:
        reasons.append("General anomalous behavior detected by model")
    return ", ".join(reasons)


print("Generating explanations...")
df['explanation'] = df.apply(generate_explanation, axis=1)
# Prepend the score to the explanation so it reads like: "Score 0.93: amount 14x median, new device, ..."
df['explanation'] = df.apply(
    lambda row: f"Score {row['probability']:.2f}: {row['explanation']}", axis=1
)
# Export for the Web App
df.to_csv('app_data.csv', index=False)
print("Success! Saved app_data.csv")
