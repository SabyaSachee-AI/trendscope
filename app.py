#!/usr/bin/env python3
"""
TrendScope - Competitive Fashion Intelligence Platform
Flask Backend Server (PostgreSQL + Auto-Cleanup)
"""

import os
import time
import threading
import logging
import random
from datetime import datetime, timezone
from urllib.parse import urlparse

# Load .env file if exists (for local dev)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from flask import Flask, jsonify, request, send_from_directory

# Configure logging FIRST
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

try:
    from flask_cors import CORS
    HAS_CORS = True
except ImportError:
    HAS_CORS = False

try:
    from apscheduler.schedulers.background import BackgroundScheduler
    HAS_SCHEDULER = True
except ImportError:
    HAS_SCHEDULER = False
    logger.warning("APScheduler not installed.")

# Import database AFTER logging is configured
from database import db, DATA_RETENTION_DAYS

try:
    from scraper import WebScraper
except ImportError as e:
    logger.error(f"Failed to import WebScraper: {e}")
    class WebScraper:
        def scrape_website(self, name, url, progress_callback=None):
            return []

# ─── Flask App ────────────────────────────────────────────────────────────────

app = Flask(__name__, static_folder='static', static_url_path='')
if HAS_CORS:
    CORS(app)

# Optional API key for external cron triggers (set CRON_SECRET env var)
CRON_SECRET = os.environ.get('CRON_SECRET', '').strip()

# ─── Default Websites ─────────────────────────────────────────────────────────

DEFAULT_WEBSITES = [
    {'id': 'zara', 'name': 'ZARA', 'url': 'https://www.zara.com/', 'logo': 'Z', 'color': '#000000', 'is_active': True, 'last_scraped': None},
    {'id': 'lululemon', 'name': 'Lululemon', 'url': 'https://shop.lululemon.com/', 'logo': 'L', 'color': '#D31334', 'is_active': True, 'last_scraped': None},
    {'id': 'uniqlo', 'name': 'UNIQLO', 'url': 'https://www.uniqlo.com/us/en/', 'logo': 'U', 'color': '#C8102E', 'is_active': True, 'last_scraped': None},
    {'id': 'next', 'name': 'Next', 'url': 'https://www.next.co.uk/', 'logo': 'N', 'color': '#E2001A', 'is_active': True, 'last_scraped': None},
    {'id': 'bershka', 'name': 'Bershka', 'url': 'https://www.bershka.com/', 'logo': 'B', 'color': '#F15A24', 'is_active': True, 'last_scraped': None},
    {'id': 'jcrew', 'name': 'J.Crew', 'url': 'https://www.jcrew.com/bd/', 'logo': 'JC', 'color': '#003865', 'is_active': True, 'last_scraped': None},
    {'id': 'ralphlauren', 'name': 'Ralph Lauren', 'url': 'https://www.ralphlauren.com/', 'logo': 'RL', 'color': '#003DA5', 'is_active': True, 'last_scraped': None},
]

def init_defaults():
    """Initialize default websites if none exist."""
    if not db.get_websites():
        for w in DEFAULT_WEBSITES:
            db.add_website(w)
        add_log('info', '📋 Initialized default websites for monitoring')

# ─── Log Helper ───────────────────────────────────────────────────────────────

def add_log(log_type, message, website_name=None):
    log_entry = {
        'id': f'log-{int(time.time() * 1000)}-{random.randint(0, 9999)}',
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'type': log_type,
        'message': message,
        'website_name': website_name
    }
    db.add_log(log_entry)
    return log_entry

# ─── Scraping Engine ──────────────────────────────────────────────────────────

scraper = WebScraper()
_scrape_lock = threading.Lock()

def run_scrape_job(website_id):
    """Run a scrape job for a specific website (background thread)."""
    websites = db.get_websites()
    website = next((w for w in websites if w['id'] == website_id), None)
    if not website:
        logger.error(f"Website {website_id} not found")
        return

    job_id = f'job-{int(time.time() * 1000)}-{random.randint(0, 9999)}'
    now = datetime.now(timezone.utc).isoformat()

    job = {
        'id': job_id,
        'website_id': website['id'],
        'website_name': website['name'],
        'status': 'running',
        'progress': 0,
        'started_at': now,
        'completed_at': None,
        'error': None,
        'products_found': 0
    }
    db.add_job(job)
    add_log('info', f'🔄 Started scraping {website["name"]}...', website['name'])

    def update_progress(progress):
        db.update_job(job_id, progress=min(int(progress), 100))

    try:
        scraped_products = scraper.scrape_website(
            website['name'], website['url'], progress_callback=update_progress
        )

        db.replace_website_products(website['name'], scraped_products)
        db.update_website_scraped(website_id)
        db.update_job(
            job_id,
            status='completed',
            progress=100,
            completed_at=datetime.now(timezone.utc).isoformat(),
            products_found=len(scraped_products)
        )
        add_log('success', f'✅ {website["name"]}: Scraped {len(scraped_products)} products', website['name'])
        logger.info(f"Completed {website['name']}: {len(scraped_products)} products")

    except Exception as e:
        logger.error(f"Failed scraping {website['name']}: {e}")
        db.update_job(
            job_id,
            status='failed',
            completed_at=datetime.now(timezone.utc).isoformat(),
            error=str(e)
        )
        add_log('error', f'❌ {website["name"]}: {str(e)}', website['name'])

def scrape_all_websites():
    """Scrape all active websites sequentially."""
    if not _scrape_lock.acquire(blocking=False):
        logger.warning("Scrape already in progress, skipping")
        return

    try:
        websites = [w for w in db.get_websites() if w.get('is_active', True)]
        if not websites:
            add_log('warning', '⚠️ No active websites to scrape')
            return

        add_log('info', f'🚀 Starting full scrape of {len(websites)} active websites...')

        for website in websites:
            run_scrape_job(website['id'])

        add_log('success', f'🎉 All {len(websites)} websites scraped successfully!')
    finally:
        _scrape_lock.release()

# ─── 🧹 Auto-Cleanup ──────────────────────────────────────────────────────────

def cleanup_task():
    """Daily cleanup task - removes old data."""
    logger.info("🧹 Running scheduled cleanup...")
    try:
        deleted = db.cleanup_old_data()
        if sum(deleted.values()) > 0:
            add_log('info',
                    f'🧹 Cleanup: deleted {deleted["products"]} old products, '
                    f'{deleted["logs"]} old logs, {deleted["jobs"]} old jobs '
                    f'(retention: {DATA_RETENTION_DAYS} days)')
    except Exception as e:
        logger.error(f"Cleanup task failed: {e}")
        add_log('error', f'❌ Cleanup failed: {str(e)}')

# ─── API Routes ───────────────────────────────────────────────────────────────

@app.route('/api/status')
def api_status():
    return jsonify({
        'status': 'online',
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'database_backend': db.backend
    })

@app.route('/api/websites', methods=['GET'])
def api_get_websites():
    return jsonify(db.get_websites())

@app.route('/api/websites', methods=['POST'])
def api_add_website():
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    name = data.get('name', '').strip()
    url = data.get('url', '').strip()

    if not name or not url:
        return jsonify({'error': 'Name and URL are required'}), 400

    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url

    try:
        parsed = urlparse(url)
        if not parsed.netloc:
            return jsonify({'error': 'Invalid URL format'}), 400
    except Exception:
        return jsonify({'error': 'Invalid URL'}), 400

    website_id = name.lower().replace(' ', '-').replace('/', '-').replace('.', '-')
    existing = db.get_websites()
    if any(w['id'] == website_id or w['url'].rstrip('/') == url.rstrip('/') for w in existing):
        return jsonify({'error': 'This website already exists'}), 409

    initials = ''.join(word[0] for word in name.split() if word).upper()[:2]
    color = f"#{random.randint(0, 0xFFFFFF):06x}"

    new_website = {
        'id': website_id,
        'name': name,
        'url': url,
        'logo': initials,
        'color': color,
        'is_active': True,
        'last_scraped': None
    }
    db.add_website(new_website)
    add_log('success', f'➕ Added new website: {name}', name)
    return jsonify(new_website), 201

@app.route('/api/websites/<website_id>', methods=['DELETE'])
def api_remove_website(website_id):
    websites = db.get_websites()
    website = next((w for w in websites if w['id'] == website_id), None)
    if not website:
        return jsonify({'error': 'Website not found'}), 404
    db.remove_website(website_id)
    add_log('info', f'🗑️ Removed website: {website["name"]}', website['name'])
    return jsonify({'success': True})

@app.route('/api/websites/<website_id>/toggle', methods=['POST'])
def api_toggle_website(website_id):
    result = db.toggle_website(website_id)
    if not result:
        return jsonify({'error': 'Website not found'}), 404
    return jsonify(result)

@app.route('/api/products')
def api_get_products():
    category = request.args.get('category', 'All')
    websites_param = request.args.get('websites')
    website_ids = websites_param.split(',') if websites_param else None
    products = db.get_products(category=category, website_ids=website_ids)
    return jsonify({'products': products, 'total': len(products)})

@app.route('/api/products/summary')
def api_get_summary():
    return jsonify(db.get_summary())

@app.route('/api/scrape', methods=['POST', 'GET'])
def api_scrape_all():
    """
    Trigger scrape of all active websites.
    Supports both POST (from UI) and GET (from cron-job.org).
    Optional: ?key=YOUR_CRON_SECRET for security.
    """
    # If CRON_SECRET is configured, validate it
    if CRON_SECRET:
        provided_key = request.args.get('key', '') or request.headers.get('X-Cron-Key', '')
        if provided_key != CRON_SECRET:
            return jsonify({'error': 'Unauthorized'}), 401

    thread = threading.Thread(target=scrape_all_websites, daemon=True)
    thread.start()
    return jsonify({'status': 'started', 'message': 'Scraping all websites...'})

@app.route('/api/scrape/<website_id>', methods=['POST'])
def api_scrape_single(website_id):
    websites = db.get_websites()
    website = next((w for w in websites if w['id'] == website_id), None)
    if not website:
        return jsonify({'error': 'Website not found'}), 404
    thread = threading.Thread(target=run_scrape_job, args=(website_id,), daemon=True)
    thread.start()
    return jsonify({'status': 'started', 'message': f'Scraping {website["name"]}...'})

@app.route('/api/jobs')
def api_get_jobs():
    return jsonify(db.get_jobs())

@app.route('/api/logs')
def api_get_logs():
    return jsonify(db.get_logs())

@app.route('/api/storage')
def api_get_storage():
    """Get storage statistics for the dashboard."""
    return jsonify(db.get_storage_stats())

@app.route('/api/cleanup', methods=['POST', 'GET'])
def api_cleanup():
    """
    Manually trigger cleanup of old data.
    Can also be called by cron-job.org (GET supported).
    """
    if CRON_SECRET:
        provided_key = request.args.get('key', '') or request.headers.get('X-Cron-Key', '')
        if provided_key != CRON_SECRET:
            return jsonify({'error': 'Unauthorized'}), 401

    deleted = db.cleanup_old_data()
    add_log('info',
            f'🧹 Manual cleanup: deleted {deleted["products"]} products, '
            f'{deleted["logs"]} logs, {deleted["jobs"]} jobs')
    return jsonify({'status': 'completed', 'deleted': deleted})

# ─── Scheduled Tasks ──────────────────────────────────────────────────────────

def init_scheduler():
    """Initialize APScheduler for monthly scraping + daily cleanup."""
    if not HAS_SCHEDULER:
        logger.warning("Scheduler not available")
        return None

    scheduler = BackgroundScheduler(daemon=True, timezone='UTC')

    # Monthly auto-scrape (1st of each month at 2:00 AM UTC)
    scheduler.add_job(
        scrape_all_websites, 'cron', day=1, hour=2, minute=0,
        id='monthly_scrape', name='Monthly Auto-Scrape', replace_existing=True
    )

    # 🧹 Daily auto-cleanup (every day at 3:00 AM UTC)
    scheduler.add_job(
        cleanup_task, 'cron', hour=3, minute=0,
        id='daily_cleanup', name='Daily Auto-Cleanup', replace_existing=True
    )

    scheduler.start()
    logger.info(f"📅 Scheduler started: monthly scrape (1st @ 2AM UTC), daily cleanup (3AM UTC, retention {DATA_RETENTION_DAYS}d)")
    add_log('info', f'📅 Scheduler active — monthly scrape + daily cleanup ({DATA_RETENTION_DAYS}d retention)')
    return scheduler

# ─── Serve Frontend ───────────────────────────────────────────────────────────

@app.route('/')
def serve_index():
    return send_from_directory(app.static_folder, 'index.html')

@app.route('/<path:path>')
def serve_static(path):
    full_path = os.path.join(app.static_folder, path)
    if os.path.exists(full_path) and os.path.isfile(full_path):
        return send_from_directory(app.static_folder, path)
    return send_from_directory(app.static_folder, 'index.html')

# ─── Initialize on startup ────────────────────────────────────────────────────

init_defaults()
scheduler_instance = init_scheduler()

# ─── Main ─────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    # On first run, trigger initial scrape if no products exist
    if not db.get_products():
        logger.info("No products found. Starting initial scrape in background...")
        add_log('info', '📋 No products found. Starting initial scrape...')
        threading.Thread(target=scrape_all_websites, daemon=True).start()

    port = int(os.environ.get('PORT', 5000))
    logger.info(f"🚀 TrendScope server starting on port {port}")
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
