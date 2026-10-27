# Alex 第一版任務

已於 2026-10-25 發布並驗證：1 張規格、11 張子任務、13 條原生 blocking relationships。

規格：[Alex 第一版：可信行情、資料工程與 Kubernetes](https://github.com/husky0787/Alex/issues/2)；[本機規格](../alex-v1-spec.md)。

清單編號是本地規劃順序；GitHub 編號以各列的 #number 為準。ready-for-agent 表示需求已具體化，仍須等待所有 blockers 完成。

1. **[讓登入與 API 錯誤有正確結果](https://github.com/husky0787/Alex/issues/3)** — 已完成；PR #14 已合併。[本機驗收條件](01-api-error-contract.md)

2. **[一筆真實行情從來源出現在畫面](https://github.com/husky0787/Alex/issues/4)** — 已完成；PR #15 已合併。[本機驗收條件](02-first-verified-price.md)

3. **[行情失敗或品質不合格時可追查與恢復](https://github.com/husky0787/Alex/issues/5)** — 已完成；PR #16 已合併。[本機驗收條件](03-quality-recovery.md)

4. **[20 支標的的 90 天歷史可回補與查詢](https://github.com/husky0787/Alex/issues/6)** — 已完成；[PR #17](https://github.com/husky0787/Alex/pull/17) 已合併；依賴 #5 已完成。[本機驗收條件](04-universe-history.md)；[驗證紀錄](../../verification/task-04-universe-history.md)

5. **[分析報告使用已驗證的行情](https://github.com/husky0787/Alex/issues/7)** — 已實作並驗證，等待 PR 審查與合併；分支 `feat/task-05-analysis-price-provenance`；依賴 #5 已完成。[本機驗收條件](05-analysis-price-provenance.md)

6. **[研究內容可寫入、檢索並用於報告](https://github.com/husky0787/Alex/issues/8)** — GitHub #8；Blocked by：#7。[本機驗收條件](06-research-chain.md)

7. **[API 在本機 Kubernetes 可部署與恢復](https://github.com/husky0787/Alex/issues/9)** — GitHub #9；Blocked by：#3。[本機驗收條件](07-local-kubernetes-api.md)

8. **[Kubernetes 每日排程及手動回補共用 ETL](https://github.com/husky0787/Alex/issues/10)** — GitHub #10；Blocked by：#6, #9。[本機驗收條件](08-scheduled-etl.md)

9. **[在限時 EKS 環境跑通應用與 ETL](https://github.com/husky0787/Alex/issues/11)** — GitHub #11；Blocked by：#7, #10。[本機驗收條件](09-bounded-eks-validation.md)

10. **[一次版本更新可自動檢查、部署並回滾](https://github.com/husky0787/Alex/issues/12)** — GitHub #12；Blocked by：#11。[本機驗收條件](10-delivery-rollback.md)

11. **[完成可重現的作品展示與驗收紀錄](https://github.com/husky0787/Alex/issues/13)** — GitHub #13；Blocked by：#8, #12。[本機驗收條件](11-release-evidence.md)

2026-10-25 核對：#3–#5 已關閉；#6、#7、#9 的前置依賴已完成。下一步依規劃順序為任務 4（#6）。下方任務的 Blocked by 保留依賴關係，不表示被引用的 issue 仍開啟。GitHub Issues 是任務狀態的主要來源；本目錄保存規格、驗收條件與發布對照，換機接續見 [進度與設定入口](../alex-v1.md)。
