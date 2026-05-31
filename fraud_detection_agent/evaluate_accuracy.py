import pandas as pd
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, confusion_matrix

def evaluate_results():
    print("Loading data...")
    # Load the agent's predictions
    results_df = pd.read_csv("current_results.csv")
    
    # Load the ground truth data
    # Assuming app_data.csv is in the parent directory based on previous interactions
    try:
        truth_df = pd.read_csv("../app_data.csv")
    except FileNotFoundError:
        print("Could not find ../app_data.csv")
        return

    # Merge the dataframes on transaction_id
    print("Merging predictions with ground truth...")
    merged_df = pd.merge(results_df, truth_df[['transaction_id', 'is_fraud']], 
                         on='transaction_id', 
                         suffixes=('_pred', '_true'))
    
    # Drop rows where prediction might be missing (if any)
    merged_df = merged_df.dropna(subset=['is_fraud_pred', 'is_fraud_true'])
    
    # Ensure boolean types
    y_pred = merged_df['is_fraud_pred'].astype(bool)
    y_true = merged_df['is_fraud_true'].astype(bool)
    
    # Calculate metrics
    accuracy = accuracy_score(y_true, y_pred)
    precision = precision_score(y_true, y_pred, zero_division=0)
    recall = recall_score(y_true, y_pred, zero_division=0)
    f1 = f1_score(y_true, y_pred, zero_division=0)
    cm = confusion_matrix(y_true, y_pred)
    
    print("\n" + "="*40)
    print("🤖 AGENT ACCURACY REPORT 🤖")
    print("="*40)
    print(f"Total Transactions Evaluated: {len(merged_df)}")
    print(f"Accuracy:  {accuracy:.2%}")
    print(f"Precision: {precision:.2%} (When agent says fraud, how often is it right?)")
    print(f"Recall:    {recall:.2%} (Out of all actual frauds, how many did the agent catch?)")
    print(f"F1 Score:  {f1:.2%}")
    print("\nConfusion Matrix:")
    print(f"True Negatives (Correctly identified as Safe):  {cm[0][0]}")
    print(f"False Positives (Falsely flagged as Fraud):     {cm[0][1]}")
    print(f"False Negatives (Missed Frauds):                {cm[1][0]}")
    print(f"True Positives (Correctly identified Fraud):    {cm[1][1]}")
    print("="*40 + "\n")

if __name__ == "__main__":
    evaluate_results()
