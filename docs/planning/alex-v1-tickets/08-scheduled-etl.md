# 08: Kubernetes 每日排程及手動回補共用 ETL

**Status:** ready-for-agent

**GitHub:** https://github.com/husky0787/Alex/issues/10

## Parent

[Alex 第一版規格 #2](https://github.com/husky0787/Alex/issues/2)

## What to build

每日排程自動更新行情，操作者亦能以手動 Job 回補；使用者可看見更新結果和新鮮度。

## Acceptance criteria

- [ ] 以 CronJob 執行每日任務，以 Job 執行回補，兩者呼叫相同 pipeline 入口。
- [ ] 依已核對的供應商發布時間和交易日曆決定執行日期，不將排程觸發日直接當交易日。
- [ ] 排程防重疊之外，驗證人工 Job 與 CronJob 同時執行仍遵守資料層冪等及鎖定。
- [ ] 紀錄 run_id、處理／隔離筆數、執行時間、失敗原因；缺漏或失敗能觸發可驗證的告警事件。
- [ ] API 或前端可查看最近行情日期和執行結果；預先設計的漏跑能透過回補恢復。

## Blocked by

- [#6](https://github.com/husky0787/Alex/issues/6) — [Alex v1/04] 20 支標的的 90 天歷史可回補與查詢
- [#9](https://github.com/husky0787/Alex/issues/9) — [Alex v1/07] API 在本機 Kubernetes 可部署與恢復
