#!/usr/bin/env python3
"""
TrendScope - Database Module
PostgreSQL (Supabase) backend with auto-cleanup.
Falls back to JSON file storage if DATABASE_URL not set (local dev).
"""

import os
import json
import logging
from datetime import datetime, timezone, timedelta
from contextlib import contextmanager

logger = logging.getLogger(__name__)

# ─── Configuration ────────────────────────────────────────────────────────────

DATABASE_URL = os.environ.get('DATABASE_URL', '').strip()
DATA_RETENTION_DAYS = int(os.environ.get('DATA_RETENTION_DAYS', '180'))  # 6 months
LOG_RETENTION_DAYS = int(os.environ.get('LOG_RETENTION_DAYS', '30'))    # 30 days
JOB_RETENTION_DAYS = int(os.environ.get('JOB_RETENTION_DAYS', '7'))     # 7 days

# Try to import psycopg2
try:
    import psycopg2
    import psycopg2.extras
    HAS_POSTGRES = True
except ImportError:
    HAS_POSTGRES = False
    logger.warning("psycopg2 not installed - using JSON file storage")

# Use PostgreSQL only if both library AND URL are available
USE_POSTGRES = HAS_POSTGRES and bool(DATABASE_URL)

# JSON fallback file
JSON_FILE = os.path.join(os.path.dirname(__file__), 'data.json')


# ═══════════════════════════════════════════════════════════════════════════════
# POSTGRESQL BACKEND (Supabase)
# ═══════════════════════════════════════════════════════════════════════════════

@contextmanager
def get_db():
    """Get a PostgreSQL connection."""
    conn = psycopg2.connect(DATABASE_URL, sslmode='require')
    conn.autocommit = True
    try:
        yield conn
    finally:
        conn.close()


def init_postgres_schema():
    """Create tables and indexes if they don't exist."""
    schema = """
    CREATE TABLE IF NOT EXISTS websites (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        url TEXT NOT NULL,
        logo TEXT,
        color TEXT,
        is_active BOOLEAN DEFAULT TRUE,
        last_scraped TIMESTAMPTZ,
        created_at TIMESTAMPTZ DEFAULT NOW()
    );

    CREATE TABLE IF NOT EXISTS products (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        price TEXT,
        currency TEXT,
        image_url TEXT,
        product_url TEXT,
        category TEXT,
        source_website TEXT,
        color TEXT,
        description TEXT,
        scraped_at TIMESTAMPTZ DEFAULT NOW()
    );

    CREATE INDEX IF NOT EXISTS idx_products_scraped_at ON products(scraped_at);
    CREATE INDEX IF NOT EXISTS idx_products_source ON products(source_website);
    CREATE INDEX IF NOT EXISTS idx_products_category ON products(category);

    CREATE TABLE IF NOT EXISTS scrape_jobs (
        id TEXT PRIMARY KEY,
        website_id TEXT,
        website_name TEXT,
        status TEXT,
        progress INTEGER DEFAULT 0,
        started_at TIMESTAMPTZ,
        completed_at TIMESTAMPTZ,
        error TEXT,
        products_found INTEGER DEFAULT 0
    );

    CREATE INDEX IF NOT EXISTS idx_jobs_started ON scrape_jobs(started_at DESC);

    CREATE TABLE IF NOT EXISTS logs (
        id TEXT PRIMARY KEY,
        "timestamp" TIMESTAMPTZ DEFAULT NOW(),
        type TEXT,
        message TEXT,
        website_name TEXT
    );

    CREATE INDEX IF NOT EXISTS idx_logs_timestamp ON logs("timestamp" DESC);
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(schema)
    logger.info("✅ PostgreSQL schema initialized")


def _row_to_dict(row, columns):
    """Convert a row tuple to a dict, serializing datetimes."""
    result = {}
    for col, val in zip(columns, row):
        if isinstance(val, datetime):
            result[col] = val.isoformat()
        else:
            result[col] = val
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# JSON FILE BACKEND (Local dev fallback)
# ═══════════════════════════════════════════════════════════════════════════════

def _load_json():
    """Load JSON data from file."""
    if os.path.exists(JSON_FILE):
        try:
            with open(JSON_FILE, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                if content:
                    return json.loads(content)
        except Exception as e:
            logger.error(f"JSON load error: {e}")
    return {'websites': [], 'products': [], 'scrape_jobs': [], 'logs': []}


def _save_json(data):
    """Save JSON data to file."""
    try:
        with open(JSON_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, default=str)
    except Exception as e:
        logger.error(f"JSON save error: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
# UNIFIED DATABASE API
# ═══════════════════════════════════════════════════════════════════════════════

class Database:
    """
    Unified database API that uses PostgreSQL (production) or JSON (local dev).
    """

    def __init__(self):
        self.backend = 'postgres' if USE_POSTGRES else 'json'
        logger.info(f"📦 Database backend: {self.backend.upper()}")

        if self.backend == 'postgres':
            try:
                init_postgres_schema()
            except Exception as e:
                logger.error(f"❌ PostgreSQL init failed: {e}")
                logger.warning("⚠️  Falling back to JSON storage")
                self.backend = 'json'

    # ─── Websites ─────────────────────────────────────────────────────────────

    def get_websites(self):
        if self.backend == 'postgres':
            with get_db() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT id, name, url, logo, color, is_active, last_scraped FROM websites ORDER BY created_at")
                    cols = ['id', 'name', 'url', 'logo', 'color', 'is_active', 'last_scraped']
                    return [_row_to_dict(r, cols) for r in cur.fetchall()]
        else:
            return _load_json().get('websites', [])

    def add_website(self, website):
        if self.backend == 'postgres':
            with get_db() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO websites (id, name, url, logo, color, is_active, last_scraped)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (id) DO NOTHING
                    """, (
                        website['id'], website['name'], website['url'],
                        website.get('logo'), website.get('color'),
                        website.get('is_active', True), website.get('last_scraped')
                    ))
        else:
            data = _load_json()
            if not any(w['id'] == website['id'] for w in data['websites']):
                data['websites'].append(website)
                _save_json(data)

    def remove_website(self, website_id):
        if self.backend == 'postgres':
            with get_db() as conn:
                with conn.cursor() as cur:
                    # Get website name first
                    cur.execute("SELECT name FROM websites WHERE id = %s", (website_id,))
                    row = cur.fetchone()
                    if row:
                        name = row[0]
                        cur.execute("DELETE FROM products WHERE source_website = %s", (name,))
                    cur.execute("DELETE FROM websites WHERE id = %s", (website_id,))
        else:
            data = _load_json()
            website = next((w for w in data['websites'] if w['id'] == website_id), None)
            if website:
                data['websites'] = [w for w in data['websites'] if w['id'] != website_id]
                data['products'] = [p for p in data['products'] if p.get('source_website') != website['name']]
                _save_json(data)

    def toggle_website(self, website_id):
        if self.backend == 'postgres':
            with get_db() as conn:
                with conn.cursor() as cur:
                    cur.execute("UPDATE websites SET is_active = NOT is_active WHERE id = %s RETURNING id, name, url, logo, color, is_active, last_scraped", (website_id,))
                    row = cur.fetchone()
                    if row:
                        cols = ['id', 'name', 'url', 'logo', 'color', 'is_active', 'last_scraped']
                        return _row_to_dict(row, cols)
        else:
            data = _load_json()
            for w in data['websites']:
                if w['id'] == website_id:
                    w['is_active'] = not w.get('is_active', True)
                    _save_json(data)
                    return w
        return None

    def update_website_scraped(self, website_id):
        """Update the last_scraped timestamp."""
        now = datetime.now(timezone.utc).isoformat()
        if self.backend == 'postgres':
            with get_db() as conn:
                with conn.cursor() as cur:
                    cur.execute("UPDATE websites SET last_scraped = NOW() WHERE id = %s", (website_id,))
        else:
            data = _load_json()
            for w in data['websites']:
                if w['id'] == website_id:
                    w['last_scraped'] = now
                    _save_json(data)
                    break

    # ─── Products ─────────────────────────────────────────────────────────────

    def get_products(self, category=None, website_ids=None):
        if self.backend == 'postgres':
            query = "SELECT id, name, price, currency, image_url, product_url, category, source_website, color, description, scraped_at FROM products WHERE 1=1"
            params = []

            if category and category != 'All':
                query += " AND category = %s"
                params.append(category)

            if website_ids:
                # Get website names from IDs
                with get_db() as conn:
                    with conn.cursor() as cur:
                        cur.execute("SELECT name FROM websites WHERE id = ANY(%s)", (website_ids,))
                        names = [r[0] for r in cur.fetchall()]
                if names:
                    query += " AND source_website = ANY(%s)"
                    params.append(names)

            query += " ORDER BY scraped_at DESC LIMIT 500"

            with get_db() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, params)
                    cols = ['id', 'name', 'price', 'currency', 'image_url', 'product_url',
                            'category', 'source_website', 'color', 'description', 'scraped_at']
                    return [_row_to_dict(r, cols) for r in cur.fetchall()]
        else:
            data = _load_json()
            products = data.get('products', [])

            if category and category != 'All':
                products = [p for p in products if p.get('category') == category]

            if website_ids:
                websites = data.get('websites', [])
                names = {w['name'] for w in websites if w['id'] in website_ids}
                products = [p for p in products if p.get('source_website') in names]

            return products

    def replace_website_products(self, website_name, new_products):
        """Replace all products for a website with new scraped products."""
        if self.backend == 'postgres':
            with get_db() as conn:
                with conn.cursor() as cur:
                    # Delete old products from this website
                    cur.execute("DELETE FROM products WHERE source_website = %s", (website_name,))
                    # Insert new products
                    if new_products:
                        psycopg2.extras.execute_values(cur, """
                            INSERT INTO products (id, name, price, currency, image_url, product_url, category, source_website, color, description, scraped_at)
                            VALUES %s
                            ON CONFLICT (id) DO NOTHING
                        """, [
                            (p['id'], p['name'], p.get('price'), p.get('currency'),
                             p.get('image_url'), p.get('product_url'), p.get('category'),
                             p.get('source_website'), p.get('color'), p.get('description'),
                             p.get('scraped_at', datetime.now(timezone.utc).isoformat()))
                            for p in new_products
                        ])
        else:
            data = _load_json()
            data['products'] = [p for p in data['products'] if p.get('source_website') != website_name]
            data['products'].extend(new_products)
            _save_json(data)

    def get_summary(self):
        """Get aggregated category statistics."""
        if self.backend == 'postgres':
            with get_db() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT category, COUNT(*) as count, COUNT(DISTINCT source_website) as website_count
                        FROM products
                        GROUP BY category
                        ORDER BY count DESC
                    """)
                    rows = cur.fetchall()
                    summary = [{'category': r[0], 'count': r[1], 'website_count': r[2]} for r in rows]

                    cur.execute("SELECT COUNT(*) FROM products")
                    total_products = cur.fetchone()[0]

                    cur.execute("SELECT COUNT(*) FROM websites WHERE is_active = TRUE")
                    active_websites = cur.fetchone()[0]

                    return {
                        'summary': summary,
                        'total_products': total_products,
                        'active_websites': active_websites,
                        'categories_with_data': len(summary)
                    }
        else:
            data = _load_json()
            products = data.get('products', [])
            categories = {}
            for p in products:
                cat = p.get('category', 'Other')
                if cat not in categories:
                    categories[cat] = {'count': 0, 'websites': set()}
                categories[cat]['count'] += 1
                categories[cat]['websites'].add(p.get('source_website'))
            summary = [
                {'category': cat, 'count': info['count'], 'website_count': len(info['websites'])}
                for cat, info in categories.items()
            ]
            summary.sort(key=lambda x: x['count'], reverse=True)
            return {
                'summary': summary,
                'total_products': len(products),
                'active_websites': len([w for w in data.get('websites', []) if w.get('is_active')]),
                'categories_with_data': len(summary)
            }

    # ─── Scrape Jobs ──────────────────────────────────────────────────────────

    def add_job(self, job):
        if self.backend == 'postgres':
            with get_db() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO scrape_jobs (id, website_id, website_name, status, progress, started_at, completed_at, error, products_found)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """, (
                        job['id'], job['website_id'], job['website_name'],
                        job['status'], job.get('progress', 0),
                        job.get('started_at'), job.get('completed_at'),
                        job.get('error'), job.get('products_found', 0)
                    ))
        else:
            data = _load_json()
            data['scrape_jobs'].append(job)
            data['scrape_jobs'] = data['scrape_jobs'][-50:]
            _save_json(data)

    def update_job(self, job_id, **updates):
        if self.backend == 'postgres':
            if not updates:
                return
            set_clause = ", ".join([f"{k} = %s" for k in updates.keys()])
            values = list(updates.values()) + [job_id]
            with get_db() as conn:
                with conn.cursor() as cur:
                    cur.execute(f"UPDATE scrape_jobs SET {set_clause} WHERE id = %s", values)
        else:
            data = _load_json()
            for j in data['scrape_jobs']:
                if j['id'] == job_id:
                    j.update(updates)
                    break
            _save_json(data)

    def get_jobs(self, limit=50):
        if self.backend == 'postgres':
            with get_db() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT id, website_id, website_name, status, progress, started_at, completed_at, error, products_found
                        FROM scrape_jobs ORDER BY started_at DESC LIMIT %s
                    """, (limit,))
                    cols = ['id', 'website_id', 'website_name', 'status', 'progress',
                            'started_at', 'completed_at', 'error', 'products_found']
                    return [_row_to_dict(r, cols) for r in cur.fetchall()]
        else:
            return _load_json().get('scrape_jobs', [])[-limit:]

    # ─── Logs ─────────────────────────────────────────────────────────────────

    def add_log(self, log):
        if self.backend == 'postgres':
            with get_db() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO logs (id, "timestamp", type, message, website_name)
                        VALUES (%s, %s, %s, %s, %s)
                    """, (log['id'], log['timestamp'], log['type'], log['message'], log.get('website_name')))
        else:
            data = _load_json()
            data['logs'].insert(0, log)
            data['logs'] = data['logs'][:200]
            _save_json(data)

    def get_logs(self, limit=200):
        if self.backend == 'postgres':
            with get_db() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT id, "timestamp", type, message, website_name
                        FROM logs ORDER BY "timestamp" DESC LIMIT %s
                    """, (limit,))
                    cols = ['id', 'timestamp', 'type', 'message', 'website_name']
                    return [_row_to_dict(r, cols) for r in cur.fetchall()]
        else:
            return _load_json().get('logs', [])[:limit]

    # ─── 🧹 AUTO-CLEANUP (THE KEY FEATURE) ────────────────────────────────────

    def cleanup_old_data(self):
        """
        Auto-delete data older than retention period.
        Called by scheduler daily at 3:00 AM.

        Returns dict with counts of deleted records.
        """
        deleted = {'products': 0, 'logs': 0, 'jobs': 0}

        if self.backend == 'postgres':
            try:
                with get_db() as conn:
                    with conn.cursor() as cur:
                        # Delete old products (>180 days)
                        cur.execute(
                            "DELETE FROM products WHERE scraped_at < NOW() - INTERVAL '%s days'",
                            (DATA_RETENTION_DAYS,)
                        )
                        deleted['products'] = cur.rowcount

                        # Delete old logs (>30 days)
                        cur.execute(
                            'DELETE FROM logs WHERE "timestamp" < NOW() - INTERVAL \'%s days\'',
                            (LOG_RETENTION_DAYS,)
                        )
                        deleted['logs'] = cur.rowcount

                        # Delete old jobs (>7 days)
                        cur.execute(
                            "DELETE FROM scrape_jobs WHERE started_at < NOW() - INTERVAL '%s days'",
                            (JOB_RETENTION_DAYS,)
                        )
                        deleted['jobs'] = cur.rowcount

                        # Vacuum to reclaim space (PostgreSQL specific)
                        # Note: VACUUM cannot run inside a transaction, skip in autocommit mode
            except Exception as e:
                logger.error(f"Cleanup error: {e}")
        else:
            # JSON cleanup
            data = _load_json()
            cutoff_products = (datetime.now(timezone.utc) - timedelta(days=DATA_RETENTION_DAYS)).isoformat()
            cutoff_logs = (datetime.now(timezone.utc) - timedelta(days=LOG_RETENTION_DAYS)).isoformat()
            cutoff_jobs = (datetime.now(timezone.utc) - timedelta(days=JOB_RETENTION_DAYS)).isoformat()

            old_products = len(data.get('products', []))
            data['products'] = [p for p in data.get('products', []) if p.get('scraped_at', '9999') > cutoff_products]
            deleted['products'] = old_products - len(data['products'])

            old_logs = len(data.get('logs', []))
            data['logs'] = [l for l in data.get('logs', []) if l.get('timestamp', '9999') > cutoff_logs]
            deleted['logs'] = old_logs - len(data['logs'])

            old_jobs = len(data.get('scrape_jobs', []))
            data['scrape_jobs'] = [j for j in data.get('scrape_jobs', [])
                                   if j.get('started_at') and j['started_at'] > cutoff_jobs]
            deleted['jobs'] = old_jobs - len(data['scrape_jobs'])

            _save_json(data)

        total = sum(deleted.values())
        logger.info(f"🧹 Cleanup: deleted {deleted['products']} products, "
                    f"{deleted['logs']} logs, {deleted['jobs']} jobs")
        return deleted

    def get_storage_stats(self):
        """Get storage usage statistics."""
        if self.backend == 'postgres':
            try:
                with get_db() as conn:
                    with conn.cursor() as cur:
                        cur.execute("SELECT COUNT(*) FROM products")
                        product_count = cur.fetchone()[0]
                        cur.execute("SELECT COUNT(*) FROM logs")
                        log_count = cur.fetchone()[0]
                        cur.execute("SELECT COUNT(*) FROM scrape_jobs")
                        job_count = cur.fetchone()[0]

                        # Get database size
                        cur.execute("SELECT pg_database_size(current_database())")
                        db_size_bytes = cur.fetchone()[0]

                        # Get oldest product date
                        cur.execute("SELECT MIN(scraped_at) FROM products")
                        oldest = cur.fetchone()[0]
                        oldest_iso = oldest.isoformat() if oldest else None

                        return {
                            'backend': 'postgres',
                            'product_count': product_count,
                            'log_count': log_count,
                            'job_count': job_count,
                            'db_size_bytes': db_size_bytes,
                            'db_size_mb': round(db_size_bytes / (1024 * 1024), 2),
                            'oldest_product': oldest_iso,
                            'retention_days': DATA_RETENTION_DAYS,
                        }
            except Exception as e:
                logger.error(f"Stats error: {e}")
                return {'backend': 'postgres', 'error': str(e)}
        else:
            data = _load_json()
            file_size = os.path.getsize(JSON_FILE) if os.path.exists(JSON_FILE) else 0
            return {
                'backend': 'json',
                'product_count': len(data.get('products', [])),
                'log_count': len(data.get('logs', [])),
                'job_count': len(data.get('scrape_jobs', [])),
                'db_size_bytes': file_size,
                'db_size_mb': round(file_size / (1024 * 1024), 4),
                'retention_days': DATA_RETENTION_DAYS,
            }


# Global database instance
db = Database()
