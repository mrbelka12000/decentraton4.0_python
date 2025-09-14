from dataclasses import dataclass
from typing import List, Optional, Dict, Tuple
from collections import defaultdict
from statistics import stdev
from datetime import datetime


# ---------- Конфиги (поддаются тюнингу) ----------
WEIGHTS = {
    "savings":  (0.40, 0.40, 0.20),  # w1 balance, w2 (1-volatility), w3 (1-withdrawals)
    "accum":    (0.50, 0.30, 0.20),  # v1 topups_per_month, v2 avg_topup_amount, v3 (1-withdrawals)
    "multi":    (0.50, 0.30, 0.20),  # u1 fx_share, u2 foreign_spend_share, u3 balance buffer
}
THRESHOLDS = {
    "high_balance": 2_000_000,   # для сберегательного
    "fx_buffer":      500_000,   # для мультивалютного
    "min_score":            40,  # порог, ниже — не предлагать вклад
    "target_topups_pm":       2,  # желательная частота пополнений/мес
    "target_topup_amt": 100_000,  # «хороший» размер пополнения
}
# Грубые ориентиры ставок (для оценки прибыли, чтобы заполнить max_potential_profit)
RATES = {
    "Депозит Сберегательный": 0.14,  # 14% годовых
    "Депозит Накопительный":  0.12,
    "Депозит Мультивалютный": 0.10,
}

FOREIGN_CURRENCIES = {"USD", "EUR", "GBP"}


# ---------- Утилиты ----------
def _ym(date_str: str) -> Tuple[int, int]:
    """Вернуть (year, month) из строки даты."""
    # Поддержи форматы 'YYYY-MM-DD' и 'DD.MM.YYYY'
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%Y/%m/%d"):
        try:
            d = datetime.strptime(date_str, fmt)
            return d.year, d.month
        except ValueError:
            continue
    # Если формат неизвестен — попробуем ISO-парсинг
    d = datetime.fromisoformat(date_str.replace("Z", "").replace("T", " "))
    return d.year, d.month


def _safe_stdev(values: List[float]) -> float:
    return stdev(values) if len(values) >= 2 else 0.0


# ---------- Признаки клиента (features) ----------
def compute_client_features(client) -> Dict[str, float]:
    txs = client.transactions or []
    trs = client.transfers or []

    # Баланс, доступный для расчётов
    balance = client.available_balance or float(client.avg_monthly_balance_KZT) or 0.0

    # Доли по валюте и FX-операциям (по количеству, можно заменить на доли по сумме)
    fx_ops = sum(1 for t in trs if t.type in ("deposit_fx_withdraw_in", "deposit_fx_topup_out"))
    fx_share = fx_ops / len(trs) if trs else 0.0

    foreign_spend_ops = sum(1 for t in txs if t.currency in FOREIGN_CURRENCIES)
    foreign_spend_share = foreign_spend_ops / len(txs) if txs else 0.0

    # Доля «out» по сумме (разумнее, чем по количеству)
    out_amt = sum(t.amount for t in trs if t.direction == "out")
    in_amt = sum(t.amount for t in trs if t.direction == "in")
    total_amt = out_amt + in_amt
    withdrawal_rate = (out_amt / total_amt) if total_amt > 0 else 0.0

    # Пополнения вкладов (условимся: type == 'deposit_topup_out' — перевод со счёта на вклад)
    topup_trs = [t for t in trs if t.type == "deposit_topup_out"]
    # Считаем «в месяц»: количество месяцев по датам переводов за период
    months_seen = { _ym(t.date) for t in trs } or { _ym(tx.date) for tx in txs } or {(1970,1)}
    months_n = max(1, len(months_seen))
    topups_per_month = len(topup_trs) / months_n
    avg_topup_amount = (sum(t.amount for t in topup_trs) / len(topup_trs)) if topup_trs else 0.0

    # Волатильность расходов: stddev месячных трат / баланс
    month_out = defaultdict(float)
    for tx in txs:
        y, m = _ym(tx.date)
        month_out[(y, m)] += float(tx.amount)
    monthly_out_values = list(month_out.values()) or [0.0]
    volatility_raw = _safe_stdev(monthly_out_values)
    volatility = min(volatility_raw / balance, 1.0) if balance > 0 else 1.0  # без баланса = высокая вола

    return {
        "balance": balance,
        "fx_share": float(fx_share),
        "foreign_spend_share": float(foreign_spend_share),
        "withdrawal_rate": float(withdrawal_rate),
        "topups_per_month": float(topups_per_month),
        "avg_topup_amount": float(avg_topup_amount),
        "volatility": float(volatility),
    }


# ---------- Скоринг депозитов ----------
def score_deposits(feat: Dict[str, float]) -> Dict[str, float]:
    w1, w2, w3 = WEIGHTS["savings"]
    v1, v2, v3 = WEIGHTS["accum"]
    u1, u2, u3 = WEIGHTS["multi"]

    score_savings = 100 * (
        w1 * min(feat["balance"] / THRESHOLDS["high_balance"], 1.0)
        + w2 * (1.0 - feat["volatility"])
        + w3 * (1.0 - feat["withdrawal_rate"])
    )

    score_accum = 100 * (
        v1 * min(feat["topups_per_month"] / THRESHOLDS["target_topups_pm"], 1.0)
        + v2 * min(feat["avg_topup_amount"] / THRESHOLDS["target_topup_amt"], 1.0)
        + v3 * (1.0 - feat["withdrawal_rate"])
    )

    score_multi = 100 * (
        u1 * feat["fx_share"]
        + u2 * feat["foreign_spend_share"]
        + u3 * min(feat["balance"] / THRESHOLDS["fx_buffer"], 1.0)
    )

    return {
        "Депозит Сберегательный": score_savings,
        "Депозит Накопительный": score_accum,
        "Депозит Мультивалютный": score_multi,
    }


def choose_deposit(scores: Dict[str, float], min_threshold: float = None) -> Optional[str]:
    if min_threshold is None:
        min_threshold = THRESHOLDS["min_score"]
    product, best = max(scores.items(), key=lambda kv: kv[1])
    return product if best >= min_threshold else None


# ---------- Оценка потенциальной выгоды (грубо, годовая) ----------
def estimate_profit(product: str, balance: float) -> float:
    rate = RATES.get(product, 0.0)
    return balance * rate


def pick_deposit_product_for_client(client):
    feat = compute_client_features(client)
    scores = score_deposits(feat)

    product, confidence = choose_deposit_with_confidence(scores)

    client.available_balance = client.available_balance or float(client.avg_monthly_balance_KZT) or 0.0
    client.product = product
    client.deposit_selection_confidence = confidence

    if product is not None:
        client.max_potential_profit = estimate_profit(product, feat["balance"])
    else:
        client.max_potential_profit = 0.0

    return client

def _softmax_confidence(scores: dict[str, float], temperature: float = 15.0) -> tuple[str, float]:
    import math
    """
    Превращаем баллы [0..100] в вероятности через softmax.
    temperature>0 сглаживает уверенность (меньше t — резче).
    Возвращает (best_product, confidence_of_best).
    """
    # защита от пустоты
    if not scores:
        return None, 0.0

    # порог минимального скора
    min_thr = THRESHOLDS["min_score"]

    # softmax
    vals = list(scores.values())
    # центрируем вокруг max — численно стабильнее
    vmax = max(vals)
    exps = {k: math.exp((v - vmax) / max(1e-9, temperature)) for k, v in scores.items()}
    z = sum(exps.values()) or 1.0
    probs = {k: exps[k] / z for k in scores.keys()}

    best_prod = max(scores.items(), key=lambda kv: kv[1])[0]
    best_score = scores[best_prod]
    conf = probs[best_prod]

    # если скора ниже порога — уверенность обнулим
    if best_score < min_thr:
        return None, 0.0
    return best_prod, float(conf)


def choose_deposit_with_confidence(scores: dict[str, float]) -> tuple[Optional[str], float]:
    """
    Обёртка над _softmax_confidence с учётом порога.
    """
    return _softmax_confidence(scores, temperature=15.0)