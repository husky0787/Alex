# 09: 在限時 EKS 環境跑通應用與 ETL

**Status:** ready-for-agent

**GitHub:** https://github.com/husky0787/Alex/issues/11

## Parent

[Alex 第一版規格 #2](https://github.com/husky0787/Alex/issues/2)

## What to build

使用者經雲端入口存取 API，日行情能透過 EKS 工作負載寫入 AWS 資料服務；展示環境能按文件重建。

## Acceptance criteria

- [ ] 部署前核對 credit、既有消耗與完整估算；規劃支出 US$80、US$20 緩衝，估算不足時先調整，不默認額外付款。
- [ ] 以 Terraform 建立限時測試環境，記錄 EKS、節點、ALB、網路與儲存等成本及清理方式。
- [ ] 分離 API／ETL 的 ServiceAccount 和 AWS 權限，使用工作負載身分及 Secrets Manager，秘密不寫入映像或版本庫。
- [ ] 驗證雲端入口授權、Aurora 存取、S3 保存與隔離、SQS 分析，以及真實每日／手動 ETL 執行。
- [ ] 驗證 HPA 所需 metrics、Pod 故障恢復及告警實際送達；紀錄時間和結果。
- [ ] 入口切換與回滾明確，保留原 API 路徑；測試資源以短期窗口運行，清理前辨認既有及含資料資源。

## Blocked by

- [#7](https://github.com/husky0787/Alex/issues/7) — [Alex v1/05] 分析報告使用已驗證的行情
- [#10](https://github.com/husky0787/Alex/issues/10) — [Alex v1/08] Kubernetes 每日排程及手動回補共用 ETL
