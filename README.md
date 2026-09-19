# 維大力體育APP｜V20 CLEAN

這是完整根目錄版本。它保留既有 MLB Base Model、MLB SUPER 盤口、足球亞洲盤結算、會員端唯讀及人工發布優先；本次調整集中在盤口取得與賽前快照保存。

## 上線前必做：永久資料庫

Streamlit 本機檔案會因重新部署或重啟遺失。請先建立 Supabase PostgreSQL 專案，於 SQL Editor 執行 `database_setup.sql`，再將**伺服器端** PostgreSQL 連線字串放入 Streamlit Secrets：

```toml
DATABASE_URL = "postgresql://..."
REQUIRE_DURABLE_STORAGE = "1"
```

不可把 `DATABASE_URL` 放進 GitHub。不可使用瀏覽器端 anon key，也不要用 Service Role key 取代資料庫連線字串。

首次部署時，管理員登入後會建立 MLB 與 Football 的資料表。完成後再執行「建立／更新歷史資料」及「立即執行自動快照」。會員頁面只讀取已保存快照，不呼叫外部 API、不重算、不寫入。

## 其他 Secrets

```toml
APP_MEMBER_PASSWORD = "..."
APP_ADMIN_PASSWORD = "..."
APP_MEMBER_LINK_SECRET = "..."
THE_ODDS_API_KEY = "..."
API_FOOTBALL_KEY = "..."
FOOTBALL_DATA_API_KEY = "..."
FOOTBALL_SEASONS_JSON = '{"eng.1":2026,"esp.1":2026,"ger.1":2026,"ita.1":2026,"fra.1":2026,"uefa.champions":2026}'

# Optional: 只在主區域缺少市場時，補抓一次。會使用額外 The Odds API 額度。
FOOTBALL_ODDS_REGIONS = "eu"
ODDS_FALLBACK_REGION = ""
```

`ODDS_FALLBACK_REGION` 預設留白。確定額度足夠並確認該區域可用後才設定，例如 `uk`；程式只會對「未開賽且缺類別」的賽事補抓一次。

## 每日操作

1. 管理員於台灣時間 19:30 前按 MLB、Football 的「立即執行自動快照」。
2. 確認完整賽表及盤口來源狀態。
3. 若你的會員平台盤不同，逐場輸入人工盤口並發布。
4. 已發布人工版本優先；比賽開始後只顯示最後已保存的賽前紀錄，不會以賽後盤重算。

## 資料安全規則

- 單一市場必須完整：足球獨贏為主／和／客三方；讓分與大小為完整雙方。
- 不會把不同莊家的半套盤口混成一組，也不會產生中位數假盤。
- 本次抓取缺少某市場時，已保存資料會留在歷程；逾時的歷史價格不會當成最新可下注盤。
- The Odds API 認證失敗、額度受限不重試；5xx／網路錯誤僅重試一次。
- PostgreSQL 寫入失敗時操作失敗，不會靜默退回 Streamlit 臨時 SQLite。

## 本機測試

```bash
python -m pip install -r requirements.txt
python -m unittest discover -s tests -q
```

完整套件已通過 63 項測試。測試不使用你的 API 金鑰或真實會員資料；部署後仍需由管理員建立一次當日快照驗證各資料來源。
