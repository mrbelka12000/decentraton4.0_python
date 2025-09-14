# Курсы валют
CURRENCY_RATES = {
    "KZT": 1,
    "USD": 500,
    "EUR": 600
}

def convert_to_kzt(amount: float, currency: str) -> float:
    """Конвертация суммы в KZT"""
    rate = CURRENCY_RATES.get(currency, 1)  # если валюта неизвестна → оставить как есть
    return amount * rate

def calculate_travel_card_benefit(client) -> float:
    travel_categories = ["Путешествия", "Такси", "Отели"]
    travel_spending = sum(
        convert_to_kzt(tx.amount, tx.currency)
        for tx in client.transactions if tx.category in travel_categories
    )
    monthly_cashback = (travel_spending * 0.04) / 3
    return monthly_cashback

def calculate_premium_card_benefit(client) -> float:
    premium_categories = ["Кафе и рестораны", "Ювелирные украшения", "Косметика и Парфюмерия"]
    premium_spending = sum(
        convert_to_kzt(tx.amount, tx.currency)
        for tx in client.transactions if tx.category in premium_categories
    )
    premium_bonus = (premium_spending * 0.02) / 3
    return premium_bonus

def calculate_credit_card_benefit(client) -> float:
    online_categories = ["Играем дома", "Смотрим дома", "Едим дома"]
    online_spending = sum(
        convert_to_kzt(tx.amount, tx.currency)
        for tx in client.transactions if tx.category in online_categories
    )
    online_cashback = online_spending * 0.05
    monthly_benefit = online_cashback / 3
    return monthly_benefit


def calculate_profit_for_client_by_product(client, product_type: str) -> float:
    if product_type == 'Карта для путешествий':
        return calculate_travel_card_benefit(client)
    elif product_type == 'Премиальная карта':
        return calculate_premium_card_benefit(client)
    elif product_type == 'Кредитная карта':
        return calculate_credit_card_benefit(client)
    
    return 0.0
