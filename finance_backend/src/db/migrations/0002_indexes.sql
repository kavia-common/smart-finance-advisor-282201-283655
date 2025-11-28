-- 0002_indexes.sql
-- Helpful indexes for common query patterns

-- Users: quick lookup by email
CREATE INDEX IF NOT EXISTS idx_users_email ON users (email);

-- Transactions: user/date and user/category
CREATE INDEX IF NOT EXISTS idx_transactions_user_date ON transactions (user_id, date);
CREATE INDEX IF NOT EXISTS idx_transactions_user_category ON transactions (user_id, category);

-- Budgets: user/month
CREATE INDEX IF NOT EXISTS idx_budgets_user_month ON budgets (user_id, month);

-- Goals: user and time-based ordering
CREATE INDEX IF NOT EXISTS idx_goals_user_created_at ON goals (user_id, created_at);
