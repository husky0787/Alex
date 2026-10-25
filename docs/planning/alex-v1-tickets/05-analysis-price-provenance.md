# 05: 分析報告使用已驗證的行情

**Status:** ready-for-agent

**GitHub:** https://github.com/husky0787/Alex/issues/7

## Parent

[Alex 第一版規格 #2](https://github.com/husky0787/Alex/issues/2)

## What to build

投資組合分析使用資料庫內有效價格，讓使用者知道報告引用的價格日期和是否過期。

## Acceptance criteria

- [ ] Planner 改讀正式行情，而非每次分析直接擷取後覆寫價格。
- [ ] 最新有效價格落後應有交易日時，畫面及報告明確顯示 stale 與實際日期。
- [ ] 任一必要持倉沒有可信價格或不在支援範圍時，拒絕產生完整估值報告並列出受影響標的。
- [ ] 工作結果保留使用的價格快照或不可變版本關聯，後續價格修訂不改寫舊報告依據。
- [ ] 驗證正常、過期、缺漏與跨使用者資料隔離情境。

## Blocked by

- [#5](https://github.com/husky0787/Alex/issues/5) — [Alex v1/03] 行情失敗或品質不合格時可追查與恢復
