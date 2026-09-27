# goit-rdb-hw-02 — ER-модель і feature store для E-commerce churn

**Автор:** Samoilenko Mariia

ML-сценарій: прогноз відтоку клієнтів інтернет-магазину (`churn_in_horizon` — жодного оплаченого замовлення протягом 30 днів після `prediction_ts`).

## Структура

| Шлях | Опис |
|---|---|
| `notebooks/hw2_ecommerce_churn.ipynb` | Основний notebook: ER, DDL, нормалізація, point-in-time correctness, online-рівень, reflection |
| `er/er_diagram.png`, `er/er_diagram.svg` | ER-діаграма |
| `er/er_diagram.dot` | ER-діаграма як текстовий DSL (Graphviz) |
| `er/make_er.py` | Генератор DSL діаграми |
| `sql/01_ddl.sql` | DDL для PostgreSQL 16 (таблиці `hw2_*`) |
| `sql/02_data.sql` | Тестові дані |
| `tools/build_notebook.py` | Збирання notebook із SQL-файлів |

## Схема

- **Бізнесові сутності (3НФ):** `hw2_customers`, `hw2_orders`, `hw2_products`, `hw2_categories`, bridge-таблиця N:M `hw2_order_items`.
- **Offline-рівень:** `hw2_customer_features_offline` (історія версій ознак, інтервали `[valid_from, valid_to)`), `hw2_training_events` (`prediction_ts`, `churn_in_horizon`).
- **Online-рівень:** `hw2_customer_features_online` — один денормалізований рядок поточних ознак на клієнта.

## Запуск

Відкрийте notebook у Google Colab і виконайте **Runtime → Restart session and run all**.
PostgreSQL 16 піднімається всередині notebook через `pgserver`, SQL-клітинки виконуються через `jupysql` (`%%sql`).
