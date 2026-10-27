# Alex 第一版規劃

更新日期：2026-10-27。狀態：任務 1–3 已合併至 `main`，GitHub #3–#5 已關閉；任務 4（GitHub #6）已在 `feat/task-04-universe-history` 實作並通過本機及真實來源驗證，等待 PR 審查與合併。規格 #2 與其餘任務仍開啟。

規格：[alex-v1-spec.md](alex-v1-spec.md)。任務：[任務清單](alex-v1-tickets/README.md)。

## 已完成與接續入口

| 任務 | 已合併 PR | 驗證紀錄 |
| --- | --- | --- |
| 1：API 錯誤契約 | [#14](https://github.com/husky0787/Alex/pull/14) | [本機驗證](../verification/task-01-api-errors.md) |
| 2：真實行情從來源到畫面 | [#15](https://github.com/husky0787/Alex/pull/15) | [驗證與 63/63 AAPL 來源證據](../verification/task-02-verified-price.md) |
| 3：品質隔離與失敗恢復 | [#16](https://github.com/husky0787/Alex/pull/16) | [測試與遷移驗證](../verification/task-03-quality-recovery.md) |

任務 3 合併 commit：`49e3a4e36b260ed7bb1e6ccf9a1c8591f2a58bc9`。上述結果以本機測試為主；新管線尚未部署 AWS，Kubernetes 仍待實作。

任務 4 新增 20 支標的選擇、90 曆日歷史與可恢復回補；真實來源驗證 20 × 62 個已發布交易日，重跑全部跳過。[Draft PR #17](https://github.com/husky0787/Alex/pull/17)；[驗證紀錄](../verification/task-04-universe-history.md)。換機接續此任務須 checkout `feat/task-04-universe-history`；合併後再從最新 `main` 開始任務 5（#7）。

目前 `/api/analyze` 明確回傳 `503`，Planner 亦拒絕舊分析路徑，避免使用無來源價格。任務 5（#7）須接上不可變行情快照後恢復分析；不要直接移除保護。行情頁可用。設計見 [ADR 0002](../adr/0002-market-quality-and-recovery.md)。

換機時 clone／更新本儲存庫，安裝 Git、GitHub CLI、Python 3.12、uv、Node.js 與 PostgreSQL 工具，依 [行情模組 README](../../backend/market_data/README.md) 安裝相依套件、設定 `PG_BIN`、遷移及執行測試。文件中的 `D:/learn/...` 工具路徑只適用原電腦，請使用新電腦的安裝位置。完整應用另外需要既有 Clerk／AWS 設定。

`.env`、AWS 登入資料與 `.local/` 私人行情不在版本庫；需要時安全移轉或重新設定。自訂 Codex skills 也須另行安裝。`.planning/` 僅保留本機執行過程，接續開發以本文件、GitHub Issues、ADR 和已提交的驗證文件為準。

## 已確認的條件

- 使用者表示 AWS 剩餘 promotional credit 約 US$100；尚未核對帳單、有效期限及適用服務。
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

## 預算策略（建議，尚未建立資源）

先以剩餘 US$100 credit 內完成作為保守規劃；額外現金支出未獲授權。
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

- 按已確認的規格、驗收條件和 GitHub 依賴執行；先完成任務 4 的 PR 審查與合併，再從更新後的 `main` 建立任務 5 分支。#7 與 #9 的前置依賴亦已完成。
- 核對可用的行情供應商方案與帳號能力，再確定排程和回補方式。
- 實作規格中已確認的缺漏、過期及研究不可用行為，留下驗證證據。

規格與任務已發布；GitHub Issues 是執行狀態的主要來源。
