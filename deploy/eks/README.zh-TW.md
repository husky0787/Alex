# 限時 EKS 驗收

[English](README.md) | 繁體中文

**目前狀態（2026-11-01）：**EKS 驗收資源、原 Aurora cluster、管理員秘密與自訂資料庫 security group 都已刪除。執行 `prepare.py` 前，須重建並驗證下列資料庫／網路前提；舊 ARNs、kubeconfig 與部署 outputs 不再指向運行中的環境。見[清理／重建紀錄](../../docs/verification/aws-account-cleanup.zh-TW.md)。

所有指令由儲存庫根目錄執行。這是八小時驗收窗口，不是永久在線部署。先閱讀[費用與資源歸屬範圍（英文）](../../docs/verification/task-09-cloud-window.md)。Terraform state、憑證、原始資料、簽章金鑰與私人證據放在忽略的本機路徑，不可提交。

## 架構

[![互動圖](../../docs/diagrams/kubernetes.svg)](https://husky0787.github.io/Alex/diagrams/kubernetes.html)

[互動圖 →](https://husky0787.github.io/Alex/diagrams/kubernetes.html) · [PNG](../../docs/diagrams/kubernetes.png)

API 與 ETL 使用不同 ServiceAccounts、Pod Identity roles、Secrets Manager 值與 PostgreSQL roles。API 可讀已驗證價格但不可修改；ETL 不可修改應用使用者／帳戶。raw 與 quarantine 物件放在同一私有資料 bucket 的不同 prefixes；前端 bucket 獨立。隔離物件是不可變 manifest，指向原始回應與其 digest，不是重複的前端檔案。

CloudFront 終止使用者端 HTTPS，其私有 VPC 連線以 HTTP 到達 internal ALB；PostgreSQL 使用驗證憑證的 TLS，因此不是每一跳都有 TLS。新 private origin subnets 沒有網際網路路由。Workers 使用既有 public subnets 與 public IPv4 存取外部相依服務，沒有公開 SSH 或 API ingress。Kubernetes API 只允許操作人員的 `/32`。部署流程以唯讀方式檢查並保留既有 Aurora VPC TCP5432 規則。

## 前置條件與產物

- `alex-task09` profile 的 AWS CLI 瀏覽器登入憑證、`default` 操作 IAM 身分、Terraform >=1.7、相容 Kubernetes 1.35 的 kubectl、Docker Linux/amd64、Python 3.12 與 uv。
- 已建立的 `alex-aurora-cluster`、其 admin secret、default VPC 中分屬兩個受支援 AZ 的 public subnets，以及既有 TCP5432 VPC ingress 規則。`prepare.py` 檢查這些假設並拒絕重疊 origin CIDRs。apply 前檢查輸出；這是課程環境的明確前提，不是通用 VPC 建立工具。
- 最新帳單／credit 與已檢閱的完整估算。US$20 範例只適用文件中的小型窗口；變更容量／流量須重算。
- 本機 `.env` 內的 `MASSIVE_API_KEY`（也支援舊名 `POLYGON_API_KEY`），不可放進 Docker context 或 manifests。
- 已驗證 imports 與「研究不可用」路徑的 Linux Reporter ZIP。可用 `uv run backend/reporter/package_docker.py` 重建（需要 Docker，不使用部署選項）；記錄 SHA256 並在 Lambda Python 3.12 runtime 測試後再使用。預設使用 task06 產物，也可明確提供其他已驗證產物：

```text
uv run --project backend --locked --package api deploy/eks/manage.py reporter --source PATH_TO_VERIFIED_ZIP --sha256 VERIFIED_SHA256
uv run --project backend --locked --package api deploy/eks/test_cloud.py
terraform -chdir=terraform/9_eks init
terraform -chdir=terraform/9_eks test
uv run --no-project deploy/eks/prepare.py
```

`prepare.py` 在 `.local/eks/task09/` 產生私密 `acceptance.tfvars.json` 與即時價格／網路證據，選取不在不支援的 `use1-az3` 的兩個既有 public subnets、檢查未使用 origin CIDRs，並設定八小時期限。`ExpiresAt` 不是自動清理機制；操作人員須在窗口內保持可處理並完成清理。

可在任何已授權 Docker 電腦建置 API 映像：

```text
docker build -t alex-api:task09 -f backend/api/Dockerfile backend
```

只有允許清單中的原始碼會進入映像。RDS 公開 trust bundle 來自 [AWS](https://truststore.pki.rds.amazonaws.com/global/global-bundle.pem)，AWS 輪替憑證時須刻意更新。建置使用固定 Python base digest 與鎖定的 uv 相依套件；push 前執行不需憑證的 import 檢查。使用 `aws ecr get-login-password` 與 Docker `--password-stdin` 登入本任務的 ECR，使用獨立 Docker config，push 後登出。Kubernetes 資源必須使用 **ECR digest**，不能使用可變 tag。

## 部署與初始化

只在基礎設施操作選用 `AWS_PROFILE=alex-task09`，保留 default IAM profile。PowerShell 的 Terraform 參數若含點或斜線，須將完整參數加引號。

```text
terraform -chdir=terraform/9_eks plan -input=false -var-file=../../.local/eks/task09/acceptance.tfvars.json -out=../../.local/eks/task09/acceptance.tfplan
terraform -chdir=terraform/9_eks apply -input=false ../../.local/eks/task09/acceptance.tfplan
terraform -chdir=terraform/9_eks output -json deployment
```

以 UTF-8 將最終 output object 存為 `.local/eks/task09/deployment.json`。使用 `aws eks update-kubeconfig --name alex-task09 --region us-east-1 --profile default --kubeconfig .local/eks/task09/kubeconfig` 建立 kubeconfig。操作人員只取得此新叢集的管理與精確叢集 `DescribeCluster` 權限。工具優先使用 `KUBECTL` 指定路徑，否則使用 PATH 中的 `kubectl`；全部使用此隔離 kubeconfig。

```text
uv run --project backend --locked --package api deploy/eks/manage.py secrets
uv run --project backend --locked --package api deploy/eks/manage.py jwks
uv run --project backend --locked --package api deploy/eks/manage.py render --image ECR_REPOSITORY_AT_SHA256
uv run --project backend --locked --package api deploy/eks/manage.py bootstrap
kubectl --kubeconfig .local/eks/task09/kubeconfig apply -f .local/eks/task09/manifests.json
kubectl --kubeconfig .local/eks/task09/kubeconfig -n alex-cloud rollout status deployment/api
```

秘密初始化會拒絕已有版本的 secret。Bootstrap 拒絕已存在的驗收資料庫，建立帶歸屬標記的資料庫／roles，並在成功或失敗後刪除暫時 Job／ServiceAccount／ConfigMap。部分完成的 bootstrap 須先檢查，不可當作 reset 直接重跑。秘密值不進入 Terraform state 或 Kubernetes manifests。AWS CLI 請求輸入使用本機暫存檔，於 `finally` 刪除；以目前使用者的檔案權限保護被 Git 忽略的 state 目錄。

## 驗收與回滾

CronJobs 起初為 `suspend: true`。先執行涵蓋最新已發布交易日的限量真實回補，再跑 daily Job，確認重複執行不新增重複 observations。要驗證排程，可暫時改成下一分鐘、取消 suspend，記錄控制器建立的 Job 及結果，再恢復正式的 `15 0 * * *`、`America/New_York` 排程，或清理前先 suspend。供應商節流為每個標的 13 秒，20 個標的需要數分鐘。

```text
uv run --project backend --locked --package api deploy/eks/manage.py backfill --from YYYY-MM-DD --to YYYY-MM-DD
uv run --project backend --locked --package api deploy/eks/manage.py daily
uv run --project backend --locked --package api deploy/eks/manage.py monitor
uv run --project backend --locked --package api deploy/eks/verify_api.py
uv run --project backend --locked --package api deploy/eks/verify_schedule.py
uv run --project backend --locked --package api deploy/eks/verify_permissions.py
uv run --project backend --locked --package api deploy/eks/verify_operations.py scaling
uv run --project backend --locked --package api deploy/eks/verify_operations.py recovery
uv run --project backend --locked --package api deploy/eks/verify_operations.py rollback
uv run --project backend --locked --package api deploy/eks/verify_operations.py etl-alert
uv run --project backend --locked --package api deploy/eks/verify_operations.py alarm
```

`verify_api.py` 使用本機持有的 signing key 與隔離叢集的公開 JWKS，驗證 HTTPS JSON 錯誤、無效／過期／偽造 JWT 拒絕、帳戶／工作歸屬，以及真實 SQS／Lambda 消費的 AAPL 快照。這不是 Clerk 瀏覽器登入測試。Reporter 儲存明確標示研究不可用的持倉摘要；全部五個代理及付費研究／模型呼叫不在此窗口的 SQS 測試範圍。

`verify_schedule.py` 自動執行一個手動 daily Job 與一個控制器 Job，記錄身分與前後價格／observation 筆數，再恢復原排程／suspension。`verify_permissions.py` 在一次性 API／ETL Pods 中以各自 ServiceAccount 與 secret 執行 `verify_workload.py`，其他測試輸入只有 ARN 與 bucket 名稱。禁止的 AWS 操作必須遭拒。ETL probe 寫入標記為 `task09_fault_injection` 的刻意不合格回應，檢查 quarantine 並確認有效價格筆數不變，不發布合成的有效價格。

檢查 `kubectl top pods`、HPA 即時 metrics 與負載造成的副本變化。刪除一個 API Pod，記錄替代 Pod readiness。只在任務擁有的 Deployment 引入不可用映像、記錄失敗，再執行 `kubectl rollout undo deployment/api` 並等待 ready。告警驗收須觀察真實 ETL／ALB health 失敗透過 SNS 送到 SQS，恢復服務前保存時間與事件。

`verify_operations.py` 依序自動執行以上檢查。Recovery 要求新 Pod UID、正確副本數及所有運行中 Pods Ready。Alarm 演練暫時移除 HPA、將 API scale 到 0，在 `finally` 恢復，再觀察 CloudWatch 回到 OK。服務 metric 發布會增加超過兩個 60 秒 period 的延遲，觀察上限為十分鐘。告警 consumers 應依序執行，避免消費彼此證據。

在已具備原應用的驗收環境，既有 API 路由是整個流程的回復目標。不修改正式 DNS／CloudFront；用戶端明確選用新 endpoint，切回即可恢復原路徑。任務 Deployment 自身也可用 Kubernetes revision history 回滾。此次清理後，若要重現這個原路由前提，須先重建原應用。

## 清理

1. Suspend 兩個 CronJobs，完成或移除只屬於它們的運行中 Jobs。將 API／ETL／metrics／告警 logs、S3 raw／quarantine 證據及資源建立時間／識別碼保存到 `.local/eks/task09/`。
2. 停止使用 API，執行 `uv run --project backend --locked --package api deploy/eks/manage.py database-cleanup`。除非指定驗收資料庫及兩個 roles 有正確歸屬 comments，否則拒絕刪除。此任務清理須保留重建前已存在的 `alex` 資料庫與 Aurora cluster。
3. 封存證據後，只清空已確認屬於任務的 S3 bucket 與 ECR repository；兩者都未啟用 Terraform force deletion。
4. 檢閱並套用**此任務** state 的 destroy plan。工作負載與暫時資料庫刪除前保留 kubeconfig。CloudFront 必須先 disable／delete，才能移除 VPC origin 與 ALB；Terraform 處理相依順序。
5. 確認沒有任務 EC2 nodes／EBS／ALB／EKS／queues／bucket／ECR。另查 task log groups 與 EKS 自動建立的服務資源，保留共用 service-linked roles。此 runbook 的 secret 刪除保留七天恢復期；比對原盤點並報告任何保留項目。2026-11-01 的帳號全面清理另已強制刪除剩餘 secrets。
6. AWS 入帳後重新查看 Billing；執行時間與估算不等於已核對的實際帳單。
