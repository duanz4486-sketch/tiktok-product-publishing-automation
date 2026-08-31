PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  username TEXT NOT NULL UNIQUE,
  role TEXT NOT NULL DEFAULT 'operator',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS batches (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  batch_name TEXT NOT NULL,
  title_file TEXT NOT NULL,
  image_prefix TEXT NOT NULL,
  shop_id INTEGER NOT NULL,
  template_detail_id INTEGER NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  total_count INTEGER NOT NULL DEFAULT 0,
  success_count INTEGER NOT NULL DEFAULT 0,
  failed_count INTEGER NOT NULL DEFAULT 0,
  log_path TEXT,
  created_by INTEGER,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (created_by) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS products (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  batch_id INTEGER NOT NULL,
  seq INTEGER NOT NULL,
  title TEXT NOT NULL,
  image_urls_json TEXT NOT NULL DEFAULT '[]',
  common_collect_box_detail_id INTEGER,
  tiktok_detail_id INTEGER,
  shop_id INTEGER NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  error_message TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (batch_id, seq),
  FOREIGN KEY (batch_id) REFERENCES batches(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS task_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  batch_id INTEGER NOT NULL,
  product_id INTEGER,
  level TEXT NOT NULL DEFAULT 'info',
  message TEXT NOT NULL,
  payload_json TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (batch_id) REFERENCES batches(id) ON DELETE CASCADE,
  FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_batches_status ON batches(status);
CREATE INDEX IF NOT EXISTS idx_products_batch_status ON products(batch_id, status);
CREATE INDEX IF NOT EXISTS idx_products_tiktok_detail_id ON products(tiktok_detail_id);
