# AWS 帳號專案資源清理 — 2026-11-01

[English](aws-account-cleanup.md) | 繁體中文

使用者因不再使用，明確要求刪除所有剩餘 AWS 資源。此指示取代先前「只清理 Alex」的範圍，也包含 devops 與 turing-eye。沒有建立新的磁碟／資料庫快照或備份。

## 本次移除項目

- 最後兩台 EC2 與各自的 30 GiB／100 GiB gp3 磁碟。turing-eye 的 root volume 設定為主機刪除後保留，因此等磁碟 available 後另行刪除。
- turing-eye CloudFormation stack，包括 Elastic IP、instance profile、role、security group。
- 六個 Alex Lambda、一個 event-source mapping、一個 API Gateway API、兩個 SQS queues、兩個 ECR repositories、一個 CloudFront distribution。
- 四個剩餘 Secrets Manager secrets，使用不可恢復的刪除；先前恢復窗口不再適用。全程未讀取 secret values。
- 一個 RDS subnet group、兩個 Sydney 舊 App Runner log groups。
- 另外九個自訂 IAM roles、兩個 customer policies、GitHub OIDC provider、四個 EC2 key pairs、三個自訂 security groups。
- 兩個 Resource Explorer views 與 indexes。
- GitHub `cd.yml`、`cd-recovery.yml` 已停用，讀回狀態為 `disabled_manually`。只執行測試的 CI 仍啟用。

原 Alex 資料庫、資料庫備份及 S3 buckets 已於[前一輪清理](original-alex-cost-cleanup.zh-TW.md)移除。

## 獨立驗證

於 2026-11-01 05:22 UTC（台北 13:22），以新的 SDK 查詢完成涵蓋 17 個已啟用區域及相關全域 APIs 的 657 項檢查。剩餘工作負載類別為 0，查詢錯誤為 0。依 SDK endpoint metadata，14 個區域／服務組合不提供 App Runner 或 Lightsail，因此跳過；這些不列為成功檢查。

確認為空的類別包括：未終止 EC2、EBS 磁碟／快照、Elastic IP、network interfaces、NAT gateways、VPC endpoints、自訂 VPC／security groups、EKS／ECS clusters、classic／v2 load balancers、RDS instances／clusters／snapshots／保留的自動備份、Lambda、API Gateway、SQS、SNS、ECR、log groups、Secrets Manager（含待刪除）、受支援的 App Runner／Lightsail 資源、SageMaker endpoints、S3／S3 Vectors、Route 53 hosted zones、CloudFront、自訂 IAM roles／policies／instance profiles／OIDC，以及 Resource Explorer。

先前補充盤點也沒有發現 DynamoDB tables、EFS、FSx、OpenSearch、Redshift、ElastiCache、SageMaker notebooks／domains、backup vaults、自訂 KMS aliases、GuardDuty detectors 或 CloudTrail／Config recorders。

詳細私人盤點與刪除回執保留在 `.local/account-cleanup-20261101/`；公開摘要不含憑證或 secret values。見[共用 JSON 摘要](aws-account-cleanup.json)。

## 保留內容與費用意義

保留帳號／root／IAM 登入身分、Billing 設定、AWS-managed service-linked roles 與 default VPC networks。這次是工作負載清理，不是關閉 AWS 帳號。程式碼儲存庫、先前本機產物及外部服務帳號未刪除。

盤點到的持續專案基礎設施費用，從磁碟與 IPv4 約 **US$14／月**降至約 **US$0／月**。先前產生的用量與延遲入帳仍可能出現；這不是歷史帳單歸零保證，也不是全部 AWS 訂閱的完整稽核。本機 Terraform states 與舊部署 outputs 屬於歷史資料，不可盲目 apply 來恢復已刪除的基礎設施。

## 日後重建

建立資源前，先選擇需要的環境：

- **離線開發／CI：**程式碼與不使用雲端憑證的測試 workflows，可在具備文件要求的本機相依套件時使用。單純啟動完整 UI／API 不會恢復已刪除的 AWS 整合或歷史使用者資料。
- **完整應用／展示或 Task9 EKS：**重建 Aurora cluster、admin secret 與所需網路設定，初始化應用 schema，再依[展示](../../deploy/showcase/README.zh-TW.md)或 [EKS](../../deploy/eks/README.zh-TW.md) 文件操作。私密 runtime 設定須使用新 outputs；開始新驗收前先檢查舊 ownership ledgers。
- **手動 EKS API 發布：**在明確管理範圍下建立真實存在的 GitHub OIDC provider，再重建 `terraform/12_cd` 的 IAM／ECR。此模組只接收 provider ARN，不會建立 provider。更新 GitHub environment outputs、核對 AWS service-linked roles，先重新啟用 recovery 再啟用 release，並建立新的費用／發布窗口。見 [CD 文件](../../deploy/cd/README.zh-TW.md)。

任何重建前，都應安全備份既有本機 Terraform state，比對實際 AWS 盤點，再檢閱所選模組的新 plan。不要把刪除 state 當捷徑，也不要套用歷史 saved plans。CI 映像 artifacts 過期時，須重新完成一次成功 CI。此文件只記錄重建前提；更新文件時沒有重建資源或重新啟用雲端 workflows。
