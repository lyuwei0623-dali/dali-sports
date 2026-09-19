# V20 CLEAN：盤口可靠性與永久快照

- 新增完整市場驗證與同莊家成對價格選取。
- 足球支援 `RCD Mallorca`、`Mallorca`、`Real Oviedo`、`Oviedo` 等來源別名。
- 缺少市場時不再刪除已保存參考盤口；過期歷史價格不會冒充即時盤。
- 對未開賽的缺盤賽事可選擇一次受控補抓，額度與錯誤重試皆受限。
- MLB、Football 快照可存入 PostgreSQL，避免 Streamlit 重新部署後遺失。
- 會員端改以只讀服務組合，無資料庫寫入、無外部 API 呼叫。
- Base Model、SUPER、亞洲盤結算與人工發布優先規則維持。
