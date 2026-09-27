"""Генерує ER-діаграму (Graphviz DOT) для схеми hw2_* (E-commerce churn)."""

TABLES = {
    "hw2_customers": ("biz", [
        ("PK", "customer_id", "BIGINT"),
        ("", "email", "VARCHAR(255) UQ NN"),
        ("", "signup_date", "DATE NN"),
        ("", "country", "VARCHAR(2) NN CHECK"),
        ("", "marketing_opt_in", "BOOLEAN NN"),
    ]),
    "hw2_orders": ("biz", [
        ("PK", "order_id", "BIGINT"),
        ("FK", "customer_id", "BIGINT NN"),
        ("", "order_ts", "TIMESTAMPTZ NN"),
        ("", "status", "VARCHAR(20) NN CHECK"),
    ]),
    "hw2_order_items": ("bridge", [
        ("PK,FK", "order_id", "BIGINT"),
        ("PK,FK", "product_id", "BIGINT"),
        ("", "quantity", "INTEGER NN CHECK &gt; 0"),
        ("", "unit_price", "NUMERIC(10,2) NN"),
    ]),
    "hw2_products": ("biz", [
        ("PK", "product_id", "BIGINT"),
        ("FK", "category_id", "INTEGER NN"),
        ("", "name", "TEXT NN"),
        ("", "list_price", "NUMERIC(10,2) NN"),
        ("", "is_active", "BOOLEAN NN"),
    ]),
    "hw2_categories": ("biz", [
        ("PK", "category_id", "INTEGER"),
        ("", "name", "VARCHAR(100) UQ NN"),
    ]),
    "hw2_customer_features_offline": ("offline", [
        ("PK,FK", "customer_id", "BIGINT"),
        ("PK", "valid_from", "TIMESTAMPTZ"),
        ("", "valid_to", "TIMESTAMPTZ NULL"),
        ("", "orders_30d", "INTEGER NN"),
        ("", "spend_30d", "NUMERIC(12,2) NN"),
        ("", "days_since_last_order", "INTEGER NULL"),
        ("", "distinct_categories_90d", "INTEGER NN"),
    ]),
    "hw2_training_events": ("offline", [
        ("PK", "event_id", "BIGINT IDENTITY"),
        ("FK", "customer_id", "BIGINT NN"),
        ("", "prediction_ts", "TIMESTAMPTZ NN"),
        ("", "label_horizon_end", "TIMESTAMPTZ NN"),
        ("", "churn_in_horizon", "BOOLEAN NN (target)"),
    ]),
    "hw2_customer_features_online": ("online", [
        ("PK,FK", "customer_id", "BIGINT"),
        ("", "country", "VARCHAR(2) NN (denorm)"),
        ("", "signup_date", "DATE NN (denorm)"),
        ("", "orders_30d", "INTEGER NN"),
        ("", "spend_30d", "NUMERIC(12,2) NN"),
        ("", "days_since_last_order", "INTEGER NULL"),
        ("", "distinct_categories_90d", "INTEGER NN"),
        ("", "feature_ts", "TIMESTAMPTZ NN"),
        ("", "updated_at", "TIMESTAMPTZ NN"),
    ]),
}

COLORS = {"biz": "#cfe2ff", "bridge": "#e2d9f3", "offline": "#ffe8b3", "online": "#c9ecd4"}

# (parent, child, parent_card, child_card, label)
RELS = [
    ("hw2_customers", "hw2_orders", "1..1", "0..N", "places"),
    ("hw2_orders", "hw2_order_items", "1..1", "1..N", "contains"),
    ("hw2_products", "hw2_order_items", "1..1", "0..N", "sold in"),
    ("hw2_categories", "hw2_products", "1..1", "0..N", "groups"),
    ("hw2_customers", "hw2_customer_features_offline", "1..1", "0..N", "history of"),
    ("hw2_customers", "hw2_training_events", "1..1", "0..N", "labelled at"),
    ("hw2_customers", "hw2_customer_features_online", "1..1", "0..1", "current row"),
]
HEAD = {"0..N": "crowodot", "1..N": "crowtee", "0..1": "teeodot", "1..1": "teetee"}


def node(name, layer, cols):
    rows = "".join(
        f'<tr><td align="left">{"<b>" + k + "</b>" if k else " "}</td>'
        f'<td align="left">{"<u>" + c + "</u>" if "PK" in k else c}</td>'
        f'<td align="left"><font color="#555555">{t}</font></td></tr>'
        for k, c, t in cols
    )
    return (f'"{name}" [label=<<table border="0" cellborder="1" cellspacing="0" cellpadding="4">'
            f'<tr><td colspan="3" bgcolor="{COLORS[layer]}"><b>{name}</b></td></tr>{rows}</table>>];')


def cluster(cid, title, color, names):
    body = "\n    ".join(node(n, TABLES[n][0], TABLES[n][1]) for n in names)
    return (f'subgraph cluster_{cid} {{\n    label=<<b>{title}</b>>; style="rounded,dashed"; '
            f'color="{color}"; fontsize=16;\n    {body}\n  }}')


dot = ['digraph ER {',
       '  graph [rankdir=LR, fontname="Helvetica", nodesep=0.5, ranksep=1.3, pad=0.3, bgcolor="white", '
       'label=<<b>E-commerce churn: ER-модель та feature store</b><br/>'
       '<font point-size="11">PK — первинний ключ, FK — зовнішній ключ, NN — NOT NULL, UQ — UNIQUE. '
       'Кардинальність min..max: min 0 — зв\'язок необов\'язковий, min 1 — обов\'язковий.</font>>, '
       'labelloc=t, fontsize=18];',
       '  node [shape=plain, fontname="Helvetica", fontsize=11];',
       '  edge [fontname="Helvetica", fontsize=10, dir=both, color="#333333"];',
       cluster("biz", "Бізнесові сутності (OLTP, 3НФ)", "#3d6fd6",
               ["hw2_categories", "hw2_products", "hw2_order_items", "hw2_orders", "hw2_customers"]),
       cluster("off", "Offline-рівень feature store (історія, навчання)", "#c98a00",
               ["hw2_customer_features_offline", "hw2_training_events"]),
       cluster("on", "Online-рівень feature store (serving)", "#2e8b57",
               ["hw2_customer_features_online"]),
       ]
PORTS = {"hw2_customer_features_offline": "s", "hw2_customer_features_online": "sw",
         "hw2_training_events": "se"}
for p, c, pc, cc, lab in RELS:
    port = f', tailport="{PORTS[c]}"' if p == "hw2_customers" and c in PORTS else ""
    dot.append(f'  "{p}" -> "{c}" [arrowtail={HEAD[pc]}, arrowhead={HEAD[cc]}, '
               f'label="{lab}", taillabel="{pc}", headlabel="{cc}", labeldistance=2.2{port}];')
dot.append('  "hw2_training_events" -> "hw2_customer_features_offline" [style=dashed, dir=forward, '
           'arrowhead=vee, color="#c98a00", fontcolor="#8a5a00", '
           'label=<<b>AS-OF JOIN</b> (логічний, без FK):<br/>valid_from &lt;= prediction_ts &lt; valid_to>];')
dot.append('  "hw2_customer_features_offline" -> "hw2_customer_features_online" [style=dashed, dir=forward, '
           'arrowhead=vee, color="#2e8b57", fontcolor="#1d5e39", '
           'label=<<b>materialize</b>: версія з valid_to IS NULL<br/>(UPSERT за customer_id)>];')
dot.append("}")

if __name__ == "__main__":
    import pathlib
    out = pathlib.Path(__file__).with_name("er_diagram.dot")
    out.write_text("\n".join(dot), encoding="utf-8")
    print("wrote", out)
