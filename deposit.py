from __future__ import annotations
from dataclasses import dataclass
from typing import List, Optional, Dict, Tuple

# ----- Конфиг: курсы и ставки (можешь менять под бэкенд/окружение) -----
DEFAULT_FX_RATES_TO_KZT: Dict[str, float] = {
    "KZT": 1.0,
    "USD": 500.0,
    "EUR": 600.0,
    "RUB": 5.0,
}

DEFAULT_DEPOSIT_RATES = {
    "Депозит Накопительный": 0.14,   # 14% годовых (пример)
    "Депозит Мультивалютный": 0.02,  # 2% годовых на FX-остаток (пример)
}

# Сколько месяцев охватывают данные (по ТЗ — 3 мес)
OBSERVED_MONTHS = 3


# ----- Утилиты -----
def to_kzt(amount: float, currency: str, rates: Dict[str, float]) -> float:
    rate = rates.get(currency.upper())
    if rate is None:
        raise ValueError(f"Нет курса для {currency}")
    return amount * rate


def count_fx_transfers(client) -> Tuple[int, float, float]:
    """
    Возвращает:
      - число FX-топапов (deposit_fx_topup_out)
      - суммарный объём topup_out в KZT
      - суммарный объём withdraw_in в KZT
    """
    topup_cnt = 0
    topup_sum_kzt = 0.0
    withdraw_sum_kzt = 0.0
    for tr in client.transfers:
        if tr.type == "deposit_fx_topup_out":
            topup_cnt += 1
            topup_sum_kzt += to_kzt(tr.amount, tr.currency, DEFAULT_FX_RATES_TO_KZT)
        elif tr.type == "deposit_fx_withdraw_in":
            withdraw_sum_kzt += to_kzt(tr.amount, tr.currency, DEFAULT_FX_RATES_TO_KZT)
    return topup_cnt, topup_sum_kzt, withdraw_sum_kzt


def has_required_fx_patterns(client) -> bool:
    seen_topup = any(t.type == "deposit_fx_topup_out" for t in client.transfers)
    seen_withdraw = any(t.type == "deposit_fx_withdraw_in" for t in client.transfers)
    return seen_topup and seen_withdraw


def estimate_avg_fx_balance_kzt(client) -> float:
    """
    Приблизительно оцениваем средний FX-остаток за период.
    Метод: проходим по времени и интегрируем кумулятивный остаток,
    но без дат можно применить устойчивую эвристику:
      avg_balance ≈ max(0, (sum_topups_kzt - sum_withdraws_kzt * 0.8))
    Коэффициент 0.8 сглаживает "качание" баланса.
    """
    _, topup_kzt, withdraw_kzt = count_fx_transfers(client)
    return max(0.0, topup_kzt - withdraw_kzt * 0.8)


# ----- Прибыль по продуктам -----
def profit_deposit_nakop(client, annual_rate: float) -> float:
    """
    Ожидаемая прибыль (KZT) за период наблюдений от накопительного вклада.
    """
    monthly_rate = annual_rate / 12.0
    return client.avg_monthly_balance_KZT * monthly_rate * OBSERVED_MONTHS


def profit_deposit_multicurrency(client, annual_rate: float) -> float:
    """
    Ожидаемая прибыль (KZT) за период наблюдений от мультивалютного вклада.
    Основана на оценке среднего FX-остатка в KZT.
    """
    avg_fx_bal_kzt = estimate_avg_fx_balance_kzt(client)
    monthly_rate = annual_rate / 12.0
    return avg_fx_bal_kzt * monthly_rate * OBSERVED_MONTHS


# ----- Уверенность (0.0..1.0) -----
def confidence_nakop(client, threshold: float = 1_000_000) -> float:
    """
    База 0.55 при выполнении порога.
    + до +0.4 линейно за «запас» над порогом (капим 0.95)
    """
    if client.avg_monthly_balance_KZT <= threshold:
        return 0.0
    surplus = client.avg_monthly_balance_KZT - threshold
    bonus = min(0.4, (surplus / threshold) * 0.4)
    return min(0.95, 0.55 + bonus)


def confidence_multicurrency(client) -> float:
    """
    База 0.6 если присутствуют оба паттерна (topup_out & withdraw_in).
    + до +0.35 за частоту топапов, +0.0..+0.0 за объём (по желанию).
    """
    if not has_required_fx_patterns(client):
        return 0.0
    topup_cnt, topup_kzt, withdraw_kzt = count_fx_transfers(client)
    # 0..0.35 за частоту (нормализация на 6 событий за 3 мес)
    freq_bonus = min(0.35, (topup_cnt / 6.0) * 0.35)
    return min(0.95, 0.60 + freq_bonus)


# ----- Правила применимости -----
def eligible_nakop(client, threshold: float = 1_000_000) -> bool:
    return client.avg_monthly_balance_KZT > threshold


def eligible_multicurrency(client) -> bool:
    return has_required_fx_patterns(client)


# ----- Основной выбор продукта -----
def choose_deposit_product(
    client,
    deposit_rates: Dict[str, float] = None,
) -> Dict[str, object]:
    """
    Возвращает словарь:
      {
        'product': str | None,
        'profit_KZT': float,
        'confidence': float,
        'reasons': List[str]
      }
    """
    rates = deposit_rates or DEFAULT_DEPOSIT_RATES
    candidates = []

    # Кандидат: Депозит Накопительный
    if eligible_nakop(client):
        profit = profit_deposit_nakop(client, rates["Депозит Накопительный"])
        conf = confidence_nakop(client)
        candidates.append(("Депозит Накопительный", profit, conf, [
            "Средний остаток > 1 000 000 ₸",
            f"Ставка по продукту ~{int(rates['Депозит Накопительный']*100)}% годовых (пример)"
        ]))

    # Кандидат: Депозит Мультивалютный
    if eligible_multicurrency(client):
        profit = profit_deposit_multicurrency(client, rates["Депозит Мультивалютный"])
        conf = confidence_multicurrency(client)
        candidates.append(("Депозит Мультивалютный", profit, conf, [
            "Есть и пополнения, и снятия FX-вклада (deposit_fx_topup_out & deposit_fx_withdraw_in)",
            f"Ставка по продукту ~{int(rates['Депозит Мультивалютный']*100)}% годовых (пример)"
        ]))

    if not candidates:
        return {
            "product": None,
            "profit_KZT": 0.0,
            "confidence": 0.0,
            "reasons": ["Нет условий для депозитов (по заданным правилам)."]
        }

    # Выбор: максимальная прибыль, при равенстве — по уверенности
    candidates.sort(key=lambda x: (x[1], x[2]), reverse=True)
    best = candidates[0]
    return {
        "product": best[0],
        "profit_KZT": round(best[1], 2),
        "confidence": round(best[2], 3),
        "reasons": best[3]
    }
