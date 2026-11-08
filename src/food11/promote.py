import argparse
import math
import os
import sys

import mlflow

MLFLOW_TRACKING_URI = os.environ.get("MLFLOW_TRACKING_URI", "http://127.0.0.1:5000")
TEST_SET_SIZE = 330  # From the mini dataset size (30 per class * 11)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", type=int, required=True, help="Model version to promote")
    args = parser.parse_args()

    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
    client = mlflow.MlflowClient()

    # 1. Get candidate run
    try:
        candidate_mv = client.get_model_version("food11", args.version)
    except Exception as e:
        print(f"Error: Version {args.version} not found. {e}")
        sys.exit(1)

    candidate_run = client.get_run(candidate_mv.run_id)
    acc_candidate = candidate_run.data.metrics.get("test_accuracy", 0.0)

    # 2. Get champion run
    try:
        champion_mv = client.get_model_version_by_alias("food11", "champion")
        champion_run = client.get_run(champion_mv.run_id)
        acc_champion = champion_run.data.metrics.get("test_accuracy", 0.0)
    except Exception:
        print("No champion found. Automatically promoting candidate.")
        acc_champion = -1.0
        champion_mv = None

    # 3. Calculate Standard Error
    se = math.sqrt(acc_champion * (1 - acc_champion) / TEST_SET_SIZE) if acc_champion > 0 else 0

    print(f"Candidate v{args.version} Accuracy: {acc_candidate:.4f}")
    print(f"Champion Accuracy: {acc_champion:.4f}")
    print(f"Standard Error (n={TEST_SET_SIZE}): {se:.4f}")
    print(f"Threshold (Champion + 2*SE): {acc_champion + 2 * se:.4f}")

    # 4. Promotion gate
    if acc_candidate >= acc_champion + 2 * se:
        print(f"✅ Candidate passes gate! Moving 'champion' alias to v{args.version}")
        client.set_registered_model_alias("food11", "champion", args.version)
        decision = "promoted"
    else:
        print(f"❌ Candidate fails gate. Setting 'challenger' alias on v{args.version}")
        client.set_registered_model_alias("food11", "challenger", args.version)
        decision = "rejected"

    # 5. Log tags
    client.set_model_version_tag("food11", args.version, "promotion_decision", decision)
    client.set_model_version_tag("food11", args.version, "candidate_accuracy", str(acc_candidate))
    client.set_model_version_tag("food11", args.version, "champion_accuracy", str(acc_champion))

if __name__ == "__main__":
    main()