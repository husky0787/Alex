# 受控發布

[English](README.md) | 繁體中文

**目前狀態（2026-11-01）：**不使用雲端憑證的 CI 仍啟用。AWS IAM／OIDC／ECR 基礎設定已刪除，獨立雲端發布／復原 workflows 已停用。要進行 AWS 發布，須先重建這些前提，見[清理紀錄](../../docs/verification/aws-account-cleanup.zh-TW.md)。

每次 main push 與 pull request 更新都會執行 PostgreSQL 行情整合測試、API JWT／資源歸屬契約、前端 tests／lint／type-check／build 及發布失敗測試。後端與前端都成功後，CI 才由鎖定相依版本的 backend workspace 建置 API／ETL 映像。Actions 固定到 commit SHA；一般 jobs 只有 `contents: read`，沒有雲端憑證或付費模型呼叫。

CI 建置目前 checkout commit 與其 parent，記錄 Git revisions、image IDs 與 archive SHA256，再將不可變 registry digests 部署至一次性 k3d。Runner 驗證健康發布與刻意缺少的 digest。共用工具在失敗時還原前一健康 template、重新檢查 readiness，即使恢復成功仍回傳非零退出碼。兩種結果後都執行授權 smoke。工具拒絕可變 tags、不健康的回滾基準與並行 template 覆寫。映像 rollout 不執行資料庫 migration，保留 fixture 資料與 schema。

## 手動 AWS 發布

Main CI 保留已測試映像 archives 三天，不會在 push 時取得 AWS 憑證或發布。獨立的[手動 EKS workflow](../cd/README.zh-TW.md) 可將精確且成功的 main CI 版本發布至臨時真實 EKS。

Task10 原本只發布 ECR 的流程已由手動 EKS workflow 取代。`terraform/10_ci` IAM／ECR 模組仍獨立，新 CD 模組不使用或管理它；其已部署資源已在帳號清理時移除。`ALEX_RELEASE_COMMIT` 不再觸發部署。原 `acceptance.py --ecr` 操作工具仍可重現 Task10 歷史證據，但部署目標是 runner k3d，不是 EKS。

## 其他已存在的 EKS 環境

`release.py` 也接受操作人員明確指定的 EKS kubeconfig／context、namespace 與可到達的 API URL：

```text
uv run --no-project deploy/ci/release.py --kubeconfig PRIVATE_KUBECONFIG --context EXPLICIT_CONTEXT --namespace alex-cloud --image ECR_URL@sha256:DIGEST --commit FULL_COMMIT --url HTTPS_API --evidence PRIVATE_EVIDENCE_JSON
```

須在有網路連線及 namespace 範圍 API Deployment `get/patch/watch` 權限的 Linux 主機執行。目前及前一健康 API 映像都必須使用 digest。工具不建立 EKS、不修改 endpoint 防火牆、不執行 migrations；ECR-only GitHub role 刻意沒有這些權限。新 CD workflow 建立自己的隔離 EKS 驗收 stack；發布到其他既有環境仍須另外界定操作範圍。

## 資料庫與證據範圍

Schema 變更採 expand/contract：先新增相容的 nullable 欄位／資料表或相容預設值，驗證新舊映像都可使用，再於回滾窗口結束後的後續版本移除舊欄位。破壞性 migration 不與映像回滾綁定。本任務沒有 schema migration；演練會檢查 schema 相同與持久化 API 行為。

公開 Actions artifacts 只包含安全的發布 JSON，以及成功 main CI 的壓縮不可變映像 archives、checksum／commit manifest。Pull-request CI 不保留映像 archives。Artifacts 排除 fixture 憑證、簽章金鑰、kubeconfig、原始資料與全部 `.env` 檔案。Docker context 採允許清單。GitHub logs 保存測試結果，發布 JSON 記錄 commit、前／後映像、目標環境、狀態與 UTC 時間。

映像 archives 保留三天，可公開證據保留十四天；長期驗收摘要應放 `docs/verification/`。若映像已過期或移除，發布前須完整重跑所選 workflow，重新建置與驗證。

驗收 runner 在 `finally` 刪除自己的 cluster／registry，GitHub 也會回收 VM。日後清理重建的 Task10 AWS setup 時，先確認歸屬標籤，明確封存／刪除 `alex-ci-api` 映像，再檢閱並刪除**只有** `terraform/10_ci` 管理的資源。不要移除外部提供的 OIDC provider 或無關 repositories。EKS CD 有自己的[清理與 bootstrap 範圍](../cd/README.zh-TW.md)。

Terraform state 必須私下備份或安全交接，不能提交。換機後先恢復 state，或刻意 import 已確認歸屬的既有資源，再 apply。一般環境可保留空 repository 與 IAM／OIDC 而不保留計費映像儲存；此次帳號清理已將它們移除。

參考：[GitHub AWS OIDC](https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-aws)、[workflow 權限](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax)、[Kubernetes rollout](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/)。
