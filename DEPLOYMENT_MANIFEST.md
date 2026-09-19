# V20 CLEAN 部署清單

請將本壓縮檔的內容完整覆蓋 GitHub 專案根目錄。不要混用 V12～V19 的任何 Python 檔案。

必須上傳：

- `app.py`
- `app_services.py`
- `admin_snapshot_ui.py`
- `backup_tools.py`
- `core_shared_ui.py`
- `database_setup.sql`
- `durable_store.py`
- `football_display.py`
- `football_module.py`
- `integration_adapter.py`
- `live_calculator.py`
- `live_ui.py`
- `manual_odds.py`
- `member_experience.py`
- `member_links.py`
- `member_release_service.py`
- `mlb_pre_release_module.py`
- `odds_ingestion.py`
- `source_health.py`
- `requirements.txt`
- `logo.png`

`README.md` 是設定說明；`tests/` 僅供驗證，可一併保留在 GitHub。

上傳後先設定 `DATABASE_URL` 並在 Supabase 執行 `database_setup.sql`，再重新部署。未完成永久資料庫設定前，請勿用這版建立正式賽前紀錄。
