# 06: 研究內容可寫入、檢索並用於報告

**Status:** ready-for-agent

**GitHub:** https://github.com/husky0787/Alex/issues/8

## Parent

[Alex 第一版規格 #2](https://github.com/husky0787/Alex/issues/2)

## What to build

一則 Researcher 產生的研究摘要可保存、建立向量、檢索，並在分析報告中辨認其來源。

## Acceptance criteria

- [ ] 先以本機替代服務驗證流程；AWS 驗收前核對 credit 適用性、到期日、既有費用與恢復資源估算。
- [ ] 確認 Guide 2–4 所需資源實際狀態，恢復缺少的部分；只處理為驗收所需範圍。
- [ ] 保留研究來源 URL、擷取時間及研究識別碼；驗證一則已知研究內容的入庫與檢索。
- [ ] 研究或檢索失敗時，報告明確標示研究內容不可用，不偽稱已有研究依據。
- [ ] 保存一次雲端研究到報告的驗證證據；同時記錄實際測試費用與資源清單。

## Blocked by

- [#7](https://github.com/husky0787/Alex/issues/7) — [Alex v1/05] 分析報告使用已驗證的行情
