# Alex｜多代理投資組合分析平台

[English](README.md) | 繁體中文

Alex 以課程中的投資組合分析應用為基礎，延伸出可驗證的每日行情、可恢復的 ETL、固定分析價格快照、研究來源追蹤、Kubernetes 維運及受控發布流程。部署完成後，已登入使用者可以管理持倉，並取得持久保存的報告、圖表與退休推算。

**部署狀態（2026-11-01）：**AWS 專案資源已移除，包括原應用與 CI/CD 的 IAM、OIDC、ECR 基礎設定。目前沒有運行中的 AWS 展示站。GitHub CI 仍啟用，雲端發布及復原工作已停用。程式碼與歷史驗收證據保留，詳見[清理紀錄與重建前提](docs/verification/aws-account-cleanup.zh-TW.md)。

**閱讀入口：**[包含資料工程與 Kubernetes 的完整架構](docs/showcase/architecture.zh-TW.md) · [45 秒證據導覽](docs/showcase/walkthrough.mp4) · [重現與清理流程](deploy/showcase/README.zh-TW.md) · [真實登入驗收紀錄（英文）](docs/verification/task-11-showcase.md)。

基礎來自 Ed Donner 的 *AI in Production* 課程。文件分別說明課程功能與個人新增內容、真實測試與故障注入資料，以及歷史驗收與目前部署狀態。驗收環境採臨時建立方式，專案不提供永久在線的公開展示站。

## 架構

總覽包含應用、資料工程、Kubernetes 與發布能力；再從下方四張細節圖展開實作。各環境並非同時部署，詳見[部署範圍](docs/showcase/architecture.zh-TW.md)。點擊預覽可開啟 Archify 互動版。

[![互動圖](docs/diagrams/architecture.svg)](https://husky0787.github.io/Alex/diagrams/architecture.html)

[互動圖 →](https://husky0787.github.io/Alex/diagrams/architecture.html) · [PNG](docs/diagrams/architecture.png)

**詳細圖（互動版）：**

- [行情資料工程](https://husky0787.github.io/Alex/diagrams/data-engineering.html)
- [Kubernetes 部署](https://husky0787.github.io/Alex/diagrams/kubernetes.html)
- [分析請求時序](https://husky0787.github.io/Alex/diagrams/analysis.html)
- [CI 與手動 CD](https://husky0787.github.io/Alex/diagrams/cicd.html)

[全部五張圖的導覽](https://husky0787.github.io/Alex/)

## 系統如何運作

1. 已登入使用者透過 API 提交分析請求。
2. API 將持倉與已驗證的每日價格固定在工作快照中，把工作寫入 Aurora，再將工作 ID 送往 SQS。
3. Planner 使用同一份快照，協調 Reporter、Charter 與 Retirement。已驗收流程中的 Tagger 分類是獨立前置步驟；缺少必要價格時會明確失敗，不會自行生成價格。
4. Reporter、Charter、Retirement 將各自結果存入獨立工作欄位。前端定期查詢工作狀態，完成後顯示結果。
5. 另一條可選排程讓 Researcher 透過 Playwright MCP 搜集市場背景，將嵌入後的文件加入 S3 Vectors 知識庫。

## 工程重點

- **非同步協調：**SQS 將請求處理與長時間代理執行分開；超過重試次數的訊息保留在 dead-letter queue。
- **專責工作：**Planner 將文字報告、圖表、退休推算交給可獨立部署的 Lambda；Tagger 另行分類標的。
- **資料工程與維運：**每日行情取得、品質隔離、回補與冪等處理；API／ETL Kubernetes 工作負載、限時 EKS 驗收、專屬 IAM、告警及回滾。
- **手動 EKS 發布：**相同程式版本的 CI 成功後，才可推送已測試映像、建立臨時 EKS、驗證授權、測試故障回滾並清理所屬資源。詳見[操作文件](deploy/cd/README.zh-TW.md)與[驗收紀錄（英文）](docs/verification/manual-eks-cd.md)。
- **持久且分隔的輸出：**各代理寫入 Aurora 工作中的獨立 JSONB 欄位，不依賴記憶體內的共用結果合併器。
- **AI 整合：**OpenAI Agents SDK 透過 Amazon Bedrock 執行；Tagger 使用結構化輸出，其他代理使用各自的資料及檢索工具。
- **知識檢索：**SageMaker 對研究內容產生 embedding，S3 Vectors 建立索引供語意檢索。
- **基礎設施即程式碼：**Terraform 元件各有獨立本機 state，可分別部署與清理。
- **可觀測性：**CloudWatch 記錄 Lambda 執行；設定可選環境變數後可使用 LangFuse tracing。

## 技術組成

| 領域 | 技術 |
| --- | --- |
| 應用 | Python 3.12、FastAPI、Pydantic、OpenAI Agents SDK |
| AI 與檢索 | Amazon Bedrock、SageMaker、S3 Vectors、Playwright MCP |
| 運算與整合 | AWS Lambda、API Gateway、SQS、EventBridge、ECR |
| 資料 | Aurora Serverless v2 PostgreSQL、RDS Data API、Secrets Manager |
| 前端 | Next.js、React、TypeScript、Clerk、Recharts |
| 發布與觀測 | Terraform、Docker、CloudFront、CloudWatch、LangFuse |

## 本機執行

已驗收的個人專案流程請依[隔離展示操作文件](deploy/showcase/README.zh-TW.md)。該流程與以下原應用指令都必須先重建 AWS 相依服務；單純啟動本機伺服器不會恢復完整分析功能。以下指令也不會建立展示環境或行情資料庫。

### 前置條件

- Node.js 20+ 與 npm
- [uv](https://docs.astral.sh/uv/)
- Docker Desktop
- Terraform 1.5+
- 已設定 AWS CLI，且登入身分有權存取已建立的開發資源

### 設定

由 [`.env.example`](.env.example) 建立根目錄 `.env`，填入後端與 AWS 整合值。建立 `frontend/.env.local`，填入 Clerk keys 與本機 API URL。兩個檔案均不可提交。

### 啟動應用

```bash
cd scripts
uv run run_local.py
```

此工具啟動 `http://localhost:8000` 的 FastAPI 與 `http://localhost:3000` 的 Next.js。互動 API 文件位於 `http://localhost:8000/docs`。

### 執行測試

測試已部署資源前，先執行使用 mock 的本機測試：

```bash
cd backend
uv run test_simple.py
```

AWS 資源設定完成後，再測試已部署流程：

```bash
cd backend
uv run test_full.py
```

各代理目錄也提供自己的 `test_simple.py` 與 `test_full.py`。

## 部署至 AWS

以下為原課程部署順序。個人延伸功能請選擇[展示](deploy/showcase/README.zh-TW.md)、[EKS](deploy/eks/README.zh-TW.md)、[CI](deploy/ci/README.zh-TW.md) 或[手動 EKS CD](deploy/cd/README.zh-TW.md) 的操作文件與對應 state，不要將所有模組視為同一環境一起 apply。

Terraform 刻意拆成獨立元件。每個元件有自己的本機 state，apply 前須由範例建立對應的 `terraform.tfvars`。

依相依順序部署：

1. `terraform/2_sagemaker`
2. `terraform/3_ingestion`
3. `terraform/4_researcher`
4. `terraform/5_database`
5. `terraform/6_agents`
6. `terraform/7_frontend`
7. `terraform/8_enterprise`

套用代理基礎設施前，使用 Docker 打包及更新代理 Lambda：

```bash
cd backend
uv run package_docker.py
uv run deploy_all_lambdas.py
```

建置並部署 API／前端基礎設施與靜態網站：

```bash
cd scripts
uv run deploy.py
```

部署工具會檢查 Docker、Terraform、npm 與 AWS CLI。apply 前應檢閱 Terraform plan 與 AWS 費用；暫停開發時清理未使用元件，尤其是資料庫。

## 安全與使用範圍

- API Lambda 存取資料前會驗證 Clerk JWT。
- 資料庫憑證放在 AWS Secrets Manager，Lambda 權限定義於 IAM policies。
- Pydantic 與代理輸出驗證限制輸入及生成資料。
- CloudWatch 支援故障調查；設定可選環境變數後，LangFuse 可記錄代理執行。
- Terraform 中的 Researcher Function URL 設為公開；對不受信任流量開放前，須加入限制或驗證。
- Alex 供資訊用途，不提供財務、投資或交易建議。

## 儲存庫目錄

```text
backend/      Lambda functions, agents, API, ingestion, and shared database code
frontend/     Next.js application and Clerk integration
terraform/    Independently managed AWS infrastructure components
scripts/      Local development and frontend deployment entry points
guides/       Architecture and operating reference material
```

## 授權

採用 [MIT License](LICENSE)。
