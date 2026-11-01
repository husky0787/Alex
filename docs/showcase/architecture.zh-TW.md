# 平台架構與部署範圍

[English](architecture.md) | 繁體中文

本圖以程式碼為依據，整合不同驗收期間各自驗證的能力，不表示所有元件曾同時部署。API 與 ETL 是 Kubernetes 工作負載，代理則以 Lambda 執行。

**部署狀態（2026-11-01）：**AWS 元件與部署基礎設定已移除。本圖說明實作與過去驗證的流程，不是目前運行中的資源清單。見[清理紀錄](../verification/aws-account-cleanup.zh-TW.md)。

[![互動圖](../diagrams/architecture.svg)](https://husky0787.github.io/Alex/diagrams/architecture.html)

[互動圖 →](https://husky0787.github.io/Alex/diagrams/architecture.html) · [PNG](../diagrams/architecture.png)

**詳細圖（互動版）：**

- [行情資料工程](https://husky0787.github.io/Alex/diagrams/data-engineering.html)
- [Kubernetes 部署](https://husky0787.github.io/Alex/diagrams/kubernetes.html)
- [分析請求時序](https://husky0787.github.io/Alex/diagrams/analysis.html)
- [CI 與手動 CD](https://husky0787.github.io/Alex/diagrams/cicd.html)

[全部五張圖的導覽](https://husky0787.github.io/Alex/)

CI 在一次性的 **runner Kubernetes** 測試映像。獨立的手動 CD 使用同一批已驗證映像封存，建立臨時 EKS API 驗收環境，搭配隔離的 PostgreSQL／JWT／AWS transport fixtures。合併到 main 只跑 CI，AWS 發布由操作人員另行啟動。此 CD 不部署 ETL／前端，也不將應用切換到 Task9 環境。見[操作文件](../../deploy/cd/README.zh-TW.md)及[歷史驗收（英文）](../verification/manual-eks-cd.md)。

Tagger 的箭頭刻意獨立：目前 Planner 協調三個分析代理，不會自動呼叫 Tagger。Reporter 除了檢索向量，也使用 SageMaker 產生查詢 embedding。

| 環境 | 執行方式與儲存 | 已觀察狀態 |
| --- | --- | --- |
| 原課程部署 | CloudFront／S3 前端、API Gateway／Lambda API、原 Aurora／Lambda | 2026-11-01 已移除，包含資料庫與雲端備份 |
| Task7／8 本機 Kubernetes | API Deployment、ETL Jobs／CronJob、本機 fixture 儲存 | 已驗證並清理；部分故障演練使用明確標記的合成輸入 |
| Task9 EKS | 真實 EKS API／ETL、S3 raw／quarantine、Aurora 行情／應用 DB、專屬 IAM | AWS 資料與維運驗證通過；67 個 Terraform 資源已清理；使用測試 JWT signer |
| Task10 CI | GitHub runner 一次性 Kubernetes、fixture DB／auth；過去真實 OIDC／ECR 發布 | CI 仍啟用；雲端 IAM／OIDC／ECR 基礎設定於 2026-11-01 移除 |
| 手動 EKS CD | 真實臨時 EKS、已測試 API 映像、隔離 PostgreSQL／JWT／AWS transport fixtures | 發布與回滾通過；執行環境及基礎設定已移除，發布／復原已停用；[歷史證據](../verification/manual-eks-cd.md) |
| Task11 展示 | 本機 Next.js／FastAPI／行情 PostgreSQL；真實 Clerk、獨立 Aurora 應用 DB、SQS、五個隔離 workers、embedding／向量資源 | 真實登入分析已驗證；AWS 相依服務已移除；[歷史證據](../verification/task-11-showcase.md) |

## 各種儲存的責任

**一般 S3** 儲存物件：行情原始回應、隔離 manifests，以及原部署中的靜態前端檔案。raw 與 quarantine prefixes 有各自的工作負載權限；只有不同 prefix 不構成存取隔離。前端檔案與資料封存使用各自部署的 bucket。Task11 的原始行情則封存在本機檔案系統。

**Aurora／PostgreSQL** 儲存可查詢且受資料約束的紀錄：使用者、帳戶、持倉、工作、固定價格快照、每日行情、觀測版本、執行與歷史。Task9 在 Aurora 使用獨立應用／行情資料庫及角色；Task11 將 Aurora 應用資料庫與本機 loopback 行情 PostgreSQL 分開。

**S3 Vectors** 是獨立的向量儲存服務／資源，即使 bucket 名稱與一般 S3 相似。它儲存研究 embedding 與已驗證 metadata，不是權威價格資料表，也不是前端 bucket。**SQS** 傳遞工作 ID 與失敗訊息，不取代持久工作狀態。

程式入口：[行情管線](../../backend/market_data/market_data/)、[API](../../backend/api/main.py)、[快照契約](../../backend/database/src/snapshots.py)、[研究契約](../../backend/research/research_chain/__init__.py)、[Kubernetes manifests](../../deploy/eks/manifests.py)、[展示隔離](../../terraform/11_showcase/main.tf)、[CI workflow](../../.github/workflows/ci.yml)。
