# 04: 20 支標的的 90 天歷史可回補與查詢

**Status:** ready-for-agent

**GitHub:** https://github.com/husky0787/Alex/issues/6

## Parent

[Alex 第一版規格 #2](https://github.com/husky0787/Alex/issues/2)

## What to build

使用者選擇支援標的後能查看最近 90 個曆日內的日行情走勢；操作者可補回漏掉的交易日。

## Acceptance criteria

- [ ] 記錄固定 20 支美股／ETF 清單與資料來源；前端清楚標示支援範圍。
- [ ] 回補最近 90 個曆日內交易日，與日常擷取使用同一個 pipeline 入口。
- [ ] 週末、休市、資料尚未發布與應有但缺漏分開處理；測試時區及 DST 邊界。
- [ ] 歷史圖表按日期排序；無資料區間不造值或悄悄填零。
- [ ] 驗證中斷後續跑與重複回補不漏資料、不產生重複觀測值。

## Blocked by

- [#5](https://github.com/husky0787/Alex/issues/5) — [Alex v1/03] 行情失敗或品質不合格時可追查與恢復
