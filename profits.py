def calculate_travel_card_benefit(client) -> float:
    travel_categories = ["Путешествия", "Такси", "Отели"]
    travel_spending = sum(tx.amount for tx in client.transactions if tx.category in travel_categories)
    monthly_cashback = (travel_spending * 0.04) / 3
    return monthly_cashback

def calculate_premium_card_benefit(client) -> float:
    balance = client.avg_monthly_balance_KZT

    if balance >= 6000000:
        base_rate = 0.04
    elif balance >= 1000000:
        base_rate = 0.03
    else:
        base_rate = 0.02

    total_spending = sum(tx.amount for tx in client.transactions)
    monthly_spending = total_spending / 3
    base_cashback = monthly_spending * base_rate

    premium_categories = ["Кафе и рестораны", "Ювелирные украшения", "Косметика и Парфюмерия"]
    premium_spending = sum(tx.amount for tx in client.transactions if tx.category in premium_categories)
    premium_bonus = (premium_spending * 0.02) / 3

    total_withdrawals = sum(tr.amount for tr in client.transfers if tr.direction == "out")
    withdrawal_savings = (total_withdrawals * 0.01) / 3

    return base_cashback + premium_bonus + withdrawal_savings

def calculate_credit_card_benefit(client) -> float:
    credit_categories = ["Одежда и обувь", "Продукты питания", "Кафе и рестораны",
                        "Медицина", "Авто", "Спорт", "Развлечения", "Кино",
                        "Косметика и Парфюмерия", "Подарки", "Ремонт дома", "Мебель"]

    top3_cashback = 0
    for cat_info in client.top4_categories[:3]:
        if cat_info["category"] in credit_categories:
            top3_cashback += cat_info["amount"] * 0.10

    online_categories = ["Играем дома", "Смотрим дома", "Едим дома"]
    online_spending = sum(tx.amount for tx in client.transactions if tx.category in online_categories)
    online_cashback = online_spending * 0.10


    monthly_benefit = (top3_cashback + online_cashback) / 3
    return monthly_benefit
