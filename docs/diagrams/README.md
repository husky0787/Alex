# Interactive architecture diagrams / 互動架構圖

[Open the diagram catalog / 開啟導覽](https://husky0787.github.io/Alex/)

Five source-backed Archify diagrams cover the platform, market-data pipeline, Task9 Kubernetes deployment, analysis sequence, and manual CI/CD. The viewer is in Traditional Chinese; technical identifiers remain unchanged. The root READMEs and deployment documents use static SVG previews linked to the HTML.

五張圖分別說明全貌、行情 ETL、Task9 Kubernetes、分析時序與手動 CI/CD。AWS 資源已清理，圖表不是目前在線的資源清單。Task9 的隔離 Reporter、Task11 的完整分析、CD 的 fixture API 驗收各自區分。

## Files and hosting / 檔案與發布

- `docs/index.html`: bilingual catalog / 中英文導覽。
- `docs/diagrams/*.html`: standalone interactive pages / 獨立互動頁面。
- `*.svg` and `*.png`: full-diagram exports from the viewer / 檢視器匯出的完整圖。
- `sources/*.json`: editable diagram definitions with frozen GitHub source references / 可維護的圖表定義與固定版本原始碼引用。
- `verification.json`: portable artifact hashes and automated gate results / 可攜式雜湊與檢查摘要。

GitHub Pages serves **main /docs**, with `.nojekyll`. This is static documentation hosting; it does not run the application or enable AWS CD. The private `.archify/` drafts and machine-specific receipts are excluded from Git.

Generated HTML/SVG are committed byte-for-byte. The local `.gitattributes` prevents line-ending conversion from invalidating verified artifact hashes; generated whitespace is preserved.

GitHub Pages 從 **main /docs** 發布靜態文件，不會啟動 Alex 應用或恢復 AWS 資源。本機草稿與含機器路徑的檢查收據不提交。

## Refreshing diagrams / 更新方式

Read the relevant implementation first. Update node/edge meaning and the full 40-character `meta.repository.revision` together; check every source line range against that commit. Preserve the separate acceptance environments and retirement notice.

先閱讀實作，再更新圖表及來源版本；不要只改標籤或把歷史驗收誤寫成目前部署。

With Archify installed, run from the repository root, replacing `<archify>` with its installation path:

```text
node <archify>/bin/archify.mjs finalize architecture docs/diagrams/sources/architecture.json docs/diagrams/architecture.html --repo-root . --quality showcase --out-dir .archify/architecture-review --json
```

Use `dataflow` for `data-engineering`, `sequence` for `analysis`, `workflow` for `cicd`, and `architecture` for `kubernetes`. Give subsequent reviews a new output directory. Re-export SVG/PNG through the viewer after changing an HTML artifact, then refresh the public verification hashes. Keep raw receipts private.

All five artifacts passed validation, delivery, strict artifact checks and real-browser checks. Light/dark captures were checked; desktop views and full exported previews were visually inspected. The ETL diagram retains two routed crossings for recovery/calendar inputs; they are not joins. Use focus/path exploration to follow them. Sequence spacing is illustrative, not measured latency. Browser evidence does not assert that AWS is running.

五張圖均通過格式、來源、產物與真實瀏覽器檢查。ETL 保留兩條日曆／恢復路徑的交叉，交叉不代表資料合併；可用互動路徑追蹤。時序間距不是實測延遲。這些檢查不代表 AWS 正在運行。
