# Alex：從課程應用延伸為具驗證證據的工程專案

[English](README.md) | 繁體中文

Alex 以 Ed Donner 的 **AI in Production** 課程為起點。個人延伸包含可追溯的每日行情、可恢復的 ETL、固定分析價格、研究來源追蹤、Kubernetes 維運及受控發布。目標是可重現的工程展示，不是交易建議，也不宣稱承載正式流量。

**目前狀態（2026-11-01）：**驗收後已移除盤點到的所有 AWS 專案資源，包括原應用與部署基礎設定。CI 仍啟用，雲端發布／復原已停用。以下結果為歷史工程證據；再次執行完整應用前須重建雲端相依服務，見[清理與重建紀錄](../verification/aws-account-cleanup.zh-TW.md)。

建議從[架構](architecture.zh-TW.md)、[短版證據導覽](walkthrough.mp4)、[英文導覽逐字稿](walkthrough.md)、[應用驗收紀錄（英文）](../verification/task-11-showcase.md)及[重建／清理操作文件](../../deploy/showcase/README.zh-TW.md)開始。影片展示已記錄的結果，不是使用者瀏覽器錄影；要體驗互動功能，須依操作文件重建並執行應用。

## 課程基礎與個人新增內容

| 課程基礎 | 個人工程貢獻 | 證據（英文） |
| --- | --- | --- |
| Next.js、Clerk、FastAPI、帳戶與持倉介面 | 保留 API 錯誤狀態／JSON；顯示日期的行情歷史；Dashboard 登入狀態競爭回歸測試 | [Task1](../verification/task-01-api-errors.md)、[Task4](../verification/task-04-universe-history.md)、[Task11](../verification/task-11-showcase.md) |
| Aurora 與 AWS 基礎設施範例 | API／ETL 專屬角色、具有歸屬標記的驗收資料庫、受檢閱的生命週期與清理 | [Task9](../verification/task-09-eks-acceptance.md) |
| 投資組合代理協調 | 強制使用已驗證價格快照；代理共用相同且不可變的價格基礎；禁止虛構備用價格 | [Task5](../verification/task-05-analysis-price-snapshots.md)、[Task11](../verification/task-11-showcase.md) |
| Researcher、embedding、向量搜尋 | 來源 URL／擷取時間／研究 ID 契約、讀回回執、明確回報研究不可用 | [Task6](../verification/task-06-aws-acceptance.md) |
| 原流程沒有個人的每日行情 ETL | 20 個標的、90 天回補、原始資料封存、隔離、冪等、持久恢復、覆蓋檢查及排程 | [Task2](../verification/task-02-verified-price.md)、[Task3](../verification/task-03-quality-recovery.md)、[Task8](../verification/task-08-scheduled-etl.md) |
| Serverless 應用部署 | 本機 Kubernetes 與限時 EKS 上的 FastAPI Deployment／ETL CronJob；工作負載權限分隔、HPA、告警、回滾 | [Task7](../verification/task-07-local-kubernetes-api.md)、[Task9](../verification/task-09-eks-acceptance.md) |
| 手動部署腳本 | 固定版本的 CI gates、不可變映像、OIDC／ECR、手動啟動臨時 EKS 發布與失敗復原 | [Task10](../verification/task-10-cicd.md)、[手動 EKS CD](../verification/manual-eks-cd.md) |

## 驗證證據對照

| 能力 | 實際驗證內容 | 範圍與限制 |
| --- | --- | --- |
| 真實資料端到端 | Massive → 驗證 → 儲存 → API → 有日期的介面；20 個標的共 1,280 筆行情 | 每日行情，非即時報價；可追蹤供應商來源不代表獨立認證價格正確 |
| 不合格資料隔離 | 刻意注入的不合格回應被拒絕並隔離；有效價格筆數不變 | 故障注入，不宣稱是供應商實際事故 |
| 缺日與恢復 | 缺漏區間偵測／回補、中斷工作恢復；保留錯誤原因與品質失敗 | Task3／4／8 記錄整合測試與故障演練 |
| 重複執行安全性 | EKS 手動 Job 與 CronJob 控制器執行後，價格／觀測筆數仍為 1,280／1,280 | 不代表所有雲端訊息具 exactly-once 傳遞保證 |
| 告警送達 | ETL 失敗與 ALB 健康 target 歸零，實際通知送達 SQS | 驗收接收器，非值班團隊反應時間測量 |
| 回滾 | 無效映像／digest 發布失敗，恢復前一健康版本且授權 smoke 通過 | EKS 操作演練、託管 runner CI 演練、手動 EKS CD |
| 完整應用分析 | 一般 Brave／Clerk 登入、虛構持倉、真實 SQS／Planner／Bedrock 專責代理、具來源研究及已保存介面結果 | Task11 使用本機 API／行情 DB；EKS 另由 Task9 驗證 |

## 面試時的簡要說法

「我將課程的多代理投資組合應用延伸為具有每日行情管線與 Kubernetes 部署的專案。我實作來源追蹤、資料品質檢查、隔離與回補、不可變價格快照及受控 CI/CD。在限時 AWS 驗收中，驗證了 1,280 筆行情、工作負載權限隔離、真實告警送達與失敗發布回滾；另以真實 Clerk 登入完成並保存報告、圖表及退休分析。」

使用連結中的證據解釋故障與取捨。不要描述為永久在線、高流量、每次合併即部署 EKS、已完成財務稽核，或完全從零開發。EKS CD 使用手動觸發與隔離 API 相依服務，不是完整應用的正式流量切換。最終帳單核對仍獨立追蹤。原 AWS 應用也已在帳號清理時移除。
