# 🚀 TrendScope — Bangla Deployment Guide

**Stack:** Render.com (Hosting) + Supabase (Database) + cron-job.org (Schedule) + Auto-Cleanup

---

## 📋 কী কী লাগবে?

আগে এই ৩টা website-এ account খুলে রাখুন (সব ফ্রি, কোনো card লাগবে না):

1. **GitHub** — https://github.com (code রাখার জন্য)
2. **Supabase** — https://supabase.com (database)
3. **Render** — https://render.com (server)
4. **cron-job.org** — https://cron-job.org (auto schedule)

---

# 🏁 Part 1: GitHub-এ Code Push করুন

## Step 1.1: GitHub-এ নতুন Repository বানান

1. https://github.com/new এ যান
2. Repository name: `trendscope`
3. Public/Private — যেকোনোটা select করুন
4. **README/gitignore কিচ্ছু add করবেন না** (আমাদের আগে থেকেই আছে)
5. **Create Repository** ক্লিক করুন

## Step 1.2: আপনার Computer থেকে Code Push করুন

আপনার project folder-এ Terminal/CMD খুলে এই command গুলো দিন:

```bash
git init
git add .
git commit -m "Initial commit: TrendScope"
git branch -M main
git remote add origin https://github.com/SabyaSachee-AI/trendscope.git
git push -u origin main
```

⚠️ `YOUR-USERNAME` এর জায়গায় আপনার GitHub username বসান।

✅ **Done!** Code এখন GitHub-এ আছে।

---

# 🗄️ Part 2: Supabase Database Setup

## Step 2.1: Supabase Account খুলুন

1. https://supabase.com এ যান
2. **Start your project** → GitHub দিয়ে sign up
3. Email verify করুন

## Step 2.2: New Project বানান

1. **New Project** button click করুন
2. ফর্ম পূরণ করুন:
   - **Name:** `trendscope`
   - **Database Password:** একটা strong password দিন (📝 কোথাও লিখে রাখুন!)
   - **Region:** **Singapore** (Bangladesh-এর জন্য fastest)
   - **Pricing Plan:** Free
3. **Create new project** click করুন
4. ২-৩ মিনিট wait করুন (database তৈরি হচ্ছে)

## Step 2.3: Database Connection String কপি করুন

1. Project ready হলে → বাম পাশে **Settings** (⚙️) icon click করুন
2. **Database** option-এ click করুন
3. নিচে scroll করে **Connection String** section খুঁজুন
4. **URI** tab select করুন
5. **Mode:** "Transaction" select করুন (port 6543)
6. URI টা copy করুন। দেখতে এরকম হবে:

```
postgresql://postgres.xxxxxxxxxxxxx:[YOUR-PASSWORD]@aws-0-ap-southeast-1.pooler.supabase.com:6543/postgres
```

7. `[YOUR-PASSWORD]` জায়গায় আপনার Step 2.2-এর password বসান
8. পুরো URL টা **Notepad-এ save** করে রাখুন। ৫ মিনিট পরে লাগবে।

✅ **Database তৈরি!** কোনো table বানানো লাগবে না, app নিজে নিজে বানাবে।

---

# 🌐 Part 3: Render.com-এ Deploy করুন

## Step 3.1: Render Account খুলুন

1. https://render.com এ যান
2. **Get Started** → GitHub দিয়ে sign up
3. GitHub authorize করুন

## Step 3.2: New Web Service বানান

1. Dashboard-এ **New +** button → **Web Service** click করুন
2. **Build and deploy from a Git repository** → Next
3. আপনার GitHub repository connect করুন (`trendscope`)
4. **Connect** click করুন

## Step 3.3: Settings পূরণ করুন

| Field | Value |
|---|---|
| **Name** | `trendscope` |
| **Region** | **Singapore** |
| **Branch** | `main` |
| **Runtime** | `Python 3` |
| **Build Command** | নিচের command টা copy করে paste করুন ⬇️ |
| **Start Command** | নিচের command টা copy করে paste করুন ⬇️ |
| **Instance Type** | **Free** |

**Build Command:**
```
pip install -r requirements.txt && python -m playwright install chromium && python -m playwright install-deps chromium || true
```

**Start Command:**
```
gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --timeout 600
```

## Step 3.4: Environment Variables Add করুন

নিচে scroll করে **Advanced** → **Add Environment Variable** click করুন।

এই ৪টা variable add করুন:

| Key | Value |
|---|---|
| `DATABASE_URL` | আপনার Supabase URL (Step 2.3-এ copy করেছিলেন) |
| `CRON_SECRET` | যেকোনো random string (যেমন: `mySecret12345xyz`) — 📝 লিখে রাখুন! |
| `DATA_RETENTION_DAYS` | `180` |
| `PYTHON_VERSION` | `3.11.0` |

## Step 3.5: Deploy Button টিপুন!

1. **Create Web Service** button click করুন
2. **৫-১০ মিনিট wait করুন** (Chromium download হচ্ছে, একটু সময় লাগবে)
3. Logs দেখুন — সব ঠিক হলে দেখবেন:
   ```
   ✅ PostgreSQL schema initialized
   📦 Database backend: POSTGRES
   📅 Scheduler started
   🚀 TrendScope server starting on port 10000
   ```

## Step 3.6: আপনার URL পাবেন

Top-এ আপনার URL দেখাবে, যেমন:
```
https://trendscope.onrender.com
```

✅ **Browser-এ এটা open করুন!** Dashboard দেখতে পাবেন।

---

# ⏰ Part 4: cron-job.org দিয়ে Auto-Schedule

Render free tier-এ server ১৫ মিনিট inactive থাকলে sleep mode-এ যায়। তাই internal scheduler কাজ নাও করতে পারে। External cron service ব্যবহার করি।

## Step 4.1: cron-job.org Account

1. https://cron-job.org এ যান
2. **Sign up free** → email/password দিয়ে register করুন
3. Email verify করুন

## Step 4.2: ২টা Cronjob বানান

### Cronjob #1: Monthly Auto-Scrape

1. **Create cronjob** click করুন
2. পূরণ করুন:
   - **Title:** `TrendScope Monthly Scrape`
   - **URL:** 
     ```
     https://trendscope.onrender.com/api/scrape?key=YOUR_CRON_SECRET
     ```
     ⚠️ `trendscope.onrender.com` জায়গায় আপনার Render URL বসান।
     ⚠️ `YOUR_CRON_SECRET` জায়গায় Step 3.4-এর CRON_SECRET বসান।
   - **Schedule:** "Custom"
     - Days of month: `1`
     - Hours: `2`
     - Minutes: `0`
   - **Request method:** GET
3. **Create** click করুন

### Cronjob #2: Daily Cleanup (Old Data Delete)

1. আবার **Create cronjob** click করুন
2. পূরণ করুন:
   - **Title:** `TrendScope Daily Cleanup`
   - **URL:**
     ```
     https://trendscope.onrender.com/api/cleanup?key=YOUR_CRON_SECRET
     ```
   - **Schedule:** Every day at 3:00 AM
   - **Request method:** GET
3. **Create** click করুন

### Cronjob #3 (Optional): Keep-Alive (Server না ঘুমানোর জন্য)

1. **Create cronjob** click করুন
2. পূরণ করুন:
   - **Title:** `TrendScope Keep-Alive`
   - **URL:** `https://trendscope.onrender.com/api/status`
   - **Schedule:** Every 10 minutes
   - **Request method:** GET
3. **Create** click করুন

✅ **Done!** এখন আপনার app:
- প্রতিদিন রাত ৩টায় auto-cleanup হবে (পুরোনো data delete)
- প্রতি মাসের ১ তারিখ রাত ২টায় auto-scrape হবে
- প্রতি ১০ মিনিটে server alive থাকবে

---

# ✅ Part 5: User Check & Testing

## Test 1: Dashboard Open করুন

আপনার Render URL browser-এ open করুন:
```
https://trendscope.onrender.com
```

দেখবেন:
- ✅ Beautiful dashboard load হবে
- ✅ Sidebar-এ ৭টা website default categories
- ✅ Top-এ "Scrape All" button

## Test 2: Database Connection Verify করুন

URL-এ যান: `https://trendscope.onrender.com/api/status`

Response দেখবেন:
```json
{
  "status": "online",
  "database_backend": "postgres"  ← ✅ এটা "postgres" দেখাতে হবে
}
```

⚠️ যদি `"json"` দেখায় — মানে DATABASE_URL ভুল আছে। Render dashboard-এ গিয়ে চেক করুন।

## Test 3: Manual Scrape Run করুন

1. Dashboard-এ **"Scrape All"** button click করুন
2. Progress bar দেখবেন (এক একটা website scrape হচ্ছে)
3. ৫-১০ মিনিট wait করুন
4. Products tab-এ গিয়ে দেখুন — products show হচ্ছে

## Test 4: Storage Card দেখুন

Dashboard-এ scroll করে **"Storage & Auto-Cleanup"** card দেখবেন:
- ✅ Backend: `PostgreSQL ✓` (green badge)
- ✅ Products count
- ✅ Storage used (MB)
- ✅ Retention: 180 days
- ✅ "Clean Now" button

## Test 5: Auto-Cleanup Test

1. Dashboard-এর Storage card-এ **"Clean Now"** button click করুন
2. Confirm করুন
3. Alert দেখাবে: "Deleted X products, Y logs, Z jobs"

## Test 6: Cron-job.org Verify

1. cron-job.org dashboard-এ যান
2. আপনার ৩টা job দেখুন
3. পাশে green checkmark থাকতে হবে (last execution successful)

---

# 🎯 Part 6: User Guide (অন্য User-দের জন্য)

আপনার app share করার জন্য এই URL দিন:
```
https://trendscope.onrender.com
```

User কী করতে পারবে:

| Feature | কীভাবে? |
|---|---|
| **Category-wise products দেখা** | বাম sidebar-এ category click |
| **Brand filter** | Top-এ brand chip-এ click করে toggle |
| **Manual Scrape** | "Scrape All" button |
| **Single Site Scrape** | Websites tab → "Scrape" button |
| **নতুন Website Add করা** | Sidebar-এ "Add Website" button |
| **Website Remove করা** | Websites tab → trash icon |
| **Activity Log দেখা** | Dashboard-এ "Scrape History" expand করুন |

---

# 🔧 Troubleshooting

## ❌ "database_backend": "json" দেখাচ্ছে
**সমাধান:** Render → আপনার service → Environment → DATABASE_URL ঠিকমতো paste হয়েছে কিনা চেক করুন। `[YOUR-PASSWORD]` জায়গায় actual password বসেছে কিনা।

## ❌ Build failed: "playwright install" error
**সমাধান:** Render free tier-এ Chromium-এর জায়গা সমস্যা হতে পারে। Build command-এ `|| true` add করা আছে যাতে fail না হয়। Playwright fail হলেও app চলবে — শুধু কিছু site mock data দেখাবে।

## ❌ Cron-job.org-এ "Unauthorized" error
**সমাধান:** URL-এ `?key=YOUR_SECRET` ঠিকমতো add হয়েছে কিনা চেক করুন। Render-এর CRON_SECRET-এর সাথে মিল আছে কিনা দেখুন।

## ❌ Products show হচ্ছে না
**সমাধান:** 
1. "Scrape All" button click করুন
2. Logs check করুন (`/api/logs`)
3. Render dashboard-এ Logs tab-এ error আছে কিনা দেখুন

## ❌ Server slow load হচ্ছে (১ম বার)
**কারণ:** Free tier-এ server sleep mode থেকে wake up হতে ৩০ সেকেন্ড লাগে।
**সমাধান:** Cronjob #3 (Keep-Alive) add করুন — তাহলে কখনো sleep হবে না।

---

# 📊 Cost Summary (চিরকাল ফ্রি!)

| Service | Plan | দাম |
|---|---|---|
| GitHub | Free | $0 |
| Supabase | Free (500MB DB, 5GB bandwidth) | $0 |
| Render | Free (750 hours/month) | $0 |
| cron-job.org | Free (50 cronjobs) | $0 |
| **মোট** | | **$0/month** |

---

# 🚀 Future Upgrades (যদি কখনো লাগে)

| Need | Upgrade To | দাম |
|---|---|---|
| Server sleep না হওয়া | Render Starter plan | $7/mo |
| বেশি storage (>500MB) | Supabase Pro | $25/mo |
| Custom domain | Render free তে support করে | $0 |
| 100% uptime + speed | Hostinger VPS | ৳৪০০/mo (bKash) |

---

# 📞 Help

কোনো সমস্যা হলে:
1. Render dashboard → **Logs** tab → error দেখুন
2. Browser console (F12) → error দেখুন
3. `/api/status` endpoint check করুন

**আপনার TrendScope এখন live এবং কাজ করছে! 🎉**
