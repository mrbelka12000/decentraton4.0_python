PROMPT_TEMPLATE = """
Ты — финансовый ассистент, который анализирует поведение клиента и предлагает персональные push-уведомления.
Твоя цель — помочь клиенту контролировать расходы, формировать сбережения и замечать возможности для дохода.
Используй только предоставленные категории расходов и продукты. Если не хватает данных — делай консервативные рекомендации.

## Контекст:
- Профиль клиента:
  - Имя: {client_name}
  - Статус: {client_status}
  - Возраст: {client_age}
  - Город: {client_city}
  - Средний месячный баланс (KZT): {avg_monthly_balance}

- Сводка за последние 3 месяца:
  - Расходы по категориям:
    {total_transactions}
  - Полученные переводы (IN):
    {total_transfers_in}
  - Переводы другим (OUT):
    {total_transfers_out}
  - Общее движение средств:
    {total_transfers}

- Топ-4 категорий расходов:
{top4_categories}



- Каталог доступных банковских продуктов:
  1) Карта для путешествий → подходит, если заметные траты на «Путешествия», «Такси», «Отели».
  2) Премиальная карта → для клиентов с высоким балансом/остатком, у кого траты на «Кафе и рестораны», «Косметика и Парфюмерия».
  3) Кредитная карта → для клиентов с активными расходами на «Игры», «Доставка», «Кино».
  4) Обмен валют → 
     • Подходит, если клиент переводил или получал более 10 000 000 ₸ за период.  
     • Также полезен для клиентов с валютными доходами или активными трансграничными операциями.
  5) Кредит наличными → если расходы превышают баланс или есть большие исходящие переводы.
  6) Депозит Мультивалютный → выгоден клиентам с доходами/переводами в разных валютах.
  7) Депозит Сберегательный → для тех, кто копит и не планирует тратить ближайшее время.
  8) Депозит Накопительный → для клиентов с регулярными расходами, кто хочет откладывать постепенно.
  9) Инвестиции → для тех, у кого остаётся свободный баланс и низкие расходы.
  10) Золотые слитки → вариант для клиентов с высоким доходом и желающих долгосрочно сохранить капитал.

## Задача:
1) Проанализируй расходы относительно доступного баланса и доходов. Обрати внимание на ростовые/аномальные категории.
2) Подбери РОВНО один продукт из каталога, который лучше всего подходит профилю и паттернам трат/переводов,
   и обоснуй выбор кратко (как оффер). Если явного соответствия нет — верни null.

## Формат ответа (строго JSON):
{{
  "product_suggestion": {{
    "name": "продукт",
    "reason": "обоснование"
  }}
}}
"""


def get_recomended_product(client) -> dict:
  from openai import OpenAI
  import json

  top4_str = "\n".join(
    [f"{item['category']}: {item['amount']:,.2f} ₸" for item in client.top4_categories]
  )

  prompt = PROMPT_TEMPLATE.format(client_name=client.name,
                                    client_status=client.status,
                                    client_age=client.age,
                                    client_city=client.city,
                                    avg_monthly_balance=client.avg_monthly_balance_KZT,
                                    total_transactions=client.total_transactions,
                                    total_transfers_in=client.total_transfers_in,
                                    total_transfers_out=client.total_transfers_out,
                                    total_transfers=client.total_transfers,
                                    top4_categories=top4_str)
  
  client = OpenAI()

  response = client.chat.completions.create(
    model="gpt-4o-mini",   # or "gpt-4o", "gpt-3.5-turbo", etc.
    messages=[
        {"role": "system", "content": "Ты умный ассистент банка."},
        {"role": "user", "content": prompt}
    ],
    temperature=0.3
  )
  result = response.choices[0].message.content
  
  # Parse JSON string to Python dict
  parsed = json.loads(result)
  # Access values
  product_name = parsed["product_suggestion"]["name"]
  reason = parsed["product_suggestion"]["reason"]

  return product_name, reason


from datetime import date

# --- 1) Системная инструкция для модели ---
SYSTEM_PROMPT = """Ты пишешь короткие пуш-уведомления про финансы.
Тон: на равных, просто и по-человечески; обращение на «вы» (с маленькой буквы).
Важное — в начале, без воды/канцеляризмов/пассивного залога. Без морали и давления.
Можно лёгкий, ненавязчивый юмор; максимум один уместный эмодзи. Без жаргона «в лоб».
Для молодёжи (<30): чуть живее; для постарше (>=30): серьёзнее, спокойнее.
Формат и редполитика:
- Длина пуша: 180–220 символов.
- Без КАПС; максимум один «!» и только по делу.
- Даты: дд.мм.гггг или «30 августа 2025» — где уместно.
- Числа: дробная часть — запятая; разряды — пробелы.
- Валюта: в приложении — «₸», в SMS — «тг»; знак/код отделяется пробелом (напр. 2 490 ₸ / 2 490 тг).
- Кнопки/ссылки называй глаголами: «Открыть», «Настроить», «Посмотреть».
- Никаких крикливых обещаний, давления и дефицита.
Выводи только итоговый текст пуша, без комментариев и префиксов.
"""

# --- 2) Пользовательский шаблон запроса ---
USER_PROMPT_TEMPLATE = """Дано:
- Имя: {name}
- Возраст: {age}
- Потенциальная экономия: {saving_fmt} ₸
- Канал: {channel_label}{product_line}

Задача:
1) Начни с выгоды: что клиент мог сэкономить — {saving_fmt} ₸.
2) Коротко и по делу предложи релевантный продукт/действие.
3) Учитывай тон по возрасту.
4) Заверши корректным призывом: «Открыть», «Настроить» или «Посмотреть».

Сгенерируй один пуш (100-150 символов)."""

def build_messages(name: str,
                   age: int,
                   saving: float | int,
                   product_type: str | None = None) -> list[dict]:

    product_line = f"\n- Рекомендуемый продукт: {product_type}" if product_type else ""

    user_prompt = USER_PROMPT_TEMPLATE.format(
        name=name,
        age=age,
        saving_fmt=f"{saving:,.2f}",
        channel_label="приложение",
        product_line=product_line
    )

    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]


def generate_push_notification(name: str,
                               age: int,
                               saving: float | int,
                               product_type: str | None = None,
                               today: date | None = None) -> str:
    from openai import OpenAI

    messages = build_messages(name, age, saving, product_type, today)

    client = OpenAI()

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        temperature=0.2
    )

    push_text = response.choices[0].message.content.strip()
    return push_text