# 手動發布至臨時 EKS

[English](README.md) | 繁體中文

**目前狀態（2026-11-01）：**發布與復原 workflows 已停用。驗收成功後，雲端基礎設定（IAM roles、GitHub OIDC provider、ECR repositories）已刪除。重新啟用前須先重建，見[清理／重建紀錄](../../docs/verification/aws-account-cleanup.zh-TW.md)。

完成一次性基礎設定後，在 **main** 開啟 **Actions → Release to temporary EKS → Run workflow**。流程會找出完全相同程式版本的成功 CI、下載已測試映像、建立真實 EKS、驗證發布／回滾、保存可公開證據，再刪除臨時 stack 與本次映像 tags。push／merge 只執行 CI。映像 artifacts 過期時，須先完整重跑 CI。

這是一次性的 **API 發布驗收環境**。PostgreSQL、JWT、AWS transport fixtures 隔離在 EKS 中。它不部署前端、不切換正式流量、不存取原 Aurora／代理秘密、不執行付費代理，也不執行 schema migrations。真實應用整合另有 Task9／11 證據，不應合併宣稱為完整應用的正式 CD 驗收。

## 一次性基礎設定

1. 確認目前 AWS 帳號、credit／到期日／適用服務及下方費用窗口，保留原本 default AWS CLI 身分。使用操作人員的短期憑證規劃 `terraform/12_cd`，不要把靜態金鑰存進 GitHub。確認 GitHub OIDC provider ARN 指向實際存在的 provider；若不存在，須在明確的管理範圍下建立。`terraform/12_cd` 只接收 ARN，不會建立 provider，先前使用的 provider 已刪除。EKS 與 managed-node service-linked roles 也是前提，須確認仍存在。
2. 執行 `terraform init`、`terraform test`，檢閱只針對此模組的 `terraform plan`，再 apply 已檢閱計畫。將此模組 state 私下備份。它建立 IAM roles／policies 與一個空 ECR repository，不會建立運行中的叢集。
3. 建立 GitHub environment `alex-eks-cd`，限制部署分支為 `main`，將 `terraform output -json github_variables` 輸出放入該 environment。透過 GitHub API 確認實際 repository 的不可變 OIDC subject；fork 須使用自己的身分設定 Terraform trust policy。
4. 設定 repository variable `ALEX_CD_RECOVERY_ENABLED=true`。確認兩個 workflows 已在預設分支，先重新啟用 recovery，再啟用 release。Recovery 不應等待人工核准，避免中斷的叢集持續計費。
5. 檢閱最新帳單後，將 environment variable `ALEX_CD_APPROVED_UNTIL` 設為距發布開始 2 至 24 小時內的 UTC ISO 時間。這是操作人員檢閱的時間窗口，**不是 AWS 強制費用上限**。未展示時保持未設定；recovery 不需要此窗口。

部署角色只可在 `alex-cd-api` 發布／刪除映像、操作 `alex-cd-window` stack、傳遞專屬 CloudFormation role 及查詢其 EKS 叢集。它也可模擬專屬 CloudFormation role 的權限，在建立收費資源前檢查節點／叢集角色的查詢前提。

CloudFormation 可建立有標籤的網路資源與指定名稱的 EKS 叢集，並傳遞固定的 node／cluster roles，不能任意建立 IAM roles。EKS 也會檢查呼叫者的 EC2 啟動權限：只允許所屬 templates／subnets、t3.medium On-Demand、IMDSv2 及 hop limit 1。AMI、security group、ENI、volume 權限限定於區域啟動相依資源；並非所有生成的 worker 資源都必須帶有 template 的歸屬標籤。

Node roles 使用標準 EKS worker／CNI／ECR policies。這些基礎設施權限比 namespace 內的應用部署權限更廣，檢閱時須據此評估。標準 CNI policy 尤其具有帳號範圍的 ENI 權限。Worker launch template 要求 IMDSv2 與 hop limit 1；應用 Pods 不使用 host networking 或 service-account tokens，以阻止一般 Pods 取得 node 憑證。若 node 或具特權 CNI 遭入侵，仍可能使用較廣權限；本設計不宣稱 CNI 達到 VPC 範圍的最小權限。

## 發布證據與失敗處理

- Gate 檢查 repository、main 分支、event、workflow 路徑、完整 Git SHA、整體成功狀態、必要 jobs 與未過期 artifact 身分。建立資源前會檢查 Docker archive checksums、image IDs 與 source labels。
- Kubernetes API 只允許 runner IPv4 `/32`，nodes 也使用 private endpoint。工作負載只暴露 ClusterIP，runner 使用可重新連線的 loopback port-forward。沒有 load balancer、NAT gateway 或 persistent volumes。
- 驗證健康候選版本、已授權的跨使用者／錯誤 smoke、刻意缺少的 digest、恢復後版本，以及未變更的 fixture database schema。即使回滾成功，失敗 rollout 仍回傳非零退出碼；只有明確預期的故障演練可將此結果視為驗收成功。
- `eks-cd-acceptance` 與 `eks-cd-cleanup` artifacts 只含可公開 JSON 摘要，保留 14 天。GitHub run 連結精確來源 CI run。私密 kubeconfig、fixture 密碼、signer 與原始診斷資料留在 runner。
- Cleanup 是使用新 OIDC 憑證的獨立 job。`workflow_run` recovery 處理取消／失敗的 run，每小時排程處理到期資源。三條路徑共用 concurrency group，且拒絕操作不屬於自己的資源。
- GitHub 排程可能延遲／停用，雲端刪除也可能失敗；自動清理與 recovery 不保證準時完成。清理失敗應立即檢查；stack 還存在時不可停用 recovery。

## 復原

先檢查 **Recover temporary EKS** 與精確 `alex-cd-window` stack 的 CloudFormation events。手動 recovery workflow 只清理已到期 stack。已授權操作人員可在可信 checkout 恢復已知完成的 run：

```text
uv run --no-project deploy/cd/lifecycle.py recover --completed-run GITHUB_RUN_ID --completed-attempt RUN_ATTEMPT
```

由私密 bootstrap 輸出設定 `ALEX_CD_CF_ROLE_ARN` 與 `ALEX_CD_REPOSITORY`，並使用限定範圍的角色憑證。不要與 Actions 同時執行 recovery，也不要手動移除歸屬標籤或強制刪除原應用資料。若 stack 不存在但指定 EKS 叢集仍在，工具會回報孤立資源，並在缺少歸屬證據時拒絕刪除，需人工檢查。ECR 的一日 lifecycle 是孤立映像的備援清理，不會立即刪除。

一般每次 run 的清理會保留 bootstrap IAM／OIDC 參照與空 ECR repository；2026-11-01 帳號清理另外移除了這些基礎設定。日後要清理 bootstrap，須先確認 runtime 資源不存在，再檢閱其刪除計畫。共用 OIDC provider 不由此模組管理，須有自己的歸屬／重建生命週期。

## 費用窗口

規劃一次短時間執行，設定兩小時資源到期標記，並以包含清理／復原緩衝的三小時情境估算。文件原估算採標準支援 EKS US$0.10／小時；另外計入兩台 t3.medium、40 GiB EBS、兩個 public IPv4、映像儲存、傳輸及可能的 burst CPU 費用。此流程沒有 NAT／LB 或付費模型呼叫。

首次執行前應更新區域 EC2／EBS 價格及帳號既有用量，US$5 是調查門檻，不是費用保證。2026-10-31 API 查價得到 t3.medium US$0.0416／小時；三小時 control plane、nodes、IPv4 與 40 GiB gp3 約 US$0.60。加上 registry、傳輸、burst／緩衝可預留 US$2。帳號其他服務另計。環境卡住或重複執行可能超出估算；兩小時到期標籤本身不會停止計費。

來源：[EKS 定價](https://aws.amazon.com/eks/pricing/)、[public IPv4 定價](https://aws.amazon.com/vpc/pricing/)、[刪除 EKS](https://docs.aws.amazon.com/eks/latest/userguide/delete-cluster.html)、[GitHub workflow events](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows)。

## 本機檢查

```text
uv run --no-project -m unittest discover -s deploy/cd -p 'test_*.py' -v
uv run --no-project deploy/ci/test_release.py
terraform -chdir=terraform/12_cd init
terraform -chdir=terraform/12_cd test
```

真實 EKS 發布、回滾與清理於 2026-11-01 通過，精確來源版本、修正的失敗與獨立資源檢查見[驗收紀錄（英文）](../../docs/verification/manual-eks-cd.md)。發布窗口已關閉，bootstrap 也已移除。再次發布前須重建、更新 GitHub environment、檢閱成本、重新啟用 recovery／release 並開啟新窗口。單元測試不能取代雲端驗收。
