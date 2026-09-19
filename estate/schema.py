"""小胖庄园 SQLite 表结构。"""


def init_estate(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS estate_profiles (
            username TEXT PRIMARY KEY COLLATE NOCASE,
            level INTEGER NOT NULL DEFAULT 1 CHECK(level >= 1),
            xp INTEGER NOT NULL DEFAULT 0 CHECK(xp >= 0),
            warehouse_level INTEGER NOT NULL DEFAULT 1 CHECK(warehouse_level >= 1),
            plot_count INTEGER NOT NULL DEFAULT 0 CHECK(plot_count >= 0),
            version INTEGER NOT NULL DEFAULT 1 CHECK(version >= 1),
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS estate_plots (
            username TEXT NOT NULL COLLATE NOCASE,
            plot_index INTEGER NOT NULL CHECK(plot_index >= 0),
            land_level INTEGER NOT NULL DEFAULT 1 CHECK(land_level >= 1),
            crop_id TEXT,
            planted_at INTEGER,
            ready_at INTEGER,
            PRIMARY KEY (username, plot_index),
            CHECK (
                (crop_id IS NULL AND planted_at IS NULL AND ready_at IS NULL) OR
                (crop_id IS NOT NULL AND planted_at IS NOT NULL AND ready_at IS NOT NULL
                 AND ready_at >= planted_at)
            )
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS estate_inventory (
            username TEXT NOT NULL COLLATE NOCASE,
            item_id TEXT NOT NULL,
            quantity INTEGER NOT NULL CHECK(quantity > 0),
            PRIMARY KEY (username, item_id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS estate_actions (
            username TEXT NOT NULL COLLATE NOCASE,
            request_id TEXT NOT NULL,
            action_type TEXT NOT NULL,
            request_hash TEXT NOT NULL,
            result_json TEXT NOT NULL,
            created_at INTEGER NOT NULL,
            PRIMARY KEY (username, request_id)
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_estate_actions_created "
        "ON estate_actions(username, created_at)"
    )
