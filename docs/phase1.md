# Phase 1：基礎跑通 + 部署

> 狀態：已完成（2026-05-11）

## 目標

最小可用版本：真實 webhook 觸發 → 自動 review 貼回 PR

## 完成項目

### 1. 專案初始化
- `pyproject.toml`（依賴：langgraph, google-genai, fastapi, uvicorn, httpx）
- `.env.example`、`.gitignore`
- `railway.toml`（含 Volume 設定）
- `CLAUDE.md` 專案索引

### 2. Webhook 驗證與解析（`src/github/webhook.py`）
- 驗證 `X-Hub-Signature-256`（HMAC-SHA256）
- 解析 payload，只處理 `pull_request` 事件的 `opened` / `synchronize` / `reopened` action
- 其餘事件回傳 `{"status": "ignored"}`

### 3. GitHub API client（`src/github/client.py`）
- 使用 `httpx.AsyncClient`（非 PyGithub，完全 async）
- `get_pr_info` / `get_pr_files`（含分頁）/ `post_review` / `post_comment`

### 4. Diff 處理（`src/github/diff.py`）
- 跳過 lockfile、generated files、圖片等（SKIP_PATTERNS）
- 檔案級截斷：整個檔案納入或跳過，不切斷 hunk
- Token 預算控制（~50K tokens，1 token ≈ 4 chars）

### 5. LangGraph Agent 核心
- `src/agent/state.py`：PRReviewState TypedDict
- `src/agent/prompts.py`：System/User prompt + Gemini function calling schema
- `src/agent/nodes.py`：fetch_diff → analyze_code → format_review → post_review
- `src/agent/graph.py`：線性 graph（Phase 1 不含 evaluate/HitL）

### 6. FastAPI App（`src/main.py`）
- `POST /webhook/github`：驗證簽章 → 立即回 200 → 背景 asyncio.create_task 執行 review
- 去重機制：追蹤 `(repo, pr_number)` → `(head_sha, task)`，新事件取消舊 task
- `GET /health`：health check

### 7. 測試（20 tests passing）
- `test_webhook.py`：簽章驗證、事件過濾
- `test_diff.py`：檔案過濾、token 預算、格式
- `test_nodes.py`：format_review 各種情境

## 設計決策

| 決策 | 選擇 | 原因 |
|------|------|------|
| GitHub API client | httpx async | PyGithub 同步會阻塞 FastAPI event loop |
| Checkpoint 持久化 | SQLite + Railway Volume | 簡單夠用，railway.toml 幾行設定 |
| LLM 結構化輸出 | Gemini function calling (mode=ANY) | 保證回傳合規 JSON，不依賴 LangChain wrapper |
| 部署時機 | Phase 1 就部署 | 省去 ngrok，直接用真實 webhook 測試 |

## 驗證方式

部署到 Railway → 在測試 repo 設定 webhook → 開 PR → 確認收到 AI review 留言
