# 02: 一筆真實行情從來源出現在畫面

**Status:** completed (merged 2026-10-25)

完成依據：[PR #15](https://github.com/husky0787/Alex/pull/15)；[驗證與限制](../../verification/task-02-verified-price.md)。以下保留原驗收條件；雲端部署狀態以驗證文件為準。

**GitHub:** https://github.com/husky0787/Alex/issues/4

## Parent

[Alex 第一版規格 #2](https://github.com/husky0787/Alex/issues/2)

## What to build

使用者可以看到一支股票某個交易日的有效 OHLCV、來源及日期；操作者可追溯至保存的原始回應。

## Acceptance criteria

- [ ] 確認供應商帳號可取得免費日資料與目標歷史範圍；不新增付費方案。
- [ ] 透過同一個 pipeline 入口取得資料，保存原始回應、轉換、驗證、寫入歷史表及執行紀錄。
- [ ] API 與前端呈現行情日期、來源及新鮮度；沒有有效資料時顯示 unavailable。
- [ ] 使用隔離的資料庫驗證儲存與查詢；真實來源 smoke test 保存不含憑證的證據。

## Blocked by

- [#3](https://github.com/husky0787/Alex/issues/3) — [Alex v1/01] 讓登入與 API 錯誤有正確結果
