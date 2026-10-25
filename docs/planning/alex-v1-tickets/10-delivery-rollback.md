# 10: 一次版本更新可自動檢查、部署並回滾

**Status:** ready-for-agent

**GitHub:** https://github.com/husky0787/Alex/issues/12

## Parent

[Alex 第一版規格 #2](https://github.com/husky0787/Alex/issues/2)

## What to build

提交新版本後可重現測試與映像建置，部署至驗收環境；失敗版本可回到上一個健康版本。

## Acceptance criteria

- [ ] CI 執行行情契約、API 授權與前端檢查，失敗時不部署。
- [ ] 用固定映像 digest 部署；CI 存取 AWS 使用短期身分和最小權限。
- [ ] 以手動觸發或受控環境啟動需要雲端費用的部署；測試不默認呼叫付費模型。
- [ ] 驗證一次成功發布及一次失敗回滾，資料庫變更採向後相容方式。
- [ ] CI 和部署紀錄能追溯 commit、測試結果、映像與目標環境。

## Blocked by

- [#11](https://github.com/husky0787/Alex/issues/11) — [Alex v1/09] 在限時 EKS 環境跑通應用與 ETL
