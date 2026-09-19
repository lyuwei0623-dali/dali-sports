# V22：自動推薦盤口完整度修正

覆蓋以下四個檔案：

- `durable_store.py`
- `odds_ingestion.py`
- `mlb_pre_release_module.py`
- `football_module.py`

不需要重跑 Supabase SQL，不會清除既有快照，也不會重算或覆蓋已發布的人工校正。

## 修正內容

1. 自動盤口主來源缺少任一標準市場時，對該批缺盤賽事執行一次受限的跨地區補抓，並要求獨贏、讓分、大小三類市場，而不是只補所有缺盤賽事共同缺少的單一類別。
2. MLB 使用 `MLB_ODDS_FALLBACK_REGIONS`（預設 `eu`）；足球使用 `FOOTBALL_ODDS_FALLBACK_REGIONS`（預設 `uk`）。舊的 `ODDS_FALLBACK_REGION` 仍可作為相容設定，但空白時會使用各運動安全預設。
3. 所有補抓市場仍需通過同一莊家、雙方完整、盤口線一致、價格有效、隊名與開賽時間匹配的驗證；不會假造盤口或改變 MLB SUPER、足球亞洲盤、+EV 或結算規則。
4. 保留 V21 Supabase revision 快取，避免管理員輸入時反覆傳輸整份資料庫。

跨地區補抓可能增加 The Odds API 額度使用量，但最多只對缺盤事件再發出一次請求。若來源本身沒有提供任何可驗證盤口，APP 仍會如實標示 PASS，而不會產生假推薦。
