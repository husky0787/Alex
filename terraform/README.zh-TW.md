# Terraform 基礎設施

[English](README.md) | 繁體中文

本目錄包含 Alex Financial Planner 的 Terraform 設定。

**目前狀態（2026-11-01）：**已部署的 AWS 專案資源已移除，包括原應用與 CI/CD 基礎設定。設定檔保留供重建使用。本機 state／saved plans 可能仍描述已在 Terraform 外部刪除的資源；應先私下備份 state，比對新的 plan 與實際資源，處理差異後才重建。不要套用舊 saved plan 或沿用已刪除資源的 outputs。先選定部署路徑及前提，見[清理／重建紀錄](../docs/verification/aws-account-cleanup.zh-TW.md)。

## 結構

課程各部分有獨立目錄：

- **`2_sagemaker/`**：SageMaker serverless embedding endpoint（Guide 2）。
- **`3_ingestion/`**：S3 Vectors、Lambda、API Gateway 文件匯入（Guide 3）。
- **`4_researcher/`**：研究代理的 container-image Lambda 與可選排程（Guide 4）。
- **`5_database/`**：Aurora Serverless v2 PostgreSQL 與 Data API（Guide 5）。
- **`6_agents/`**：代理協調用的 Lambda（Guide 6）。
- **`7_frontend/`**：API Lambda 與前端基礎設施（Guide 7）。
- **`8_enterprise/`**：CloudWatch 監控 dashboards（Guide 8）。

個人延伸使用獨立模組：`6_research_acceptance/`、`9_eks/`、`10_ci/`、`11_showcase/`、`12_cd/`。應依對應操作文件執行，不要將所有目錄一起部署成同一環境。

## 設計選擇

### 為什麼分開目錄？

1. **教學清楚：**課程各指南對應自己的 Terraform 目錄。
2. **獨立部署：**可個別部署，不必一起套用其他模組。
3. **縮小變更範圍：**各部分的變更以自身 state 管理。
4. **循序學習：**按指南選擇下一個模組，降低意外部署後續部分的機會。

### 為什麼使用本機 state？

1. **簡單：**不必先管理遠端 S3 state bucket。
2. **減少前置資源：**state backend 本身不需要額外基礎設施。
3. **費用：**不產生 state 檔案的 S3 儲存費。
4. **保密：**state 已列入 `.gitignore`，仍須妥善保護及備份。

## 使用方式

每個模組分別執行：

```bash
# Navigate to the specific part's directory
cd terraform/2_sagemaker  # (or 3_ingestion, 4_researcher, etc.)

# Initialize Terraform (only needed once per directory)
terraform init

# Review what will be created
terraform plan

# Deploy the infrastructure
terraform apply

# When done with that part (optional)
terraform destroy
```

## 環境變數

部分設定需要 `.env` 的值：

- `OPENAI_API_KEY`：研究代理（Part 4）。
- `ALEX_API_ENDPOINT`：文件匯入 API Gateway endpoint（Part 3）。
- `ALEX_API_KEY`：匯入 API key（Part 3）。
- `AURORA_CLUSTER_ARN`：Aurora cluster ARN（Part 5）。
- `AURORA_SECRET_ARN`：Secrets Manager ARN（Part 5）。
- `VECTOR_BUCKET`：S3 Vectors bucket 名稱（Part 3）。
- `BEDROCK_MODEL_ID`：代理使用的 Bedrock model（Part 6）。

## State 管理

- 每個目錄有自己的 `terraform.tfstate`。
- State 放在本機，不使用 S3 backend。
- 所有 `*.tfstate` 都排除於 Git 之外。
- 重大變更前先私下備份 state。

## 正式環境的考量

目前結構以學習用途為主。正式使用時可評估：

- **Remote State：**使用有存取控制的遠端 backend，依 Terraform／backend 版本設定適當 locking。
- **Modules：**共用不同環境的設定。
- **Workspaces：**管理 dev、staging、prod。
- **CI/CD：**自動化部署管線。
- **Terragrunt：**協調多個 Terraform 模組。

## 排查問題

1. **State 不一致：**各目錄有獨立 state。確定資源歸屬後，才 import 既有資源：

   ```bash
   terraform import <resource_type>.<resource_name> <resource_id>
   ```

2. **缺少相依服務：**確認已完成需要的前置指南，並填好必要環境變數。
3. **清理後重建：**保留私密 state 備份，核對實際資源歸屬；apply 前檢閱所選模組的新 plan。若資源仍在，只以其所屬 state 的已檢閱計畫刪除。不要刪除 state 來隱藏差異或留下無人管理的資源。
