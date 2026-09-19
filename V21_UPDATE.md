# V21：Supabase 操作速度修正

只需覆蓋 `durable_store.py`。

本更新不變更 Supabase 資料表、不清除資料、也不重算已發布的賽事。它保留既有的 PostgreSQL 資料庫內容，並改為以小型 revision 查詢確認資料是否更新；同一個 APP 執行程序內的重複讀取不再下載或上傳整份 SQLite 資料庫影像。

已發布的人工快照仍優先於自動快照；會員端仍是唯讀，不會抓取 API 或重新計算。
