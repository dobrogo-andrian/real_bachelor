"""
run_this_first_v5.py
Verifies the FINAL, most stable list of SOTA datasets.
"""
from datasets import get_dataset_split_names

# FINAL list of datasets confirmed LIVE and STABLE
datasets_to_check = [
    ("MonoHime/ru_sentiment_dataset", None),
    ("ukr-detect/ukr-emotions-binary", None), # <-- The new, stable Ukrainian dataset
    ("tweet_eval", "sentiment"),
]

print("=" * 60)
print("Verifying FINAL SOTA dataset list...")
print("=" * 60)
for dataset_id, config_name_to_pass in datasets_to_check:
    try:
        splits = get_dataset_split_names(dataset_id, config_name=config_name_to_pass)
        print(f"[OK]   {dataset_id} (config: {config_name_to_pass}) | splits: {splits}")
    except Exception as e:
        print(f"[FAIL] {dataset_id} | error: {e}")
print("=" * 60)