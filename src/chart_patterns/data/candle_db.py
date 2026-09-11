import base64
import hashlib
import json
import os
import sqlite3
import threading
from datetime import date, datetime

import numpy as np
import pandas as pd

from ..custom_logger import logger
from ..paths import PROJECT_ROOT

MEMORY_DB_CONN = None
MEMORY_DB_PATH = None
MEMORY_DB_LOCK = threading.RLock()
_THREAD_LOCAL = threading.local()
_MEMORY_INITIALIZED = set()

DB_DIR = os.path.join(PROJECT_ROOT, "data")
os.makedirs(DB_DIR, exist_ok=True)
DEFAULT_DB_PATH = os.path.join(DB_DIR, "candles.db")

CORE_COLUMNS = ["open", "high", "low", "close", "volume"]


def _copy_disk_db_to_memory(memory_conn, disk_path):
    if not os.path.exists(disk_path):
        return
    disk_conn = sqlite3.connect(disk_path, detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES)
    try:
        disk_conn.backup(memory_conn)
    finally:
        disk_conn.close()


def _memory_db_uri(db_path):
    normalized_path = os.path.abspath(db_path or DEFAULT_DB_PATH)
    digest = hashlib.md5(normalized_path.encode("utf-8")).hexdigest()
    return f"file:mem_{digest}?mode=memory&cache=shared"


def _get_connection(db_path=None, memory=False):
    global MEMORY_DB_CONN, MEMORY_DB_PATH
    if memory:
        path = db_path or DEFAULT_DB_PATH
        uri = _memory_db_uri(path)
        conn = getattr(_THREAD_LOCAL, "memory_db_conn", None)
        current_path = getattr(_THREAD_LOCAL, "memory_db_path", None)
        if conn is None or current_path != path:
            conn = sqlite3.connect(
                uri,
                uri=True,
                detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES,
                check_same_thread=False,
            )
            conn.row_factory = sqlite3.Row
            _THREAD_LOCAL.memory_db_conn = conn
            _THREAD_LOCAL.memory_db_path = path
            with MEMORY_DB_LOCK:
                if path not in _MEMORY_INITIALIZED:
                    if os.path.exists(path):
                        disk_conn = sqlite3.connect(path, detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES)
                        try:
                            disk_conn.backup(conn)
                        finally:
                            disk_conn.close()
                    _MEMORY_INITIALIZED.add(path)
            MEMORY_DB_CONN = conn
            MEMORY_DB_PATH = path
        return conn, False

    path = db_path or DEFAULT_DB_PATH
    conn = sqlite3.connect(path, detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES)
    conn.row_factory = sqlite3.Row
    return conn, True


def initialize_database(db_path=None, memory=False):
    db_path = db_path or DEFAULT_DB_PATH
    if not memory:
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn, should_close = _get_connection(db_path, memory=memory)
    try:
        if memory:
            with MEMORY_DB_LOCK:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS candles (
                        id INTEGER PRIMARY KEY,
                        symbol TEXT NOT NULL,
                        timestamp TEXT NOT NULL,
                        date TEXT NOT NULL,
                        open REAL,
                        high REAL,
                        low REAL,
                        close REAL,
                        volume REAL,
                        extra TEXT,
                        UNIQUE(symbol, timestamp)
                    )
                    """
                )
                cursor.execute(
                    "CREATE INDEX IF NOT EXISTS idx_candles_symbol_timestamp ON candles(symbol, timestamp)"
                )
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_candles_date ON candles(date)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_candles_symbol ON candles(symbol)")
                conn.commit()
        else:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS candles (
                    id INTEGER PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    date TEXT NOT NULL,
                    open REAL,
                    high REAL,
                    low REAL,
                    close REAL,
                    volume REAL,
                    extra TEXT,
                    UNIQUE(symbol, timestamp)
                )
                """
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_candles_symbol_timestamp ON candles(symbol, timestamp)"
            )
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_candles_date ON candles(date)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_candles_symbol ON candles(symbol)")
            conn.commit()
    finally:
        if should_close:
            conn.close()


def _normalize_timestamp(ts):
    if ts is None:
        return None
    if isinstance(ts, datetime):
        return ts.isoformat()
    if isinstance(ts, pd.Timestamp):
        return ts.to_pydatetime().isoformat()
    if isinstance(ts, str):
        return ts
    return str(ts)


def _normalize_date(ts):
    if ts is None:
        return None
    if isinstance(ts, datetime):
        return ts.date().isoformat()
    if isinstance(ts, pd.Timestamp):
        return ts.date().isoformat()
    if isinstance(ts, str):
        if "T" in ts:
            return ts.split("T")[0]
        return ts
    return str(ts)


def _serialize_extra_value(value):
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8")
        except UnicodeDecodeError:
            return {"__bytes__": True, "encoding": "base64", "data": base64.b64encode(value).decode("ascii")}
    if isinstance(value, bytearray):
        return _serialize_extra_value(bytes(value))
    if isinstance(value, (np.integer, np.floating, np.bool_)):
        return value.item()
    if isinstance(value, (datetime, date, pd.Timestamp)):
        return str(value)
    if pd.isna(value):
        return None
    return value


def _normalize_core_value(value):
    if isinstance(value, (bytes, bytearray)):
        try:
            return float(int.from_bytes(bytes(value), byteorder="little", signed=False))
        except Exception:
            try:
                return float(value.decode("utf-8"))
            except Exception:
                return None
    if isinstance(value, (np.integer, np.floating, np.bool_)):
        return float(value.item())
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    if pd.isna(value):
        return None
    return value


def _make_extra_json(row):
    extra = {}
    for column, value in row.items():
        if column in CORE_COLUMNS:
            continue
        if pd.isna(value):
            continue
        serialized = _serialize_extra_value(value)
        if serialized is not None:
            extra[column] = serialized
    if not extra:
        return None
    try:
        return json.dumps(extra, ensure_ascii=False)
    except Exception:
        logger.exception("Failed to serialize extra columns to JSON")
        safe_extra = {}
        for col, value in extra.items():
            try:
                json.dumps(value)
                safe_extra[col] = value
            except Exception:
                safe_extra[col] = str(value)
        return json.dumps(safe_extra, ensure_ascii=False)


def insert_candle_df(df, symbol, db_path=None, memory=False):
    if df is None:
        logger.warning(f"No data to insert for {symbol}: data is None.")
        return 0

    if not isinstance(df, pd.DataFrame):
        logger.warning(f"No data to insert for {symbol}: expected pandas DataFrame, got {type(df).__name__}.")
        return 0

    if df.empty:
        logger.warning(f"No data to insert for {symbol}: DataFrame is empty.")
        return 0

    initialize_database(db_path, memory=memory)

    data_rows = []
    df = df.copy()
    if df.index.name is None or df.index.name == "":
        if "timestamp" in df.columns:
            df = df.set_index("timestamp")
        elif "date" in df.columns:
            df = df.set_index("date")

    for timestamp, row in df.iterrows():
        timestamp_str = _normalize_timestamp(timestamp)
        if timestamp_str is None:
            continue

        date_str = _normalize_date(timestamp)
        row_data = {
            key.lower(): row.get(key)
            for key in df.columns
        }
        open_val = _normalize_core_value(row_data.get("open"))
        high_val = _normalize_core_value(row_data.get("high"))
        low_val = _normalize_core_value(row_data.get("low"))
        close_val = _normalize_core_value(row_data.get("close"))
        volume_val = _normalize_core_value(row_data.get("volume"))
        extra_json = _make_extra_json(row_data)

        data_rows.append(
            (
                symbol,
                timestamp_str,
                date_str,
                open_val,
                high_val,
                low_val,
                close_val,
                volume_val,
                extra_json,
            )
        )

    if not data_rows:
        logger.warning(f"No candle rows were prepared for {symbol}.")
        return 0

    conn, should_close = _get_connection(db_path, memory=memory)
    try:
        if memory:
            with MEMORY_DB_LOCK:
                cursor = conn.cursor()
                cursor.executemany(
                    "INSERT OR REPLACE INTO candles (symbol, timestamp, date, open, high, low, close, volume, extra) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    data_rows,
                )
                conn.commit()
        else:
            cursor = conn.cursor()
            cursor.executemany(
                "INSERT OR REPLACE INTO candles (symbol, timestamp, date, open, high, low, close, volume, extra) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                data_rows,
            )
            conn.commit()
        inserted = cursor.rowcount
        logger.info(f"Inserted/updated {inserted} rows for {symbol} into SQLite database.")
        return inserted
    finally:
        if should_close:
            conn.close()


def _read_query(sql, params=None, db_path=None, memory=False):
    conn, should_close = _get_connection(db_path, memory=memory)
    try:
        if memory:
            with MEMORY_DB_LOCK:
                df = pd.read_sql_query(sql, conn, params=params or [], parse_dates=["timestamp"])
        else:
            df = pd.read_sql_query(sql, conn, params=params or [], parse_dates=["timestamp"])
        if "extra" in df.columns:
            df["extra"] = df["extra"].apply(lambda value: json.loads(value) if value else {})
        return df
    finally:
        if should_close:
            conn.close()


def get_history(symbol, start=None, end=None, db_path=None, memory=False):
    initialize_database(db_path, memory=memory)
    sql = "SELECT * FROM candles WHERE symbol = ?"
    params = [symbol]

    if start:
        sql += " AND date >= ?"
        params.append(_normalize_date(start))
    if end:
        sql += " AND date <= ?"
        params.append(_normalize_date(end))

    sql += " ORDER BY timestamp"
    df = _read_query(sql, params=params, db_path=db_path, memory=memory)
    return df


def get_date_data(date, db_path=None, memory=False):
    initialize_database(db_path, memory=memory)
    date_str = _normalize_date(date)
    sql = "SELECT * FROM candles WHERE date = ? ORDER BY symbol, timestamp"
    return _read_query(sql, params=[date_str], db_path=db_path, memory=memory)


def get_symbols_for_date(date, db_path=None, memory=False):
    initialize_database(db_path, memory=memory)
    date_str = _normalize_date(date)
    sql = "SELECT DISTINCT symbol FROM candles WHERE date = ? ORDER BY symbol"
    conn, should_close = _get_connection(db_path, memory=memory)
    try:
        if memory:
            with MEMORY_DB_LOCK:
                cursor = conn.cursor()
                cursor.execute(sql, (date_str,))
                result = [row[0] for row in cursor.fetchall()]
        else:
            cursor = conn.cursor()
            cursor.execute(sql, (date_str,))
            result = [row[0] for row in cursor.fetchall()]
        return result
    finally:
        if should_close:
            conn.close()


def get_all_data(db_path=None, parse_dates=True, memory=False):
    initialize_database(db_path, memory=memory)
    sql = "SELECT * FROM candles ORDER BY symbol, timestamp"
    conn, should_close = _get_connection(db_path, memory=memory)
    try:
        if memory:
            with MEMORY_DB_LOCK:
                if parse_dates:
                    df = pd.read_sql_query(sql, conn, parse_dates=["timestamp"])
                else:
                    df = pd.read_sql_query(sql, conn)
        else:
            if parse_dates:
                df = pd.read_sql_query(sql, conn, parse_dates=["timestamp"])
            else:
                df = pd.read_sql_query(sql, conn)
        if "extra" in df.columns:
            df["extra"] = df["extra"].apply(lambda value: json.loads(value) if value else {})
        return df
    finally:
        if should_close:
            conn.close()


def print_all_data(db_path=None, max_rows=1000):
    df = get_all_data(db_path=db_path)
    total = len(df)
    logger.info(f"Reading all candle data from database: {total} rows")
    if max_rows is not None and total > max_rows:
        logger.info(f"Printing first {max_rows} rows out of {total}")
        logger.info(df.head(max_rows).to_string(index=False))
    else:
        logger.info(df.to_string(index=False))
    return df


def export_history_to_csv(symbol=None, start=None, end=None, output_path=None, db_path=None):
    """Export local candle history to CSV.

    If symbol is provided, exports only that symbol's history; otherwise exports all data.
    """
    if symbol:
        df = get_history(symbol, start=start, end=end, db_path=db_path)
    elif start is not None or end is not None:
        initialize_database(db_path)
        sql = "SELECT * FROM candles WHERE 1=1"
        params = []
        if start:
            sql += " AND timestamp >= ?"
            params.append(_normalize_timestamp(start))
        if end:
            sql += " AND timestamp <= ?"
            params.append(_normalize_timestamp(end))
        sql += " ORDER BY symbol, timestamp"
        df = _read_query(sql, params=params, db_path=db_path)
    else:
        df = get_all_data(db_path=db_path)

    if df is None or df.empty:
        logger.warning("No historical data available to export.")
        return None

    if output_path is None:
        parts = [symbol or "all"]
        if start:
            parts.append(f"from_{_normalize_date(start)}")
        if end:
            parts.append(f"to_{_normalize_date(end)}")
        output_path = os.path.join(os.getcwd(), f"candle_history_{'_'.join(parts)}.csv")

    df.to_csv(output_path, index=False)
    logger.info(f"Exported candle history to CSV: {output_path}")
    return output_path


def export_symbol_counts(output_path=None, db_path=None, memory=False):
    """Export symbol row counts for the candle database."""
    initialize_database(db_path, memory=memory)
    sql = "SELECT symbol, COUNT(*) AS row_count FROM candles GROUP BY symbol ORDER BY symbol"
    df = _read_query(sql, db_path=db_path, memory=memory)

    if df is None or df.empty:
        logger.warning("No symbol count data available to export.")
        return None

    if output_path is None:
        output_path = os.path.join(os.getcwd(), "candle_symbol_counts.csv")

    df.to_csv(output_path, index=False)
    logger.info(f"Exported candle symbol counts to CSV: {output_path}")
    return output_path


if __name__ == "__main__":
    # Example usage: export all data to CSV
    export_history_to_csv(symbol = "KTKBANK", output_path="candle_history_all.csv")
    #export_symbol_counts()
    #export_symbol_counts()
