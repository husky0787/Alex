# 03: 行情失敗或品質不合格時可追查與恢復

**Status:** completed (merged 2026-10-25)

完成依據：[PR #16](https://github.com/husky0787/Alex/pull/16)；[驗證與限制](../../verification/task-03-quality-recovery.md)。以下保留原驗收條件；雲端部署狀態以驗證文件為準。

**GitHub:** https://github.com/husky0787/Alex/issues/5

## Parent

[Alex 第一版規格 #2](https://github.com/husky0787/Alex/issues/2)

## What to build

操作者能找到失敗原因，修正後重跑；使用者不會讀到遭隔離或虛構的價格。

## Acceptance criteria

- [ ] 驗證必填欄位、symbol/date、有限正數價格、OHLC 關係、非負有限小數成交量（保留來源的小數股精度）。
- [ ] 壞資料隔離並保留原因與原始物件關聯；有效資料可處理，執行狀態揭露部分失敗。
- [ ] 對限流與暫時錯誤採有上限的重試；驗證 429、timeout、異常 schema 和資料庫寫入失敗。
- [ ] 相同內容重跑不增加重複資料；並行執行及失敗重試不會提前更新完成進度。
- [ ] 資料修訂有可追溯版本；行情服務與分析路徑移除隨機價格 fallback，既有無來源價格不冒充已驗證資料。

## Blocked by

- [#4](https://github.com/husky0787/Alex/issues/4) — [Alex v1/02] 一筆真實行情從來源出現在畫面
