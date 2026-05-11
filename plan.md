# pr-sentinel — 計劃書

> 建立日期：2026-05-11  
> Repo 名稱：`pr-sentinel`  
> 目標：用 LangGraph 建置一個自動 Code Review Agent，串接 GitHub Webhook，自動審查所有 repo 的 PR 並貼回留言

---

## 一、專案目標

**解決的問題**：PR 等人工 review 耗時，小問題（格式錯誤、潛在 bug、安全疑慮）應該在送審前就被發現。

**使用場景**：
- 任何你管理的 GitHub repo 開 PR，Agent 自動分析 diff 並在 PR 留言區貼出 review 結果
- 支援多個 repo，只需要在每個 repo 設定一次 webhook

**面試價值**：
- 展示 LangGraph 核心能力：條件分支、循環 retry、Checkpoint（HitL）
- 有真實 webhook 觸發，不是空跑 demo
- Python 實作，補足你目前 TypeScript 為主的技術形象

---

## 二、技術選型

| 元件 | 選擇 | 原因 |
|------|------|------|
| Agent 框架 | LangGraph（Python）| 支援 cycle、條件 edge、Checkpoint |
| Web Server | FastAPI | 輕量、async、適合接 webhook |
| LLM | Anthropic Claude Haiku（分析）+ Sonnet（複雜判斷）| Model Tier 降成本 |
| 部署 | Railway 免費方案 | 有公開 URL，免費足夠 side project |
| 觀測 | LangSmith 免費 tier | trace 每步 Node 執行，方便 debug |
| GitHub 整合 | PyGithub + Webhook | 讀 diff、貼 review 留言 |

---

## 三、系統架構

```
GitHub Repo A ──┐
GitHub Repo B ──┼──→ Webhook POST /webhook/github
GitHub Repo C ──┘           │
                             ▼
                    FastAPI Webhook Receiver
                    （驗證 X-Hub-Signature）
                             │
                             ▼
                    LangGraph PR Review Agent
                    ┌────────────────────────┐
                    │  fetch_diff            │ ← GitHub API 取得 diff
                    │       ↓                │
                    │  analyze_code          │ ← LLM 分析問題
                    │       ↓                │
                    │  evaluate_quality      │ ← Evaluator 評分 0-10
                    │       ↓                │
                    │  score < 6?            │
                    │  ├─ Yes → revise       │ ← 最多 2 次 retry
                    │  └─ No ↓               │
                    │  high_risk?            │ ← 偵測高風險變更
                    │  ├─ Yes → [HitL 等待] │ ← Checkpoint 暫停
                    │  └─ No ↓               │
                    │  post_review           │ ← 貼回 GitHub PR
                    └────────────────────────┘
```

---

## 四、LangGraph State 設計

```python
from typing import TypedDict, Annotated
from langgraph.graph import add_messages

class PRReviewState(TypedDict):
    # ── 輸入（Webhook payload 填入）──
    repo: str               # "Pin-Han/travel-agent-coordinator"
    pr_number: int          # 42
    pr_title: str           # "feat: add memory persistence"
    pr_description: str     # PR body 描述
    diff: str               # 完整 git diff 內容
    changed_files: list     # 變更的檔案清單

    # ── 分析過程 ──
    analysis: str           # LLM 的初步分析結果
    issues: list            # 找到的問題列表（type, severity, file, line, message）
    suggestions: list       # 改善建議列表
    score: int              # 品質評分 0-10
    revision_feedback: str  # Evaluator 的扣分說明（用於 retry）

    # ── 流程控制 ──
    retry_count: int        # 目前 retry 次數（上限 2）
    is_high_risk: bool      # 是否偵測到高風險變更
    human_approved: bool    # HitL 人工確認結果

    # ── 輸出 ──
    review_body: str        # 最終貼到 PR 的 review 內容
    review_decision: str    # "APPROVE" / "REQUEST_CHANGES" / "COMMENT"
```

---

## 五、各 Node 說明

### Node 1：`fetch_diff`
- 用 PyGithub 呼叫 GitHub API 取得 PR 的完整 diff
- 超過 token 限制（diff 太大）就截取前 N 個檔案，並在 review 中標注「僅分析部分檔案」

```python
def fetch_diff(state: PRReviewState) -> PRReviewState:
    g = Github(os.environ["GITHUB_TOKEN"])
    repo = g.get_repo(state["repo"])
    pr = repo.get_pull(state["pr_number"])
    files = pr.get_files()
    diff = "\n".join([f.patch for f in files if f.patch])
    return {**state, "diff": diff[:MAX_DIFF_TOKENS]}
```

### Node 2：`analyze_code`
- 用 Claude Haiku 分析 diff，輸出結構化 JSON
- Prompt 要求回傳：issues（問題列表）+ suggestions（建議）

```python
ANALYZE_PROMPT = """
你是一個資深工程師在進行 Code Review。
分析以下 PR 的 diff，找出：
1. 潛在 bug 或邏輯錯誤
2. 安全性問題（SQL injection、XSS、未驗證的輸入等）
3. 效能問題（N+1、不必要的重複計算等）
4. 程式碼風格問題
5. 缺少錯誤處理的地方

輸出 JSON 格式：
{
  "issues": [{"type": "bug|security|performance|style", "severity": "high|medium|low", "file": "...", "message": "..."}],
  "suggestions": [{"file": "...", "suggestion": "..."}]
}
"""
```

### Node 3：`evaluate_quality`
- 用 Claude Sonnet 當 Evaluator，對 analysis 結果評分 0-10
- 評分標準：分析是否完整、有沒有遺漏明顯問題、建議是否具體可行
- 同時偵測 `is_high_risk`：diff 含 DB migration、auth 相關、secrets 操作

```python
def is_high_risk_change(diff: str) -> bool:
    high_risk_patterns = [
        "migration", "ALTER TABLE", "DROP TABLE",
        "password", "secret", "token", "private_key",
        "sudo", "chmod", "eval("
    ]
    return any(p.lower() in diff.lower() for p in high_risk_patterns)
```

### Node 4：`revise_review`（條件觸發）
- 當 `score < 6` 且 `retry_count < 2` 時觸發
- 把 Evaluator 的 feedback 注入 prompt，讓 analyze_code 重新跑一次
- 這就是 LangGraph 的 **cycle**：revise → 回到 evaluate → 再判斷

### Node 5：`human_checkpoint`（條件觸發）
- 當 `is_high_risk = True` 時觸發
- 用 LangGraph Checkpoint（存到 SQLite）暫停 Agent
- 送 Slack 通知或 Email 通知你確認
- 你回覆「approve」或「reject」後，Agent 從 Checkpoint 恢復繼續

```python
# 使用 LangGraph interrupt 暫停執行
from langgraph.types import interrupt

def human_checkpoint(state: PRReviewState) -> PRReviewState:
    result = interrupt({
        "message": f"高風險 PR 需要確認：{state['repo']} #{state['pr_number']}",
        "review_preview": state["review_body"]
    })
    return {**state, "human_approved": result["approved"]}
```

### Node 6：`post_review`
- 組合最終 review 格式（Markdown）
- 用 GitHub API 貼回 PR review

```python
def post_review(state: PRReviewState) -> PRReviewState:
    g = Github(os.environ["GITHUB_TOKEN"])
    repo = g.get_repo(state["repo"])
    pr = repo.get_pull(state["pr_number"])
    pr.create_review(
        body=state["review_body"],
        event=state["review_decision"]  # "APPROVE" / "REQUEST_CHANGES" / "COMMENT"
    )
    return state
```

---

## 六、條件 Edge 設計

```python
def route_after_evaluate(state: PRReviewState) -> str:
    if state["score"] < 6 and state["retry_count"] < 2:
        return "revise_review"
    elif state["is_high_risk"] and not state["human_approved"]:
        return "human_checkpoint"
    else:
        return "post_review"

graph.add_conditional_edges(
    "evaluate_quality",
    route_after_evaluate,
    {
        "revise_review": "revise_review",
        "human_checkpoint": "human_checkpoint",
        "post_review": "post_review"
    }
)

# revise 後回到 evaluate（形成 cycle）
graph.add_edge("revise_review", "evaluate_quality")

# human checkpoint 後繼續 post
graph.add_edge("human_checkpoint", "post_review")
```

---

## 七、PR Review 輸出格式

```markdown
## 🤖 AI Code Review

**品質評分：8 / 10**  
**決定：REQUEST_CHANGES**

---

### ❗ 問題（需修正）

| 嚴重度 | 檔案 | 問題 |
|--------|------|------|
| 🔴 High | `src/auth.ts:42` | 用戶輸入未做 sanitization，有 XSS 風險 |
| 🟡 Medium | `src/db.ts:18` | 查詢未使用 parameterized query，有 SQL injection 風險 |

---

### 💡 建議（可選改善）

- `src/utils.ts`：`fetchData` 函式缺少 error handling，建議加 try/catch
- `src/types.ts`：`UserData` interface 建議加 `readonly` 避免意外修改

---

### ✅ 優點

- 新增的單元測試覆蓋了主要邏輯分支
- TypeScript 型別定義完整，無 `any` 使用

---

*由 PR Review Agent 自動生成 · [查看原始碼](https://github.com/Pin-Han/pr-sentinel)*
```

---

## 八、專案結構

```
pr-sentinel/
├── src/
│   ├── agent/
│   │   ├── graph.py          # LangGraph graph 定義
│   │   ├── nodes.py          # 各 Node 實作
│   │   ├── state.py          # PRReviewState TypedDict
│   │   ├── prompts.py        # Prompt 管理
│   │   └── router.py         # 條件 edge 邏輯
│   ├── github/
│   │   ├── client.py         # PyGithub 封裝
│   │   └── webhook.py        # Webhook 驗證與解析
│   ├── checkpointer.py       # LangGraph Checkpoint 設定（SQLite）
│   └── main.py               # FastAPI app + /webhook/github endpoint
├── tests/
│   ├── test_nodes.py         # 各 Node 的 unit test
│   └── test_graph.py         # 端對端 graph 測試（mock GitHub API）
├── .env.example
├── railway.toml              # Railway 部署設定
├── requirements.txt
└── README.md
```

---

## 九、實作階段

### Phase 1：基礎跑通（第 1 個週末）
- [ ] FastAPI webhook receiver（驗證 `X-Hub-Signature-256`）
- [ ] GitHub API client（讀 diff、貼留言）
- [ ] LangGraph 基本 graph：fetch → analyze → post（先不加 evaluate 和 HitL）
- [ ] 本地用 `ngrok` 測試 webhook 接收

### Phase 2：加入 Evaluator + Retry cycle（第 2 個週末）
- [ ] `evaluate_quality` Node
- [ ] `revise_review` Node
- [ ] 條件 edge + cycle（score < 6 → retry → re-evaluate）
- [ ] 加上 `retry_count` 上限防止無限循環

### Phase 3：Checkpoint + HitL + 部署（第 3 個週末）
- [ ] `is_high_risk` 偵測邏輯
- [ ] LangGraph Checkpoint（SQLite）+ `interrupt` 暫停機制
- [ ] 簡單的 resume endpoint：`POST /review/{thread_id}/resume`
- [ ] 部署到 Railway，設定環境變數
- [ ] 在 2~3 個 repo 設定 GitHub Webhook
- [ ] README 加截圖

### Phase 4：加分項（時間允許）
- [ ] LangSmith 整合（每次 review 留下完整 trace）
- [ ] 支援多種語言的 review（TypeScript / Python / Go）
- [ ] 統計 dashboard：每個 repo 的 review 歷史、平均分數

---

## 十、環境變數

```env
# LLM
ANTHROPIC_API_KEY=sk-ant-...

# GitHub
GITHUB_TOKEN=ghp_...           # 有 repo + pull_request 權限
GITHUB_WEBHOOK_SECRET=...      # 驗證 webhook 簽章用

# LangSmith（選填）
LANGCHAIN_API_KEY=ls__...
LANGCHAIN_TRACING_V2=true
LANGCHAIN_PROJECT=pr-sentinel

# Server
PORT=8000
```

---

## 十一、面試時怎麼介紹這個 Project

**一句話定位**：「一個用 LangGraph 建置的 GitHub PR Review Agent，有 Evaluator + cycle retry、高風險變更的 Human-in-the-Loop，以及跨 repo 的 webhook 整合。」

**可以展示的 LangGraph 能力**：
- **Cycle**：analyze → evaluate → revise → evaluate（score 不夠就重跑）
- **Conditional Edge**：score 夠了才往下走，高風險才觸發 HitL
- **Checkpoint / interrupt**：Agent 暫停等人工確認，確認後從斷點繼續

**和 travel-agent-coordinator 的差異**（避免被問「為什麼做兩個類似的）：
> 「前一個展示了自建 Orchestrator 的能力和 A2A Protocol。這個展示的是 LangGraph 在『複雜流程控制』上的優勢——特別是 Checkpoint 讓 Agent 可以暫停等人工介入，這是我自建 Orchestrator 比較難做到的地方。」

---

*最後更新：2026-05-11*
