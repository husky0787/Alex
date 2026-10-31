# Alex 第一版規劃

更新日期：2026-10-31。狀態：任務 1–10 的實作 PR 均已合併；任務 6 的功能驗收通過，費用核對獨立追蹤。任務 10 的 PR #24 已合併為 `7d7c5d5`，issue #12 已關閉。任務 11 在 `feat/task-11-showcase` 完成真實 Clerk 登入、完整分析、展示文件與影片、雙軸審查及隔離資源清理；接續入口為本分支的 PR／CI。GitHub Issues 是狀態主要來源。

規格：[alex-v1-spec.md](alex-v1-spec.md)。任務：[任務清單](alex-v1-tickets/README.md)。

## 已完成與接續入口

| 任務 | 已合併 PR | 驗證紀錄 |
| --- | --- | --- |
| 1：API 錯誤契約 | [#14](https://github.com/husky0787/Alex/pull/14) | [本機驗證](../verification/task-01-api-errors.md) |
| 2：真實行情從來源到畫面 | [#15](https://github.com/husky0787/Alex/pull/15) | [驗證與 63/63 AAPL 來源證據](../verification/task-02-verified-price.md) |
| 3：品質隔離與失敗恢復 | [#16](https://github.com/husky0787/Alex/pull/16) | [測試與遷移驗證](../verification/task-03-quality-recovery.md) |

任務 3 合併 commit：`49e3a4e36b260ed7bb1e6ccf9a1c8591f2a58bc9`。上述任務當時以本機測試為主；後續 AWS／EKS 驗收見任務 9。

任務 4 已於 PR [#17](https://github.com/husky0787/Alex/pull/17) 合併，commit `75f301cd94131e920f4debc2b3d9ef0a5d8b3ffe`；[驗證紀錄](../verification/task-04-universe-history.md)。

任務 5 已新增建立工作時固定的持倉與行情快照。設定完成時 `/api/analyze` 可建立使用可信價格的分析工作；缺價或不支援的必要標的會回傳 422，未設定服務仍回傳 503。四個分析 agents 均讀取同一份快照，舊工作無快照仍會被拒絕。見 [ADR 0004](../adr/0004-analysis-price-snapshots.md) 與 [驗證紀錄](../verification/task-05-analysis-price-snapshots.md)。新程式尚未部署 AWS。

任務 5 已於 PR [#18](https://github.com/husky0787/Alex/pull/18) 合併，commit `70b3201a7f3135feb277ac6b891787c1dbfc4e76`。任務 6 的本機研究來源追蹤、寫入回執與不可用處理已於 [PR #19](https://github.com/husky0787/Alex/pull/19) 合併，commit `3848f7b97998cd0360c03f7ddaca688d0c7c469e`；建置與驗收接續分支為 `feat/task-06-container-acceptance`、[PR #20](https://github.com/husky0787/Alex/pull/20)。使用者於 2026-10-31 恢復 AWS 驗收；真實研究入庫、檢索、隔離 Reporter 報告與不可用降級均已通過。任務 6 仍待實際帳單核對，見 [AWS 驗收證據](../verification/task-06-aws-acceptance.md)。

PR #20 已合併為 `52395b5208c0bd04d2bb992de314273750b48762`。任務 7 的 [PR #21](https://github.com/husky0787/Alex/pull/21) 已合併為 `72a967a`，issue #9 已關閉：本機 k3d 的登入／授權 smoke、Pod 自動重建、故障版本回滾和 readiness 恢復均通過，測試叢集已清理。見 [任務 7 證據](../verification/task-07-local-kubernetes-api.md) 與 [重現步驟](../../deploy/local/README.md)。

換機時 clone／更新本儲存庫，安裝 Git、GitHub CLI、Python 3.12、uv、Node.js 與 PostgreSQL 工具，依 [行情模組 README](../../backend/market_data/README.md) 安裝相依套件、設定 `PG_BIN`、遷移及執行測試。文件中的 `D:/learn/...` 工具路徑只適用原電腦，請使用新電腦的安裝位置。完整應用另外需要既有 Clerk／AWS 設定。

任務 8 的 [PR #22](https://github.com/husky0787/Alex/pull/22) 已合併為 `4e9343b`，新增共用的每日／手動 ETL 入口、批次鎖、完成時的執行快照、缺漏監控和告警事件，以及 `/api/market-data/status`。59 項後端、13 項 API 測試通過；實際 CronJob／手動 Job 競爭、品質失敗、漏資料回補及授權 API 均已驗收。見 [任務 8 證據](../verification/task-08-scheduled-etl.md) 與 [重現／操作步驟](../../deploy/etl/README.md)。該次行情為隔離的合成資料。

任務 9 在 `feat/task-09-bounded-eks` 完成真實 EKS 驗收：20 個標的、1,280 筆可信行情、每日／手動 ETL、AWS 權限隔離、HTTPS 授權、SQS 報告、HPA、故障恢復、回滾及告警送達。67 個 Terraform 資源已清理，state 已清空；獨立 AWS 核對確認原資料庫、6 個 Lambda 和 2 台 EC2 保留。兩筆測試秘密進入七天刪除恢復期。見 [任務 9 證據與限制](../verification/task-09-eks-acceptance.md)、[成本窗口](../verification/task-09-cloud-window.md) 和 [重建／清理步驟](../../deploy/eks/README.md)。測試使用獨立 JWT signer 與 Reporter 的研究不可用路徑，不能當成完整 Clerk 登入或五 agent 研究鏈驗收。

`.env`、AWS 登入資料與 `.local/` 私人行情不在版本庫；需要時安全移轉或重新設定。自訂 Codex skills 也須另行安裝。`.planning/` 僅保留本機執行過程，接續開發以本文件、GitHub Issues、ADR 和已提交的驗證文件為準。

## 已確認的條件

- 2026-10-27 核對 AWS API／使用者 Billing 畫面：預估剩餘 credit US$114.63，兩筆均於 2026-11-30 到期；當時本月至今 US$2.41，預測 US$2.90。所需研究鏈服務列於兩筆適用清單。2026-10-31 執行前 API 更新為 US$111.81。已依 [US$2.18 驗收情境估算](../verification/task-06-cloud-window.md) 執行雲端驗收；實際帳單仍待核對。
- 希望一個月內完成，可視進度加速；以 2026-11-25 作為目標日期。
- 專案來源為 husky0787/Alex，本機工作目錄為 alex-husky0787。
- 目標為可展示的個人專案，涵蓋既有 AI 應用、資料工程和 Kubernetes。
- 每週可投入時間尚未指定，因此以下是里程碑安排，不是交付時間保證。
- 使用者已確認第一版為 20 支美股／ETF、每日行情、最近 90 個曆日內交易日回補。

## 第一版範圍（已確認）

- 固定 20 支美股／ETF，日頻 OHLCV，以及最近 90 個曆日內的交易日回補。
- 行情擷取、S3 原始資料、品質檢查及壞資料隔離、Aurora 歷史行情與執行紀錄。
- 重跑冪等、限流重試、缺漏辨識、歷史回補及資料新鮮度狀態。
- 前端與 Planner 使用已驗證行情；失敗時不產生隨機價格。
- 核對並恢復既有研究／檢索流程，記錄可重現的端到端驗收。
- Kubernetes 第一版承載 FastAPI API 和 ETL；既有分析 agents 保留 Lambda。
- 本機 Kubernetes 先驗證部署與排程，再於短期 EKS 環境驗證 AWS 權限、Ingress、告警及回滾。
- 第一版不包含即時串流、全市場覆蓋、交易執行或全天候 EKS 展示服務。

## 預算策略與實際驗收窗口

先以 US$100 credit 內完成作為保守規劃；額外現金支出未獲授權。2026-10-31 任務 9 部署前核對剩餘 credit US$111.67、本月累計費用 US$5.37，採包含既有用量及緩衝的 US$20 情境估算與最多 8 小時窗口；這些數字不是任務 9 的已結算費用。
所有既有 AWS 服務的持續費用也要計入，不能把 US$100 全部分配給 EKS。

AWS 官方 EKS 標準支援價格為每叢集每小時 US$0.10：
- 30 天控制平面費用為 US$72。
- 72 小時控制平面費用為 US$7.20。
- 上述均未包含工作節點、負載平衡器、儲存、網路及其他服務費用。

建議主要在本機開發，EKS 集中於 2–3 天驗收窗口；驗收後保留建置程式和證據，清理專為驗收建立的資源。刪除既有或含資料資源需另行確認。
暫以 US$80 為規劃支出目標，保留 US$20 緩衝；這是分配目標，不是實測報價或 AWS 強制支出上限。
建立雲端環境前，先核對 credit 有效期限、適用服務、當前費用和選定部署的完整成本估算。

來源：
- https://aws.amazon.com/eks/pricing/
- https://aws.amazon.com/awscredits/

## 建議里程碑

1. 第 1 週：核對既有流程與待修項目，完成一筆行情從來源到前端的完整路徑。
2. 第 2 週：每日 ETL、90 天回補、品質隔離、冪等與失敗恢復；接入 Planner。
3. 第 3 週：API／ETL 容器化、本機 Kubernetes、部署流程及 AWS 基礎設施設定。
4. 第 4 週：短期 EKS 驗收、研究鏈端到端測試、告警與回滾演練、文件及展示。

提前完成某個里程碑即可進入下一階段；保持同一組驗收條件，不因趕進度省略驗證。

## 執行時需核對

- 任務 6 仍待實際帳單核對；任務 7／8／9 已合併。[PR #23](https://github.com/husky0787/Alex/pull/23) 合併為 `a819cef`，issue #11 已關閉。[任務 10／issue #12](https://github.com/husky0787/Alex/issues/12) 在 `feat/task-10-controlled-cicd` 完成 CI/CD 驗收：[Actions 實測](https://github.com/husky0787/Alex/actions/runs/41194304688) 四項工作全通過，106 項 CI 測試及另 2 項本機 Terraform 測試通過。發布開關已關閉，ECR 測試映像與驗收叢集已清理，保留可重用的 OIDC／IAM／空 ECR 設定。見 [發布操作](../../deploy/ci/README.md) 與 [驗證紀錄](../verification/task-10-cicd.md)。自動部署目標是 GitHub runner 的一次性 Kubernetes；EKS 仍採受控人工執行同一發布工具，不能宣稱已自動化 EKS 發布。
- [任務 11／issue #13](https://github.com/husky0787/Alex/issues/13) 已解除阻擋：使用者確認費用核對獨立追蹤，#12 已完成。真實 Brave／Clerk → 本機 API → 隔離 AWS Planner／三個分析 workers → 保存結果已通過；使用者確認行情日期／歷史與報告畫面。Tagger 是另外的分類預檢，研究來源沿用 Task6 真實紀錄。見 [作品入口](../showcase/README.md)、[Task11 證據與目前清理狀態](../verification/task-11-showcase.md)；不可把這次本機 API 驗收寫成新的 EKS 整合部署。
- 核對可用的行情供應商方案與帳號能力，再確定排程和回補方式。
- 實作規格中已確認的缺漏、過期及研究不可用行為，留下驗證證據。

規格與任務已發布；GitHub Issues 是執行狀態的主要來源。
