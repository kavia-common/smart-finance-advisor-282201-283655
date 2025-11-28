-- 0002_indexes.sql
-- Helpful indexes for common query patterns

-- Users: quick lookup by email
CREATE INDEX IF NOT EXISTS idx_users_email ON users (email);

-- Income: user and month/year queries
CREATE INDEX IF NOT EXISTS idx_income_user_month_year ON income (user_id, year, month);

-- Expenses: user, month/year, category queries
CREATE INDEX IF NOT EXISTS idx_expenses_user_month_year_cat ON expenses (user_id, year, month, category);

-- Goals: user and time-based ordering
CREATE INDEX IF NOT EXISTS idx_goals_user_created_at ON goals (user_id, created_at);
