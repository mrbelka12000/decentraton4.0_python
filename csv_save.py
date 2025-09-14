import csv

def save_push_notifications(results,filename="result.csv"):
    # --- Write to CSV ---
    with open(filename, mode="w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(["client_code", "product", "push_notification"])
        writer.writerows(results)

    print(f"Saved {len(results)} push notifications to {filename} ✅")