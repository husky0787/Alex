# 原 Alex AWS 費用資源清理 — 2026-11-01

[English](original-alex-cost-cleanup.md) | 繁體中文

這是**第一輪清理的歷史紀錄**。同一天稍後，使用者將授權擴大到全部 AWS 專案；下方當時保留的專案資源已陸續移除。目前狀態請看[帳號全面清理](aws-account-cleanup.zh-TW.md)。

使用者當時明確授權停止原 Alex 網站／API／分析，並刪除原資料庫，不保留 final snapshot 或資料庫備份。這一輪只處理 Alex，排除 devops 與 turing-eye。

## 當時移除內容

- 原 Aurora instance 與 cluster。AWS 要求先啟動已停止的 cluster 才能刪除 instance。刪除時略過 final snapshot，並要求移除 automated backups。七個自動 snapshot 條目在 cluster 刪除後曾短暫留在目錄，之後消失；原 cluster 沒有保留 automated backup 或 manual／final snapshot。
- 兩個原 Alex S3 buckets：前端靜態檔案及 Lambda deployment ZIPs。刪除前，48 個 object versions 全部封存在本機，核對大小與 SHA256，適用時也比對來源 ETags。
- 六個原 Alex Lambda log groups，先將事件封存在本機再刪除。
- 兩個 Alex CloudWatch dashboards，先保存定義再刪除。

原資料庫 credential secret 當時排入七天恢復窗口刪除，已不是 active secret。恢復窗口不會保留已刪除資料庫或其備份。後續帳號全面清理已將該 secret 強制刪除，請勿將本段當作目前可恢復狀態。

## 當時停用及保留內容

- CloudFront 已 disabled，設定完成部署。
- API Gateway execute-api endpoint 已 disabled，stage 使用 auto-deploy。
- 六個原 Lambda reserved concurrency 均為 0；Planner SQS event-source mapping 已 disabled。
- 可重用 IAM、空 CI／CD ECR repositories 與不活動的應用設定當時仍保留。已檢查部署中沒有運行的 Alex EKS、SageMaker endpoint、App Runner、NAT gateway、load balancer 或 VPC Interface Endpoint。

其他專案的兩台 stopped EC2、30／100 GiB 磁碟與 turing-eye 固定 IP 當時不在清理範圍，因此仍可能計收儲存／IP 費用；後續已另行刪除。歷史用量可能延後入帳；此紀錄是資源狀態核對，不宣稱整個 AWS 帳單為零。

## 證據與重現

[獨立稽核 JSON](original-alex-cost-cleanup.json) 於 2026-11-01 03:18:04 UTC（台北 11:18:04）通過，包含當時排除的專案主機、磁碟及固定 IP 檢查。

私密設定、部署檔案與日誌封存位於操作電腦 `.local/cost-cleanup-20261101/`，不納入 Git。此次清理沒有新建資料庫備份。更早驗收紀錄屬於歷史證據，其中「保留原資料庫」描述的是另行授權清理之前的狀態。

原網站無法再使用舊 database／buckets 執行。再次使用前須重新建立應用相依服務、恢復部署設定並初始化新資料。先檢閱既有 Terraform state 與 proposed changes；原 module 5／6／7／8 state 不在此 checkout，所以當時沒有使用 blanket Terraform destroy。獨立手動 EKS CD 在這一輪曾保留 reusable bootstrap，發布窗口關閉；後續全面清理也已移除該 bootstrap。
