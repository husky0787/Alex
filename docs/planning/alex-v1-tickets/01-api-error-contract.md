# 01: 讓登入與 API 錯誤有正確結果

**Status:** completed (merged 2026-10-25)

完成依據：[PR #14](https://github.com/husky0787/Alex/pull/14)；[驗證與限制](../../verification/task-01-api-errors.md)。以下保留原驗收條件；雲端部署狀態以驗證文件為準。

**GitHub:** https://github.com/husky0787/Alex/issues/3

## Parent

[Alex 第一版規格 #2](https://github.com/husky0787/Alex/issues/2)

## What to build

使用者登入後能載入自己的資料；未登入、沒有權限或不存在的 API，回傳正確錯誤而非首頁 HTML。

## Acceptance criteria

- [ ] 重現並修正 API 錯誤被轉成首頁的路徑；有效頁面仍能載入。
- [ ] 驗證未登入拒絕、跨使用者資料拒絕、有效使用者資料載入。
- [ ] 留下本機自動化結果；雲端回應於短期驗收時再核對。

## Blocked by

None (completed)
