# 重現投資組合展示

[English](README.md) | 繁體中文

**目前狀態（2026-11-01）：**原 Aurora cluster／admin secret 及所有展示 AWS workers 已刪除。執行下方 preflight 前，須重建相容的應用資料庫基礎設施並初始化 schema。舊 `.env` ARNs 與 `.local/showcase/` ledgers 屬於歷史紀錄，開始新一輪前先檢查並封存。不要對已刪除 cluster 重跑舊資料庫 cleanup。見[清理／重建紀錄](../../docs/verification/aws-account-cleanup.zh-TW.md)。

此操作文件將真實 Next.js／FastAPI／Clerk 流程連接到隔離 AWS workers 與獨立應用資料庫，不取代原應用。行情資料庫、前端與 API 在本機執行；Task9 的另一種部署方式見 [EKS 文件](../eks/README.zh-TW.md)。先閱讀[驗收紀錄](../../docs/verification/task-11-showcase.md)與[雲端費用窗口](../../docs/verification/task-11-cloud-window.md)（英文）。

## 前置條件與歸屬

使用 Python 3.12、PATH 中的 uv、Node 24／npm、PostgreSQL 17 工具、支援瀏覽器登入的 AWS CLI，以及 Terraform 1.7+（驗收版本 1.16.4）。只有重建 Reporter dependency ZIP 時需要 Linux amd64 Docker；已私下移轉且獨立核對 hash 的既有 ZIP 可重用。映像不得含 Docker 憑證或 AWS 秘密。

需要已建立且支援 Data API 的 Aurora PostgreSQL cluster、admin secret、允許 localhost 的真實 Clerk application，以及 Massive／Polygon key。驗收紀錄中的操作 profile 為 `alex-task09`，一般 runtime 用 `default`。請設定自己帳號的 profiles，或修改工具中明確指定的 profile，不要複製他人憑證。

`.local/`、`.planning/`、`.env`、database dumps 與全部 Terraform state 必須私下保存；`.local/` 只允許目前使用者存取。POSIX 可先設定 `umask 077`，Windows 則維持只允許擁有者的 checkout ACL。換機前安全備份 state。Fresh clone 不含 state 或 live resources。未核對歸屬／state 前，不可 apply 到既有 guide2／3 資源；此驗收要求它們原本不存在。

Windows 執行 cloud helpers 前設定 `PYTHONUTF8=1` 與 `PYTHONIOENCODING=utf-8`，避免 AWS CLI JSON 報告文字在 console 編碼中損壞。PowerShell 必須為完整 Terraform 參數加引號，例如 `'-var-file=../../.local/showcase/workers.tfvars.json'`。

## 建置與初始化

以下都從 repository 根目錄執行。大寫 placeholder 必須換成實際值。

1. 同步鎖定的 API workspace：`uv sync --project backend --locked --package api`。建立私密 `.local/showcase/admin-input.json`，內容為 `{"cluster":"YOUR_CLUSTER_ARN","secret":"YOUR_ADMIN_SECRET_ARN","database":"alex"}`，只有資源參照，不是密碼。執行 `uv run --project backend --locked --package api --with sqlparse deploy/showcase/environment.py preflight --admin-target .local/showcase/admin-input.json`，私下檢閱盤點、credit 適用性、用量與費用窗口；此腳本不是費用上限。
2. 執行 `uv run --project backend --locked --package api --with sqlparse deploy/showcase/environment.py database`，只建立 `alex_task11`、`alex_task11_app`、`alex-task11/database`。若已有初始化 ledger，應停下檢查，不代表可覆寫。再執行 `uv run --project backend --locked --package api deploy/showcase/environment.py market --pg-bin PG_BIN_DIRECTORY`，於 55441 建立具 SCRAM 保護的 loopback cluster；Linux 不可用 OS root 執行。
3. 在被忽略的根目錄 `.env` 設定 `MASSIVE_API_KEY` 或支援的舊名 `POLYGON_API_KEY`，見[供應商設定（英文）](../../backend/market_data/README.md)。執行 `uv run --project backend --locked --package api deploy/showcase/refresh_market.py`，確認每個標的都成功覆蓋；不得以生成價格取代取得失敗的行情。
4. 建置 Linux dependencies：`uv run --project backend/reporter --locked backend/reporter/package_docker.py`，不要帶 `--deploy`。輸出 `backend/reporter/reporter_lambda.zip`，記錄 SHA256，再執行 `uv run --no-project deploy/showcase/build_workers.py --runtime-zip RUNTIME_ZIP --runtime-sha256 EXPECTED_SHA256`。五個 workers 共用鎖定的 Reporter dependencies，覆蓋目前 worker／database／research 原始碼。相依套件變更時須重建並實測 runtime；ZIP hash 相符本身不能證明相容。
5. 用 `uv run --project backend/ingest --locked backend/ingest/package.py` 建置 ingestion，分別初始化 `terraform/2_sagemaker`、`terraform/3_ingestion`、`terraform/11_showcase`。Guide2 的私密 tfvars 設定 `aws_region="us-east-1"`；Guide3 另需 `sagemaker_endpoint_name="alex-embedding-endpoint"`。

各目錄執行 `terraform -chdir=terraform/DIRECTORY init`。若 provider 無法讀 CLI 瀏覽器 profile，可用 `uv run --no-project deploy/showcase/terraform_run.py DIRECTORY plan -out=../../.local/showcase/NAME.tfplan`，只將憑證匯入 child process。私下用 `terraform -chdir=terraform/DIRECTORY show PLAN_PATH` 檢閱 saved plans；plan JSON 與 outputs 可能含秘密。要求只有新增變更，且 apply 前確認所有名稱不存在。用同一 wrapper apply 已檢閱計畫，不做未檢閱的 blanket apply。驗收當時 guide2／3 分別新增 6／20 個資源。

Guide2／3 apply 後，執行 `uv run --project backend --locked --package api deploy/showcase/configure.py --clerk-jwks-url https://YOUR_CLERK_DOMAIN/.well-known/jwks.json`，產生 `.local/showcase/workers.tfvars.json`。以該 var-file plan `11_showcase`，檢閱其 23 個新增資源後 apply saved plan。工具不會啟動 Researcher 或排程。

## 驗證真實流程

1. `uv run --project backend --locked --package api deploy/showcase/verify_cloud.py workers` 檢查已部署 ZIP hashes 與 native imports，不執行付費代理，並私下保存 queue／worker outputs。
2. 依 [Task6 操作紀錄（英文）](../../docs/verification/task-06-aws-acceptance.md) 取得一筆真實且具來源的 Researcher 紀錄，或私下恢復先前擷取內容。提供一個元素的 JSON array，含 `id`、`text`、`metadata.sources` 及原 URL／擷取時間，不得虛構來源。執行 `uv run --project backend/reporter --locked deploy/showcase/verify_cloud.py research --captured-research PRIVATE_RECORD_JSON`；會真實匯入、embedding、向量檢索，保留原身分／時間，但不是再跑一次 Researcher 瀏覽器。
3. 被忽略的 `frontend/.env.local` 填入相符 `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` 與 `NEXT_PUBLIC_API_URL=http://localhost:8000`。啟動 `uv run --project backend --locked --package api deploy/showcase/api.py`，將 logs 私下重新導向。另一 terminal 進入 `frontend/` 執行 `npm ci`、`npm run dev -- --hostname 127.0.0.1`。若無法使用 telemetry 設定，可設 `NEXT_TELEMETRY_DISABLED=1`。API 啟動監聽前會驗證專屬資料庫／secret。
4. 用一般瀏覽器開啟 `http://localhost:3000/dashboard`，透過 Clerk 登入。不可停用驗證或匯出瀏覽器 tokens。`/api/user` 成功且隔離 DB 恰有一個 user 後，執行 `uv run --project backend --locked --package api deploy/showcase/fixture.py`。它建立有標示的虛構持倉（AAPL 1 股、MSFT 2 股、現金 1,000）並做一次真實 Tagger 分類；拒絕覆寫帳戶或重跑已有 fixture ledger。
5. 開啟 Market Data 檢查 AAPL 來源／日期／歷史，再到 Advisor Team **只按一次 Start New Analysis**。確認保存的報告、圖表與退休輸出。執行 `uv run --project backend --locked --package api deploy/showcase/verify_analysis.py`，驗證快照、圖表值及研究來源。Pending／failed 不算成功；queue 在一次 receive 失敗後送入 DLQ，應先檢查而非無限重試模型。

展示必須標明範例持倉。唯讀驗證不需要再呼叫分析。Tagger 是獨立前置步驟，Planner 協調 Reporter、Charter、Retirement。應如實記錄驗證失敗及後續成功請求，不可將所有 403 都判定為過期。

## 封存與清理

停止新增分析請求。先跑 `uv run --no-project deploy/showcase/cleanup.py archive`，再跑 `uv run --no-project deploy/showcase/archive_cloud.py`，保留私密 table exports、PostgreSQL custom dump、限定範圍 CloudWatch logs 與帳號／模型窗口用量觀察。保留原始行情與 artifact hashes。公開證據須移除 tokens、Clerk／user IDs、AWS account numbers、原始研究及財務帳戶總額。

停止所屬 API process。依 **11_showcase → 3_ingestion → 2_sagemaker** 反序，用相同 variables 建立 saved `terraform plan -destroy`，對照建立計畫及盤點檢閱完整資源清單後 apply。驗收 state 含 23+20+6 個資源，不包含原應用。不要執行課程的整體資料庫 destroy。若非空且屬於本任務的 vector index／bucket 阻止刪除，先封存，再只移除已檢閱且確認歸屬的內容，重試同一計畫。

Workers 移除後跑 `uv run --no-project deploy/showcase/cleanup.py database`。工具要求相符封存／ownership markers，只移除專屬 database／login，將 secret 排入七天恢復期刪除，並驗證原 database 與 Lambda 版本。可在重新核對每個剩餘物件標記後恢復部分刪除。用 `uv run --no-project deploy/showcase/cleanup.py market` 停止本機 DB，並只停止展示啟動的前端／瀏覽器輔助 processes。這是單次展示清理流程；此次帳號全面清理已移除原應用及剩餘 secrets，不可直接重跑上述舊環境操作。

檢查三份 Terraform states 為空，並獨立驗證資源不存在。SageMaker 可能在 Terraform 外建立 `/aws/sagemaker/Endpoints/alex-embedding-endpoint`；先封存，只有名稱與建立時間確認為此次驗收所屬才刪除。一般單次展示清理須保留預先存在的 service-linked roles、原應用及獨立 Task10 IAM／OIDC／空 ECR；2026-11-01 帳號清理已另外移除這些專案設定。

## 保存內容與測試

公開成果是程式碼、操作文件、去識別結果及短版**證據導覽**，不是永久 endpoint。導覽根據檢查結果產生，明確不是 Brave 畫面錄影。私密 dumps／logs／來源回應保留本機，直到安全移轉或刻意刪除；單純 clone GitHub 不能恢復它們。日後使用自己的 keys 與已檢閱 plans 重建及重驗。

離線檢查：`uv run --no-project -m unittest discover -s deploy/showcase -p 'test_*.py' -v`；`terraform -chdir=terraform/11_showcase test` 使用 mock provider，不建立 AWS 資源。前端回歸測試於 `frontend/` 執行 `npm run test:dashboard`。上方 cloud verifier 會連線真實 AWS；其中 fixture 與 analysis 步驟才會呼叫付費代理。
