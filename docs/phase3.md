# Phase 3：HitL Checkpoint + 收尾

> 狀態：已完成（2026-05-13）

## 目標

展示 LangGraph Checkpoint / interrupt，完成面試展示版

## 完成項目

### 1. SQLite Checkpointer（`src/checkpointer.py`）
- `AsyncSqliteSaver` 做 async checkpoint 持久化
- 路徑偵測：嘗試 `/data`（Railway Volume）→ `/tmp`（ephemeral）→ `.data/`（本地開發）
- 用實際 SQLite open 測試可寫性，不依賴 `os.access()`

### 2. HitL Node（`src/agent/nodes.py`）
- `human_checkpoint`：用 `interrupt()` 暫停 graph，回傳 PR 資訊供人工審核
- Resume 後從 `interrupt()` 返回值取得 `approved` flag

### 3. Resume & Status Endpoints（`src/main.py`）
- `POST /review/resume`：接受 `{repo, pr_number, head_sha, approved}`，用 `Command(resume=...)` 恢復 graph
- `GET /review/status/{repo}/{pr_number}/{head_sha}`：檢查 review 是否在等待人工審核
- Thread ID 策略：`repo:pr_number:head_sha`（每次 push 獨立 thread，舊的自動 orphan）

### 4. FastAPI Lifespan 重構（`src/main.py`）
- 從 deprecated `@app.on_event("startup")` 改為 `lifespan` context manager
- `AsyncSqliteSaver` 需要 async context 管理生命週期

### 5. 收尾
- 在 `travel-agent-orchestrator` repo 設定 Webhook，成功跑通完整 review
- README 加架構圖、demo 截圖、技術說明
- CLAUDE.md 更新至 Phase 2 架構
- Best-effort ack comment（403 不阻斷 review 流程）

## 未實作（有意識的 scope cut）

| 項目 | 原因 |
|------|------|
| rejected → 跳過 review | 目前 rejected 仍會貼 review（as COMMENT），未來可加條件 edge |
| Resume endpoint 認證 | 目前無 auth，生產環境應加 bearer token |
| LangSmith 整合 | Optional 觀測工具，不影響核心功能 |

## 驗證方式

1. 35 個測試全部通過
2. Railway 部署成功，healthcheck 通過
3. PR #6 on `travel-agent-orchestrator` 收到完整 AI review（截圖見 `docs/images/review-demo.png`）
