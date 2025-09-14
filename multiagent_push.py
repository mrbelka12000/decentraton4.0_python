from __future__ import annotations
from dataclasses import dataclass
import json
from typing import Optional, Tuple

from langchain_openai import ChatOpenAI
from langchain.prompts import (
    ChatPromptTemplate,
    SystemMessagePromptTemplate,
    HumanMessagePromptTemplate,
    MessagesPlaceholder,
)
from langchain.agents import AgentExecutor, create_structured_chat_agent
from pydantic import BaseModel, Field
from langchain.tools.render import render_text_description
from langchain.output_parsers import PydanticOutputParser

class ProductRecommendation(BaseModel):
    name: str = Field(description="The name of the product to recommend")
    reason: str = Field(description="The reason for the recommendation")

class PushGenerator(BaseModel):
    push: str = Field(description="The push message to generate")

FORMAT_INSTRUCTIONS_PRODUCT_RECOMMENDER = PydanticOutputParser(pydantic_object=ProductRecommendation).get_format_instructions()
FORMAT_INSTRUCTIONS_PUSH_GENERATOR = PydanticOutputParser(pydantic_object=PushGenerator).get_format_instructions()

def make_react_agent_product_recommender(
    system_text: str,
    model: str = "gpt-4o-mini",
    temperature: float = 0.3
) -> AgentExecutor:
    llm = ChatOpenAI(model=model, temperature=temperature).with_structured_output(ProductRecommendation)

    tools = []
    tools_str = render_text_description(tools)
    tool_names = ", ".join(t.name for t in tools)

    prompt = ChatPromptTemplate.from_messages(
        [
            SystemMessagePromptTemplate.from_template(
                system_text + "\n\n"
                "Доступные инструменты:\n{tools}\n\n"
                "Имена инструментов: {tool_names}\n\n"
                "Следуй формату размышлений и действий:\n{format_instructions}\n"
            ),
            HumanMessagePromptTemplate.from_template("{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad"),
        ]
    ).partial(
        tools=tools_str,
        tool_names=tool_names,
        format_instructions=FORMAT_INSTRUCTIONS_PRODUCT_RECOMMENDER,
    )

    agent = create_structured_chat_agent(llm=llm, tools=tools, prompt=prompt)
    return AgentExecutor(agent=agent, tools=tools, verbose=False, handle_parsing_errors=False)

def make_react_agent_push_generator(system_text: str, model: str = "gpt-4o-mini", temperature: float = 0.3) -> AgentExecutor:
    llm = ChatOpenAI(model=model, temperature=temperature).with_structured_output(PushGenerator)

    tools = []
    tools_str = render_text_description(tools)
    tool_names = ", ".join(t.name for t in tools)


    prompt = ChatPromptTemplate.from_messages(
        [
            SystemMessagePromptTemplate.from_template(
                system_text + "\n\n"
                "Доступные инструменты:\n{tools}\n\n"
                "Имена инструментов: {tool_names}\n\n"
                "Следуй формату размышлений и действий:\n{format_instructions}\n"
            ),
            HumanMessagePromptTemplate.from_template("{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad"),
        ]
    ).partial(
        tools=tools_str,
        tool_names=tool_names,
        format_instructions=FORMAT_INSTRUCTIONS_PUSH_GENERATOR,
    )
    agent = create_structured_chat_agent(llm=llm, tools=[], prompt=prompt)
    return AgentExecutor(agent=agent, tools=[], verbose=False, handle_parsing_errors=False)

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

SYSTEM_PROMPT_FOR_SAVINGS = """Ты пишешь короткие пуш-уведомления про финансы.
Тон: на равных, просто и по-человечески; обращение на «вы» (с маленькой буквы).
Важное — в начале, без воды/канцеляризмов/пассивного залога. Без морали и давления.
Можно лёгкий, ненавязчивый юмор; максимум один уместный эмодзи. Без жаргона «в лоб».
Для молодёжи (<25): чуть живее; для постарше (>=25): серьёзнее, спокойнее.
Формат и редполитика:
- Длина пуша: 180–220 символов.
- Без КАПС; максимум один «!» и только по делу.
- Даты: дд.мм.гггг или «30 августа 2025» — где уместно.
- Числа: дробная часть — запятая; разряды — пробелы.
- Валюта: в приложении — «₸», в SMS — «тг»; знак/код отделяется пробелом (напр. 2 490 ₸ / 2 490 тг).
- Кнопки/ссылки называй глаголами: «Открыть», «Настроить», «Посмотреть».
- Никаких крикливых обещаний, давления и дефицита.
- Варианты текста должны звучать по-разному: используй разные конструкции, порядок слов и стили (от лаконичных до чуть более образных).
- Допускается лёгкая метафора или сравнение (не более одного за пуш).
- Начало сообщения может меняться: иногда прямо с выгоды, иногда с ситуации/наблюдения.
- Добавляй разные связки: «по итогу», «вышло бы», «можно было бы», «получилось бы» вместо шаблонного «вы могли сэкономить».
- Не делай пуши однотипными — меняй глаголы действия («узнать», «открыть», «попробовать», «посмотреть»).
- ВНИМАНИЕ: если выгода 0.00 ₸, то не упоминай выгоду вообще, а просто предложи продукт, но без намека на бедность.
Выводи только итоговый текст пуша, без комментариев и префиксов.
"""

USER_PROMPT_TEMPLATE_FOR_SAVINGS = """Дано:
- Имя: {name}
- Возраст: {age}
- Статус: {status}
- Потенциальная экономия: {profit_fmt} ₸
- Обоснование: {reason}
- Канал: {channel_label}{product_line}

Задача:
1) Скажи о выгоде {profit_fmt} ₸, но формулировку подавай по-разному (не повторяйся).
2) Коротко предложи продукт или действие; стиль может быть чуть разнообразнее (от прямого до намёка).
3) Учитывай тон по возрасту.
4) Заверши корректным призывом: «Открыть», «Настроить» или «Посмотреть» (вариативно).


Сгенерируй один пуш (100-150 символов)."""


def make_product_recommender_agent() -> AgentExecutor:
    return make_react_agent_product_recommender(
        system_text="Ты умный ассистент банка. Следуй инструкциям и верни строго JSON, как описано.",
        model="gpt-4o-mini",
        temperature=0.3,
    )


def recommend_product(agent: AgentExecutor, client: Client) -> Tuple[Optional[str], Optional[str], dict]:
    top4_str = "\n".join(f"{i['category']}: {i['amount']:,.2f} ₸" for i in client.top4_categories)
    filled = PROMPT_TEMPLATE.format(
        client_name=client.name,
        client_status=client.status,
        client_age=client.age,
        client_city=client.city,
        avg_monthly_balance=f"{client.avg_monthly_balance_KZT:,.2f}",
        total_transactions=client.total_transactions,
        total_transfers_in=client.total_transfers_in,
        total_transfers_out=client.total_transfers_out,
        total_transfers=client.total_transfers,
        top4_categories=top4_str,
    )
    out = agent.invoke({"input": filled, "agent_scratchpad": []})
    raw = (out.get("output") or "").strip()

    def _extract_json(s: str) -> str:
        a, b = s.find("{"), s.rfind("}")
        return s[a:b+1] if a != -1 and b != -1 and b > a else s

    data = json.loads(_extract_json(raw))
    sugg = data.get("product_suggestion") or {}
    return sugg.get("name"), sugg.get("reason"), data


def make_push_master_agent() -> AgentExecutor:
    return make_react_agent_push_generator(
        system_text=SYSTEM_PROMPT_FOR_SAVINGS,
        model="gpt-4o-mini",
        temperature=0.7,
    )


def generate_push(master_agent: AgentExecutor,
                  name: str,
                  age: int,
                  status: str,
                  profit: float | int,
                  reason: str,
                  product_type: Optional[str]) -> str:
    product_line = f"\n- Рекомендуемый продукт: {product_type}" if product_type else ""
    user_prompt = USER_PROMPT_TEMPLATE_FOR_SAVINGS.format(
        name=name,
        age=age,
        status=status,
        profit_fmt=f"{profit:,.2f}",
        reason=reason,
        channel_label="приложение",
        product_line=product_line,
    )
    out = master_agent.invoke({"input": user_prompt, "agent_scratchpad": []})
    return (out.get("output") or "").strip()


class MultiAgentSystem:
    def __init__(self,
                 model_recommender: str = "gpt-4o-mini",
                 model_master: str = "gpt-4o-mini"):
        self.recommender = make_product_recommender_agent()
        self.master = make_push_master_agent()

    def recommend_product(self, client: Client) -> Tuple[Optional[str], Optional[str], dict]:
        return recommend_product(self.recommender, client)

    def generate_push(self, client: Client, profit: float | int, reason: str, product_type: Optional[str]) -> str:
        return generate_push(
            self.master,
            name=client.name,
            age=client.age,
            status=client.status,
            profit=profit,
            reason=reason,
            product_type=product_type,
        )