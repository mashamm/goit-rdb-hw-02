INSERT INTO hw2_customers
    (customer_id, email, signup_date, country, marketing_opt_in)
VALUES
    (1,  'anna@example.com',  DATE '2024-01-10', 'UA', TRUE),
    (2,  'piotr@example.com', DATE '2024-02-20', 'PL', FALSE),
    (3,  'olena@example.com', DATE '2024-05-05', 'UA', TRUE),
    (42, 'max@example.com',   DATE '2024-03-15', 'DE', FALSE);

INSERT INTO hw2_categories (category_id, name)
VALUES
    (1, 'Electronics'),
    (2, 'Books'),
    (3, 'Home');

INSERT INTO hw2_products (product_id, category_id, name, list_price, is_active)
VALUES
    (101, 1, 'Wireless headphones', 79.99, TRUE),
    (102, 1, 'USB-C charger',       25.00, TRUE),
    (201, 2, 'SQL for Data Science', 39.90, TRUE),
    (202, 2, 'Novel "Kobzar"',      15.50, TRUE),
    (301, 3, 'Desk lamp',           49.00, FALSE);

INSERT INTO hw2_orders (order_id, customer_id, order_ts, status)
VALUES
    (1001, 42, TIMESTAMPTZ '2024-09-19 14:20:00+00', 'delivered'),
    (1002, 42, TIMESTAMPTZ '2024-10-27 09:05:00+00', 'delivered'),
    (1003, 42, TIMESTAMPTZ '2024-12-14 18:40:00+00', 'delivered'),
    (1004, 1,  TIMESTAMPTZ '2024-11-13 11:00:00+00', 'delivered'),
    (1005, 1,  TIMESTAMPTZ '2024-12-23 16:30:00+00', 'shipped'),
    (1006, 2,  TIMESTAMPTZ '2024-10-11 08:15:00+00', 'delivered'),
    (1007, 3,  TIMESTAMPTZ '2024-10-26 19:45:00+00', 'delivered'),
    (1008, 3,  TIMESTAMPTZ '2024-12-17 12:10:00+00', 'returned');

INSERT INTO hw2_order_items (order_id, product_id, quantity, unit_price)
VALUES
    (1001, 101, 1, 79.99),
    (1002, 102, 1, 25.00),
    (1002, 202, 1, 15.50),
    (1003, 201, 2, 39.90),
    (1003, 301, 1, 45.00),
    (1004, 101, 1, 74.99),
    (1004, 201, 1, 39.90),
    (1005, 202, 3, 15.50),
    (1006, 202, 1, 15.50),
    (1007, 201, 1, 39.90),
    (1007, 301, 1, 49.00),
    (1008, 102, 2, 25.00);

-- Історія ознак: 12 temporal-версій для 4 клієнтів.
-- Для customer_id = 42 — 4 послідовні версії, для 1 і 2 — по 3, для 3 — 2.
-- Кожна наступна версія починається рівно там, де закінчується попередня.
INSERT INTO hw2_customer_features_offline
    (customer_id, valid_from, valid_to,
     orders_30d, spend_30d, days_since_last_order, distinct_categories_90d)
VALUES
    (42, TIMESTAMPTZ '2024-10-01 00:00:00+00', TIMESTAMPTZ '2024-11-01 00:00:00+00', 1,  79.99, 12, 1),
    (42, TIMESTAMPTZ '2024-11-01 00:00:00+00', TIMESTAMPTZ '2024-12-15 00:00:00+00', 2, 100.00,  5, 2),
    (42, TIMESTAMPTZ '2024-12-15 00:00:00+00', TIMESTAMPTZ '2025-01-15 00:00:00+00', 5, 200.00,  1, 3),
    (42, TIMESTAMPTZ '2025-01-15 00:00:00+00', NULL,                                  0,   0.00, 32, 2),

    (1,  TIMESTAMPTZ '2024-10-01 00:00:00+00', TIMESTAMPTZ '2024-11-15 00:00:00+00', 3, 120.50,  4, 2),
    (1,  TIMESTAMPTZ '2024-11-15 00:00:00+00', TIMESTAMPTZ '2025-01-01 00:00:00+00', 4, 180.00,  2, 3),
    (1,  TIMESTAMPTZ '2025-01-01 00:00:00+00', NULL,                                  2,  95.00,  9, 2),

    (2,  TIMESTAMPTZ '2024-10-15 00:00:00+00', TIMESTAMPTZ '2024-12-01 00:00:00+00', 1,  15.50, 20, 1),
    (2,  TIMESTAMPTZ '2024-12-01 00:00:00+00', TIMESTAMPTZ '2025-01-10 00:00:00+00', 0,   0.00, 50, 1),
    (2,  TIMESTAMPTZ '2025-01-10 00:00:00+00', NULL,                                  0,   0.00, 90, 0),

    (3,  TIMESTAMPTZ '2024-11-01 00:00:00+00', TIMESTAMPTZ '2024-12-20 00:00:00+00', 2,  88.90,  6, 2),
    (3,  TIMESTAMPTZ '2024-12-20 00:00:00+00', NULL,                                  3, 140.40,  3, 3);

-- Training events: момент прогнозу, горизонт 30 днів і мітка churn.
INSERT INTO hw2_training_events
    (customer_id, prediction_ts, label_horizon_end, churn_in_horizon)
VALUES
    (42, TIMESTAMPTZ '2024-12-10 10:00:00+00', TIMESTAMPTZ '2025-01-09 10:00:00+00', FALSE),
    (42, TIMESTAMPTZ '2024-12-20 10:00:00+00', TIMESTAMPTZ '2025-01-19 10:00:00+00', TRUE),
    (42, TIMESTAMPTZ '2025-01-15 00:00:00+00', TIMESTAMPTZ '2025-02-14 00:00:00+00', TRUE),
    (1,  TIMESTAMPTZ '2024-12-01 12:00:00+00', TIMESTAMPTZ '2024-12-31 12:00:00+00', FALSE),
    (1,  TIMESTAMPTZ '2025-01-05 09:00:00+00', TIMESTAMPTZ '2025-02-04 09:00:00+00', FALSE),
    (2,  TIMESTAMPTZ '2024-11-20 08:00:00+00', TIMESTAMPTZ '2024-12-20 08:00:00+00', FALSE),
    (2,  TIMESTAMPTZ '2025-01-05 08:00:00+00', TIMESTAMPTZ '2025-02-04 08:00:00+00', TRUE),
    (3,  TIMESTAMPTZ '2024-10-20 00:00:00+00', TIMESTAMPTZ '2024-11-19 00:00:00+00', FALSE),
    (3,  TIMESTAMPTZ '2024-12-01 18:00:00+00', TIMESTAMPTZ '2024-12-31 18:00:00+00', FALSE);
