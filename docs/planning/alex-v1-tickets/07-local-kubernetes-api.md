# 07: API 在本機 Kubernetes 可部署與恢復

**Status:** ready-for-agent

**GitHub:** https://github.com/husky0787/Alex/issues/9

## Parent

[Alex 第一版規格 #2](https://github.com/husky0787/Alex/issues/2)

## What to build

使用者透過本機 Kubernetes 中的 API 存取應用；操作者能觀察部署健康狀態與 Pod 故障恢復。

## Acceptance criteria

- [ ] 使用可重現的 API 容器及明確版本，完成 Deployment、Service 與本機入口。
- [ ] 驗證登入、授權、健康檢查與資源 requests/limits；設定及秘密與映像分離。
- [ ] 刪除測試 Pod 後服務能恢復；部署失敗版本時能返回上一個可用版本。
- [ ] 使用相容資料庫與隔離服務完成本機 smoke test，記錄與 AWS 尚未驗證的差異。

## Blocked by

- [#3](https://github.com/husky0787/Alex/issues/3) — [Alex v1/01] 讓登入與 API 錯誤有正確結果
