import csv
def load_csv(path):
    with open(path, newline='', encoding='utf-8') as f:
        return list(csv.DictReader(f))

profiles = {r['user_id']: r for r in load_csv('dataset/financial_profiles.csv')}

sample_users = ['user_01','user_02','user_03','user_04','user_05','user_06','user_07','user_08','user_09','user_10',
                'user_11','user_12','user_13','user_14','user_15','user_16','user_17','user_18','user_19','user_20',
                'user_21','user_22','user_23','user_24','user_25']

print('=== PROFILE FIELDS for sample users ===')
print(f"{'user':<10} {'cur':<5} {'balance':<15} {'min_bal':<15} {'pref_methods':<50}")
for uid in sample_users:
    p = profiles.get(uid, {})
    cur = p.get('home_currency','?')
    bal = p.get('current_balance','?')
    minb = p.get('minimum_balance_to_keep','?')
    pref = p.get('payment_methods_user_will_consider','?')
    print(f"{uid:<10} {cur:<5} {bal:<15} {minb:<15} {pref:<50}")
