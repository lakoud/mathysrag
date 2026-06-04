import csv
import os

def append_evaluation_to_csv(metrics, csv_path="src/rems/evaluation.csv"):
    file_exists = os.path.isfile(csv_path)

    with open(csv_path, mode="a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=metrics.keys())

        if not file_exists:
            writer.writeheader()

        writer.writerow(metrics)