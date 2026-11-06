"""应用 SQLite 迁移：python -m scripts.init_sqlite"""

from app.storage import sqlite

if __name__ == "__main__":
    applied = sqlite.migrate()
    print(f"SQLite 迁移完成，本次执行: {applied or '无（已是最新）'}；当前: {sqlite.ping()}")
