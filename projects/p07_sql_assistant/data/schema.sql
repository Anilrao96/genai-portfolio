CREATE TABLE customers (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    region TEXT NOT NULL CHECK (region IN ('North','South','East','West')),
    segment TEXT NOT NULL CHECK (segment IN ('startup','growth','enterprise'))
);
CREATE TABLE orders (
    id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES customers(id),
    ordered_at TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('completed','refunded','cancelled')),
    total_cents INTEGER NOT NULL CHECK (total_cents >= 0)
);
