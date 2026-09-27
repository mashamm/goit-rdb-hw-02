"""Збирає notebooks/hw2_ecommerce_churn.ipynb із SQL-файлів і Markdown-текстів."""
import base64
import pathlib

import nbformat as nbf

ROOT = pathlib.Path(__file__).resolve().parents[1]
DDL = (ROOT / "sql/01_ddl.sql").read_text(encoding="utf-8").strip()
DATA = (ROOT / "sql/02_data.sql").read_text(encoding="utf-8").strip()
PNG = base64.b64encode((ROOT / "er/er_diagram.png").read_bytes()).decode()

cells = []
md = lambda s, **kw: cells.append(nbf.v4.new_markdown_cell(s.strip(), **kw))
code = lambda s: cells.append(nbf.v4.new_code_cell(s.strip()))
sql = lambda s: code("%%sql\n" + s.strip())

# ---------------------------------------------------------------- intro
md("""
# ДЗ 2. Схема даних для ML-сценарію: E-commerce churn

**Студентка:** Samoilenko Mariia

**Сценарій.** Інтернет-магазин хоче прогнозувати відтік клієнтів. У момент `prediction_ts` модель отримує ознаки клієнта
(активність за останні 30/90 днів) і прогнозує `churn_in_horizon` — чи **не** зробить клієнт жодного оплаченого
замовлення протягом наступних 30 днів (`label_horizon_end = prediction_ts + 30 днів`).

**Структура notebook**
1. ER-діаграма (бізнесові сутності, offline- та online-рівні feature store)
2. DDL у PostgreSQL 16
3. Нормалізація та свідома денормалізація
4. Point-in-Time correctness: історичні ознаки, AS-OF запити, training-data join, контроль інтервалів
5. Online-рівень: матеріалізація з offline-джерела
6. Reflection
""")

md("## 0. Середовище: PostgreSQL 16 через `pgserver` + `jupysql`")
code('%pip install -q pgserver jupysql "psycopg[binary]"')
code('''
import os

import pgserver
from sqlalchemy import create_engine, text

# Локальний сервер PostgreSQL 16 усередині notebook; дані зберігаються в ./pgdata
pg = pgserver.get_server(os.path.abspath("pgdata"))
engine = create_engine(pg.get_uri())

with engine.connect() as conn:
    print(conn.execute(text("SELECT version()")).scalar())

%load_ext sql
%sql engine
%config SqlMagic.displaylimit = 50
%config SqlMagic.displaycon = False
''')

# ---------------------------------------------------------------- task 1
md("""
## Завдання 1. ER-діаграма

Діаграму побудовано в Graphviz (текстовий DSL `er/er_diagram.dot` у репозиторії; зображення — `er/er_diagram.png`, `er/er_diagram.svg`).

- **Синій блок** — бізнесові сутності (OLTP, 3НФ); фіолетова таблиця — bridge-таблиця N:M.
- **Жовтий блок** — offline-рівень feature store: історія ознак із `valid_from / valid_to` і training events.
- **Зелений блок** — online-рівень: один денормалізований рядок поточних ознак на клієнта.
- Суцільні лінії — FOREIGN KEY; пунктирні — логічні зв'язки без FK (AS-OF JOIN і матеріалізація).

![ER-діаграма](attachment:er_diagram.png)
""", attachments={"er_diagram.png": {"image/png": PNG}})

md("""
### Кардинальності та обов'язковість зв'язків

Нотація `min..max`: `min = 0` — зв'язок необов'язковий, `min = 1` — обов'язковий.

| Батьківська таблиця (PK) | Дочірня таблиця (FK) | Кардинальність | Зміст |
|---|---|---|---|
| `hw2_customers` | `hw2_orders` | 1..1 — 0..N | замовлення завжди має клієнта; клієнт може ще нічого не купити |
| `hw2_orders` | `hw2_order_items` | 1..1 — 1..N | позиція належить одному замовленню; замовлення має хоча б одну позицію (бізнес-правило) |
| `hw2_products` | `hw2_order_items` | 1..1 — 0..N | товар може ще жодного разу не продаватися |
| `hw2_categories` | `hw2_products` | 1..1 — 0..N | товар обов'язково має категорію |
| `hw2_customers` | `hw2_customer_features_offline` | 1..1 — 0..N | історія версій ознак клієнта (може бути порожньою для нового клієнта) |
| `hw2_customers` | `hw2_training_events` | 1..1 — 0..N | точки прогнозу з міткою |
| `hw2_customers` | `hw2_customer_features_online` | 1..1 — 0..1 | не більше одного поточного рядка на клієнта |

### Зв'язок N:M

У домені є природний зв'язок **N:M між замовленнями й товарами**: одне замовлення містить багато товарів,
один товар входить у багато замовлень. Його реалізовано bridge-таблицею `hw2_order_items` зі складеним
PK `(order_id, product_id)` і власними атрибутами зв'язку `quantity`, `unit_price` (ціна на момент покупки).
Зв'язок «клієнт ↔ товар» теж є N:M, але він похідний (через `orders` → `order_items`), тому окрема
таблиця для нього не потрібна.
""")

# ---------------------------------------------------------------- task 2
md("""
## Завдання 2. DDL у PostgreSQL 16

- `DROP TABLE IF EXISTS ... CASCADE` на початку робить повторний запуск відтворюваним.
- `PRIMARY KEY` у кожній таблиці, `FOREIGN KEY` для всіх зв'язків, `NOT NULL` для обов'язкових колонок.
- Доменні `CHECK`: формат коду країни, допустимі статуси замовлення, невід'ємні кількості/суми, `quantity > 0`.
- Temporal `CHECK (valid_to IS NULL OR valid_to > valid_from)` в історичній feature-таблиці.
- Індекси під основні access patterns:
  - `hw2_idx_customer_features_asof (customer_id, valid_from DESC)` — AS-OF lookup ознак клієнта;
  - `hw2_uq_customer_features_current` — частковий унікальний індекс: не більше однієї поточної версії (`valid_to IS NULL`) на клієнта;
  - `hw2_idx_orders_customer_ts (customer_id, order_ts)` — вибірка замовлень клієнта за часовим вікном під час розрахунку ознак.
""")
sql(DDL)
sql("""
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'public'
  AND table_name LIKE 'hw2\\_%'
ORDER BY table_name;
""")

# ---------------------------------------------------------------- task 3
md("""
## Завдання 3. Нормалізація

**Таблиці у 3НФ.** `hw2_customers`, `hw2_categories`, `hw2_products`, `hw2_orders`, `hw2_order_items` і
`hw2_customer_features_offline` перебувають у 3НФ: значення атомарні, кожна таблиця має PK, а неключові атрибути
залежать від усього ключа і тільки від нього — часткових і транзитивних залежностей немає.

**Функціональні залежності, враховані під час декомпозиції:**
- `customer_id → email, signup_date, country, marketing_opt_in`
- `category_id → name`; `product_id → category_id, name, list_price, is_active`
- `order_id → customer_id, order_ts, status`
- `(order_id, product_id) → quantity, unit_price`
- `(customer_id, valid_from) → valid_to, orders_30d, spend_30d, days_since_last_order, distinct_categories_90d`

Назву категорії винесено в окрему таблицю, щоб прибрати транзитивну залежність `product_id → category_id → category_name`.
Суму замовлення не зберігаємо — вона обчислюється з позицій. `unit_price` не дублює `list_price`: це ціна на момент
покупки, вона залежить від позиції замовлення, а не від товару.

**Свідома денормалізація.** `hw2_customer_features_online` містить лише поточну версію ознак і копії `country`,
`signup_date` з `hw2_customers`. Read pattern — lookup одного рядка за `customer_id` під час інференсу з низькою
latency: один index scan за PK, без JOIN і без часових фільтрів.

**Ризик неузгодженості.** Якщо з'явиться нова версія ознак або клієнт змінить країну, online-рядок буде застарілим
до наступного оновлення.

**Оновлення.** Батч-джоба бере з offline-таблиці версію з `valid_to IS NULL`, приєднує атрибути клієнта й виконує
`INSERT ... ON CONFLICT (customer_id) DO UPDATE` (розділ 5). `feature_ts` = `valid_from` версії дає змогу контролювати
свіжість, а окремий запит рахує розбіжності між рівнями.
""")

# ---------------------------------------------------------------- task 4
md("""
## Завдання 4. Point-in-Time correctness

### 4.1. Тестові дані

- 12 temporal-версій ознак для 4 клієнтів (`customer_id = 42` — 4 послідовні версії, `1` і `2` — по 3, `3` — 2);
- усі часові літерали — `TIMESTAMPTZ` з явним `+00` (UTC);
- версії одного клієнта йдуть встик: `valid_to` попередньої = `valid_from` наступної, тому інтервали не перекриваються й не мають «дір»;
- 9 training events; серед них є подія рівно на межі версій (`2025-01-15 00:00:00+00`) і подія до появи першої версії ознак.
""")
sql(DATA)

md("""
### 4.2. Поява нової версії ознак (SCD Type 2) в одній транзакції

Нова версія додається двома кроками: закрити поточну (`valid_to = new_ts`) і вставити нову (`valid_from = new_ts`,
`valid_to = NULL`). Обидва кроки виконуються **атомарно** (`engine.begin()` = `BEGIN ... COMMIT`): якщо вставка
не вдасться, закриття старої версії теж відкотиться, і клієнт не залишиться без поточної версії.
Після цього кроку в історичній таблиці 13 рядків, у клієнта `3` — 3 версії.
""")
code('''
new_ts = "2025-01-20 00:00:00+00"

with engine.begin() as conn:  # BEGIN ... COMMIT (або ROLLBACK при помилці)
    conn.execute(text("""
        UPDATE hw2_customer_features_offline
        SET valid_to = CAST(:ts AS timestamptz)
        WHERE customer_id = 3
          AND valid_to IS NULL
    """), {"ts": new_ts})
    conn.execute(text("""
        INSERT INTO hw2_customer_features_offline
            (customer_id, valid_from, valid_to,
             orders_30d, spend_30d, days_since_last_order, distinct_categories_90d)
        VALUES (3, CAST(:ts AS timestamptz), NULL, 1, 50.00, 34, 1)
    """), {"ts": new_ts})
print("Нову версію для customer_id = 3 додано.")
''')
sql("""
SELECT customer_id,
       COUNT(*)                          AS versions,
       MIN(valid_from)                   AS first_version_from,
       COUNT(*) FILTER (WHERE valid_to IS NULL) AS current_versions
FROM hw2_customer_features_offline
GROUP BY customer_id
ORDER BY customer_id;
""")

md("""
### 4.3. AS-OF SELECT №1: ознаки клієнта 42 станом на `2024-12-10 10:00:00+00`

Очікувано: версія `[2024-11-01, 2024-12-15)` з `orders_30d = 2`. Версія, що починається 2024-12-15,
на момент прогнозу ще не існувала й не повинна потрапити в результат.
""")
sql("""
SELECT customer_id, orders_30d, spend_30d, days_since_last_order,
       distinct_categories_90d, valid_from, valid_to
FROM hw2_customer_features_offline
WHERE customer_id = 42
  AND valid_from <= TIMESTAMPTZ '2024-12-10 10:00:00+00'
  AND (valid_to > TIMESTAMPTZ '2024-12-10 10:00:00+00' OR valid_to IS NULL);
""")

md("""
### 4.4. AS-OF SELECT №2: момент рівно на межі версій `2025-01-15 00:00:00+00`

Інтервали напіввідкриті `[valid_from, valid_to)`: момент межі належить **лише новій** версії
(`valid_from = 2025-01-15`, `orders_30d = 0`), а стара версія з `valid_to = 2025-01-15` уже не чинна.
Тому результат — рівно один рядок.
""")
sql("""
SELECT customer_id, orders_30d, spend_30d, days_since_last_order,
       distinct_categories_90d, valid_from, valid_to
FROM hw2_customer_features_offline
WHERE customer_id = 42
  AND valid_from <= TIMESTAMPTZ '2025-01-15 00:00:00+00'
  AND (valid_to > TIMESTAMPTZ '2025-01-15 00:00:00+00' OR valid_to IS NULL);
""")

md("""
### 4.5. AS-OF SELECT №3: зріз ознак усіх клієнтів станом на `2024-12-20 10:00:00+00`

Такий point-in-time snapshot потрібен, наприклад, для batch-скорингу на історичну дату.
Для клієнта 3 має повернутися версія, що почалася рівно 2024-12-20 00:00.
""")
sql("""
SELECT c.customer_id, c.country,
       f.orders_30d, f.spend_30d, f.days_since_last_order,
       f.distinct_categories_90d, f.valid_from, f.valid_to
FROM hw2_customers AS c
LEFT JOIN hw2_customer_features_offline AS f
       ON f.customer_id = c.customer_id
      AND f.valid_from <= TIMESTAMPTZ '2024-12-20 10:00:00+00'
      AND (f.valid_to > TIMESTAMPTZ '2024-12-20 10:00:00+00' OR f.valid_to IS NULL)
ORDER BY c.customer_id;
""")

md("""
### 4.6. AS-OF JOIN: формування training data за `prediction_ts`

Кожен training event отримує лише ту версію ознак, яка була чинною на його `prediction_ts`.
`LEFT JOIN` зберігає подію навіть тоді, коли ознак ще не існувало (клієнт 3 на 2024-10-20) —
такі рядки з `NULL`-ознаками видно одразу, і їх можна свідомо відфільтрувати, а не втратити непомітно.
""")
sql("""
SELECT e.event_id,
       e.customer_id,
       e.prediction_ts,
       e.label_horizon_end,
       e.churn_in_horizon,
       f.orders_30d,
       f.spend_30d,
       f.days_since_last_order,
       f.distinct_categories_90d,
       f.valid_from AS feature_valid_from
FROM hw2_training_events AS e
LEFT JOIN hw2_customer_features_offline AS f
       ON f.customer_id = e.customer_id
      AND f.valid_from <= e.prediction_ts
      AND (f.valid_to > e.prediction_ts OR f.valid_to IS NULL)
ORDER BY e.event_id;
""")

md("""
### 4.7. Контроль часових інтервалів

1. Перевірка перекривних версій для одного `customer_id` — **має повернути 0 рядків**.
2. Автоматичні перевірки (`assert`): немає `valid_to <= valid_from`, немає перекриттів,
   AS-OF JOIN не розмножує training events, жодна приєднана версія не почалася після `prediction_ts`.
""")
sql("""
SELECT a.customer_id,
       a.valid_from AS a_from, a.valid_to AS a_to,
       b.valid_from AS b_from, b.valid_to AS b_to
FROM hw2_customer_features_offline AS a
JOIN hw2_customer_features_offline AS b
  ON a.customer_id = b.customer_id
 AND a.valid_from < COALESCE(b.valid_to, 'infinity'::timestamptz)
 AND b.valid_from < COALESCE(a.valid_to, 'infinity'::timestamptz)
 AND a.valid_from < b.valid_from;
""")
code('''
checks = {
    "перекривні версії": """
        SELECT COUNT(*)
        FROM hw2_customer_features_offline a
        JOIN hw2_customer_features_offline b
          ON a.customer_id = b.customer_id
         AND a.valid_from < COALESCE(b.valid_to, 'infinity'::timestamptz)
         AND b.valid_from < COALESCE(a.valid_to, 'infinity'::timestamptz)
         AND a.valid_from < b.valid_from""",
    "valid_to <= valid_from": """
        SELECT COUNT(*) FROM hw2_customer_features_offline
        WHERE valid_to IS NOT NULL AND valid_to <= valid_from""",
    "події з >1 версією ознак": """
        SELECT COUNT(*) FROM (
            SELECT e.event_id
            FROM hw2_training_events e
            JOIN hw2_customer_features_offline f
              ON f.customer_id = e.customer_id
             AND f.valid_from <= e.prediction_ts
             AND (f.valid_to > e.prediction_ts OR f.valid_to IS NULL)
            GROUP BY e.event_id
            HAVING COUNT(*) > 1) t""",
    "ознаки з майбутнього в AS-OF JOIN": """
        SELECT COUNT(*)
        FROM hw2_training_events e
        JOIN hw2_customer_features_offline f
          ON f.customer_id = e.customer_id
         AND f.valid_from <= e.prediction_ts
         AND (f.valid_to > e.prediction_ts OR f.valid_to IS NULL)
        WHERE f.valid_from > e.prediction_ts""",
}

with engine.connect() as conn:
    n_hist = conn.execute(text("SELECT COUNT(*) FROM hw2_customer_features_offline")).scalar()
    n_events = conn.execute(text("SELECT COUNT(*) FROM hw2_training_events")).scalar()
    for name, q in checks.items():
        n = conn.execute(text(q)).scalar()
        print(f"{name:35s} -> {n}")
        assert n == 0, f"Перевірка не пройдена: {name}"

assert n_hist >= 10, "Потрібно щонайменше 10 історичних рядків"
print(f"\\nІсторичних рядків: {n_hist}, training events: {n_events}. Усі перевірки пройдено.")
''')

md("""
### 4.8. Чому простий JOIN лише за `customer_id` неприпустимий

Нижче — порівняння «наївного» JOIN і AS-OF JOIN. Наївний JOIN приєднує до кожної події **всі** версії
ознак клієнта, зокрема ті, що з'явилися після `prediction_ts`.
""")
sql("""
WITH naive AS (
    SELECT e.event_id, e.prediction_ts, f.valid_from
    FROM hw2_training_events AS e
    JOIN hw2_customer_features_offline AS f
      ON f.customer_id = e.customer_id
),
as_of AS (
    SELECT e.event_id
    FROM hw2_training_events AS e
    LEFT JOIN hw2_customer_features_offline AS f
           ON f.customer_id = e.customer_id
          AND f.valid_from <= e.prediction_ts
          AND (f.valid_to > e.prediction_ts OR f.valid_to IS NULL)
)
SELECT
    (SELECT COUNT(*) FROM hw2_training_events)                    AS training_events,
    (SELECT COUNT(*) FROM as_of)                                  AS rows_as_of_join,
    (SELECT COUNT(*) FROM naive)                                  AS rows_naive_join,
    (SELECT COUNT(*) FROM naive WHERE valid_from > prediction_ts) AS naive_rows_from_future;
""")
md("""
**Висновок з таблиці вище.** AS-OF JOIN дає рівно по одному рядку на training event. Наївний JOIN повертає
значно більше рядків, і частина з них містить ознаки, обчислені **після** моменту прогнозу:

- **дублікати training examples**: одна подія потрапляє в датасет кілька разів з різними ознаками, що спотворює ваги й метрики;
- **data leakage**: для події клієнта 42 від `2024-12-10` у датасет потрапила б і версія від `2025-01-15`
  з `orders_30d = 0` та `days_since_last_order = 32`. Це фактично «підглядання» у майбутню неактивність, яка
  прямо корелює з міткою `churn_in_horizon`;
- **завищена якість моделі**: на навчанні й валідації модель «бачить» майбутнє і показує високі метрики, але в продакшені
  таких ознак на момент прогнозу немає, тож якість різко падає.

### 4.9. Пояснення умов AS-OF

1. **`valid_from <= prediction_ts`** — беремо лише версії, які вже існували на момент прогнозу.
   Версія, що почалася пізніше, містить інформацію з майбутнього.
2. **`valid_to > prediction_ts OR valid_to IS NULL`** — версія ще не була замінена на момент прогнозу. Строга
   нерівність виключає версію, яка закінчилася рівно в `prediction_ts`. `valid_to IS NULL` означає поточну (відкриту)
   версію; без цієї умови `NULL > ts` дає `NULL`, і поточна версія ніколи б не потрапляла в результат.
3. **Напіввідкриті інтервали `[valid_from, valid_to)`** — сусідні версії стикуються без перекриття й без «дір»:
   `valid_to` попередньої = `valid_from` наступної. Будь-який момент часу, зокрема точна межа
   (`2025-01-15 00:00:00+00` у запиті №2), належить рівно одній версії. Із закритими інтервалами `[a, b]` межа
   належала б двом версіям і створювала б дублікати.
4. **Без часового фільтра** до події потрапили б усі пізніші версії: майбутні значення `orders_30d`, `spend_30d`,
   `days_since_last_order`, які вже відображають поведінку клієнта в горизонті мітки, тобто саму відповідь (churn).
""")

# ---------------------------------------------------------------- online
md("""
## 5. Online-рівень: матеріалізація з offline-джерела

Online-таблиця оновлюється батч-джобою: беремо поточну версію (`valid_to IS NULL`), приєднуємо атрибути клієнта
й виконуємо UPSERT. Умова `WHERE ... feature_ts <= EXCLUDED.feature_ts` не дає перезаписати свіжіші дані старішими,
тому повторний запуск ідемпотентний.
""")
sql("""
INSERT INTO hw2_customer_features_online
    (customer_id, country, signup_date,
     orders_30d, spend_30d, days_since_last_order, distinct_categories_90d,
     feature_ts, updated_at)
SELECT f.customer_id, c.country, c.signup_date,
       f.orders_30d, f.spend_30d, f.days_since_last_order, f.distinct_categories_90d,
       f.valid_from, CURRENT_TIMESTAMP
FROM hw2_customer_features_offline AS f
JOIN hw2_customers AS c ON c.customer_id = f.customer_id
WHERE f.valid_to IS NULL
ON CONFLICT (customer_id) DO UPDATE
SET country                 = EXCLUDED.country,
    signup_date             = EXCLUDED.signup_date,
    orders_30d              = EXCLUDED.orders_30d,
    spend_30d               = EXCLUDED.spend_30d,
    days_since_last_order   = EXCLUDED.days_since_last_order,
    distinct_categories_90d = EXCLUDED.distinct_categories_90d,
    feature_ts              = EXCLUDED.feature_ts,
    updated_at              = EXCLUDED.updated_at
WHERE hw2_customer_features_online.feature_ts <= EXCLUDED.feature_ts;
""")
md("Online lookup під час інференсу — один рядок за PK, без JOIN і часових фільтрів:")
sql("""
SELECT customer_id, country, orders_30d, spend_30d, days_since_last_order,
       distinct_categories_90d, feature_ts
FROM hw2_customer_features_online
WHERE customer_id = 42;
""")
md("Контроль узгодженості online ↔ offline (має повернути 0 розбіжностей):")
sql("""
SELECT COUNT(*) AS mismatches
FROM hw2_customer_features_offline AS f
LEFT JOIN hw2_customer_features_online AS o
       ON o.customer_id = f.customer_id
WHERE f.valid_to IS NULL
  AND (o.customer_id IS NULL
       OR o.feature_ts <> f.valid_from
       OR o.orders_30d <> f.orders_30d
       OR o.spend_30d <> f.spend_30d);
""")

# ---------------------------------------------------------------- reflection
md("""
## Завдання 5. Reflection

**1. Що було найскладнішим.** Найбільше уваги потребувала point-in-time correctness. Треба було зафіксувати семантику
напіввідкритих інтервалів і гарантувати, що версії одного клієнта не перекриваються. У `pgserver` немає розширення
`btree_gist`, тому обмеження `EXCLUDE USING gist` недоступне. Натомість я поєднала temporal `CHECK`, частковий унікальний
індекс на поточну версію, зміну версії в одній транзакції та перевірочні запити з `assert`. Ще одна тонкість —
кардинальності: правило «замовлення має хоча б одну позицію» (1..N) не виражається через FK і залишається бізнес-правилом.

**2. Проєктні компроміси.** Бізнесові таблиці та offline-історію я нормалізувала до 3НФ. Offline-рівень читається
великими пакетами під час навчання, тому JOIN там прийнятні, а головне — коректність і відсутність дублювання. Online-рівень
навмисно денормалізований: один рядок поточних ознак плюс копії атрибутів клієнта, бо його читають точково за
`customer_id` з вимогою низької latency. Ціна цього рішення — потреба регулярно синхронізувати online з offline і контролювати розбіжності.

**3. Online-рівень при дуже великому навантаженні.** Я залишила б один денормалізований, попередньо матеріалізований рядок
на `customer_id`, але винесла б його в key-value сховище (Redis, DynamoDB) або поставила б кеш перед PostgreSQL.
Масштабувала б горизонтально (шардинг за `customer_id`, read-репліки), а батч-оновлення доповнила б потоковим. Свіжість
контролювала б через `feature_ts`, TTL і моніторинг затримки.

**4. Ризики еволюції схеми за шість місяців.** Перейменування чи видалення ознаки ламає запити й старі моделі. Зміна типу
(`INTEGER → NUMERIC`) або семантики (наприклад, `orders_30d` почне враховувати скасовані замовлення) небезпечна тим, що
назва лишається тією самою, а модель тихо деградує. Щоб цього уникнути, варто версіонувати ознаки (`orders_30d_v2`),
додавати колонки замість змінювати їх, проводити міграції через скрипти в git і вести feature registry з описом і
власником. Для кожної моделі слід зберігати перелік ознак і версію схеми, щоб старі моделі можна було підтримувати до виведення з експлуатації.
""")

md("""
## Чек-лист

- [x] ER-діаграма з PK/FK, кардинальностями, offline- та online-рівнями; N:M через bridge-таблицю `hw2_order_items`
- [x] DDL виконується в PostgreSQL 16: PK, FK, NOT NULL, доменні CHECK, temporal CHECK, індекси
- [x] Історична feature-таблиця: 13 temporal-рядків для 4 клієнтів, 4 версії для `customer_id = 42`
- [x] Три AS-OF SELECT + AS-OF JOIN training events за `prediction_ts`
- [x] Перевірка перекривних інтервалів повертає 0 рядків
- [x] Notebook виконується від початку до кінця (Restart & Run All)
""")

nb = nbf.v4.new_notebook(cells=cells)
nb.metadata = {
    "kernelspec": {"name": "python3", "display_name": "Python 3", "language": "python"},
    "language_info": {"name": "python"},
    "colab": {"provenance": []},
}
out = ROOT / "notebooks/hw2_ecommerce_churn.ipynb"
out.parent.mkdir(parents=True, exist_ok=True)
nbf.write(nb, out)
print("wrote", out)
