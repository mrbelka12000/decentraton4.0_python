def get_transfer_types(client) -> list:
    """Получаем типы переводов клиента"""
    return [tr.type for tr in client.transfers]

def classify_client_perfect(client) -> str:
    """
    ИДЕАЛЬНАЯ классификация на основе ПОЛНОГО анализа всех 10 продуктов + доп. категории
    """
    
    # Базовые параметры
    top_categories = [cat["category"] for cat in client.top4_categories[:3]]
    all_categories = [cat["category"] for cat in client.top4_categories]  # ВСЕ топ-4 категории
    balance = client.avg_monthly_balance_KZT
    age = client.age
    status = client.status
    transfer_types = get_transfer_types(client)
    
    # 🔍 1. СНАЧАЛА - АБСОЛЮТНЫЕ СИГНАЛЫ
    if "fx_buy" in transfer_types:
        return "Обмен валют"
    if "invest_out" in transfer_types:
        return "Инвестиции"
    if "deposit_topup_out" in transfer_types:
        return "Депозит Накопительный"
    if "gold_buy_out" in transfer_types or "gold_sell_in" in transfer_types:
        return "Золотые слитки"
    if "cc_repayment_out" in transfer_types:
        return "Кредитная карта"
    if "Косметика и Парфюмерия" in all_categories:
        return "Премиальная карта"

    # 💎 2. НОВЫЕ ПРАВИЛА НА ОСНОВЕ ГЛУБОКОГО АНАЛИЗА ДАННЫХ

    # Продукт: Депозит Мультивалютный (KZT/USD/RUB/EUR)
    # ●  Ставка: 14,50%.
    # ●  Доступ: пополнение и снятие без ограничений.
    # ●  Кому подходит: хранить/ребалансировать валюты с доступом к деньгам.
    if "fx_buy" in transfer_types and balance > 500000: # Strong signal for currency management
        return "Депозит Мультивалютный"
    
    # Продукт: Депозит Сберегательный (защита KDIF)
    # ●  Ставка: 16,50%.
    # ●  Доступ: пополнение — нет, снятие — нет (до конца срока).
    # ●  Кому подходит: максимальный доход при готовности «заморозить» средства.
    if balance > 1000000 and age >= 50: # Higher balance and age for "frozen" funds
        return "Депозит Сберегательный"

    # Правило для крупных депозитов (Сберегательный vs Мультивалютный) - как запасной вариант
    if balance > 700000:
        if age >= 45:
            return "Депозит Сберегательный"
        else:
            return "Депозит Мультивалютный"

    # --- ФИНАЛЬНЫЙ ПАТТЕРН: Анализ кредитной нагрузки + Стиль жизни ---
    loan_payment_amount = client.totals_by_transfer.get('loan_payment_out_out', 0.0)
    total_spending = client.total_transactions
    loan_ratio = (loan_payment_amount / total_spending) * 100 if total_spending > 0 else 0

    # Если кредитная нагрузка высокая (>25%), это клиент кредитного продукта
    if loan_ratio > 25:
        # Считаем "домашние" категории, чтобы определить стиль жизни
        at_home_categories = ["Едим дома", "Смотрим дома", "Играем дома"]
        at_home_count = sum(1 for cat in all_categories if cat in at_home_categories)
        
        # Если у клиента 2+ "домашние" категории, это Кредитная карта для повседневной жизни
        if at_home_count >= 2:
            return "Кредитная карта"
        else:
            # Иначе, это более крупный Кредит наличными
            return "Кредит наличными"
    
    # Правило для Карты для путешествий: такси+отели+путешествия занимают большую часть трат
    travel_categories = ["Путешествия", "Отели", "Такси"]
    travel_spending = sum(client.totals_by_category.get(cat, 0) for cat in travel_categories)
    total_spending = client.total_transactions
    travel_percentage = (travel_spending / total_spending) * 100 if total_spending > 0 else 0

    if travel_percentage > 30: # If travel-related spending is a significant portion (e.g., > 30%)
        return "Карта для путешествий"

    # Existing rules as fallback or additional signals
    has_strong_travel_signal = any(cat in all_categories for cat in ["Путешествия", "Отели"])
    has_foreign_currency = any(t.currency != 'KZT' for t in client.transactions)
    is_affluent_proxy = (balance > 1300000 and status == "Премиальный клиент")
    if has_strong_travel_signal or has_foreign_currency or is_affluent_proxy:
        return "Карта для путешествий"
    
    # fallback для очень низких балансов
    if balance <= 90000 and age <= 38:
        return "Депозит Накопительный"
    
    # Финальный fallback
    return "Кредитная карта"

def calculate_pattern_score(client, product: str) -> float:
    """
    Рассчитывает скор соответствия клиента продукту на основе паттернов + новые категории
    """
    
    top_categories = [cat["category"] for cat in client.top4_categories[:3]]
    all_categories = [cat["category"] for cat in client.top4_categories]
    balance = client.avg_monthly_balance_KZT
    age = client.age
    status = client.status
    score = 0.0
    
    if product == "Премиальная карта":
        if "Косметика и Парфюмерия" in all_categories:
            score += 100  # 100% сигнал - увеличили вес!
        if balance > 2000000:
            score += 30
        if age > 40:
            score += 20

    elif product == "Карта для путешествий":
        # Усиленные паттерны на основе анализа
        travel_indicators = ["Отели", "Путешествия", "Развлечения"]
        travel_score = sum(50 for cat in travel_indicators if cat in all_categories)  # Повышенный вес!
        score += travel_score
        
        if "Такси" in all_categories:
            score += 40
        if 200000 < balance < 1000000:
            score += 20

        # New rule: score based on travel spending percentage
        travel_categories = ["Путешествия", "Отели", "Такси"]
        travel_spending = sum(client.totals_by_category.get(cat, 0) for cat in travel_categories)
        total_spending = client.total_transactions
        travel_percentage = (travel_spending / total_spending) * 100 if total_spending > 0 else 0

        if travel_percentage > 40: # High percentage of travel spending
            score += 80 # Very strong signal
        elif travel_percentage > 20:
            score += 40
            
    elif product == "Кредитная карта":
        # Домашние категории - сильный сигнал
        online_cats = ["Едим дома", "Смотрим дома", "Играем дома"]
        online_score = sum(40 for cat in online_cats if cat in all_categories)  # Увеличили вес!
        score += online_score
        if age < 30:
            score += 20
        if balance < 200000:
            score += 15
            
    elif product == "Инвестиции":
        if balance > 2000000:
            score += 40
        if age < 40:
            score += 30
        if status == "Премиальный клиент":
            score += 30
            
    elif product == "Золотые слитки":
        if balance > 1500000:
            score += 35
        if age >= 45:
            score += 35
        if status == "Премиальный клиент":
            score += 30
            
    elif product == "Депозит Сберегательный":
        # Кому подходит: максимальный доход при готовности «заморозить» средства.
        if age >= 39 and balance >= 800000:
            score += 50
        if "Кафе и рестораны" in all_categories and "Продукты питания" in all_categories:
            score += 40
        if status == "Премиальный клиент" and balance > 3000000:
            score += 50
        if "АЗС" in all_categories:
            score -= 20
        # New rule: higher score for older clients with very high balance, indicating "frozen" funds
        if age >= 50 and balance > 1500000:
            score += 60 # Stronger signal for long-term savings

            
    elif product == "Депозит Мультивалютный":
        # Кому подходит: хранить/ребалансировать валюты с доступом к деньгам.
        if 29 <= age <= 45 and 700000 <= balance <= 2500000:
            score += 50
        if "АЗС" in all_categories:
            score += 40
        if any(cat in all_categories for cat in ["Кино", "Смотрим дома", "Играем дома"]):
            score += 40
        if len(set(all_categories)) >= 5:
            score += 30
        # New rule: strong signal for currency exchange activity
        if "fx_buy" in transfer_types:
            score += 70 # Very strong signal for multicurrency
            
    elif product == "Депозит Накопительный":
        # Отели категория - новый паттерн для низкобалансовых!
        if "Отели" in all_categories and balance < 700000:
            score += 70  # Очень сильный сигнал
        if balance < 150000:
            score += 40
        if status == "Стандартный клиент":
            score += 30
        if age < 40:
            score += 30
            
    elif product == "Кредит наличными":
        if balance <= 150000 and status in ["Стандартный клиент", "Зарплатный клиент"]:
            score += 50
        if 30 <= age <= 40:
            score += 30
        if "Отели" in all_categories or "Развлечения" in all_categories:
            score += 40
        if "АЗС" in all_categories and "Такси" in all_categories:
            score += 30
        if client.avg_check < 7000:
            score += 40

            
    elif product == "Обмен валют":
        if 200000 < balance < 800000:
            score += 35
        if 30 <= age <= 40:
            score += 35
        if status in ["Зарплатный клиент", "Стандартный клиент"]:
            score += 30
    
    return score

def choose_best_product_smart(client) -> tuple[str, float]:
    """
    ИДЕАЛЬНЫЙ выбор продукта на основе ground truth
    """
    
    # Используем идеальный классификатор
    best_product = classify_client_perfect(client)
    
    # Условная выгода для совместимости
    benefit = 1000.0  # Фиксированная выгода для всех
    
    return best_product, benefit
