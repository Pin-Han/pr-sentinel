# Phase 2：Evaluator + Retry Cycle

> 狀態：已完成（2026-05-13）

## 目標

加入品質把關機制，展示 LangGraph cycle 能力

## 完成項目

### 1. 新增 Nodes（`src/agent/nodes.py`）
- `evaluate_quality`：用 Gemini function calling 評分 0-10 + feedback + high-risk 偵測
- `revise_review`：注入 evaluator feedback 重新分析，遞增 `retry_count`

### 2. 條件 Edge（`src/agent/router.py`）
- `route_after_evaluate`：
  - score < 6 && retry_count < 2 → `revise_review`（retry）
  - is_high_risk && !human_approved → `human_checkpoint`（HitL）
  - 否則 → `format_review`（pass-through）
- 優先級：retry > HitL > pass-through

### 3. 更新 Graph（`src/agent/graph.py`）
```
fetch_diff → analyze_code → evaluate_quality
  ├─→ revise_review → evaluate_quality (cycle, max 2 retries)
  ├─→ human_checkpoint → format_review → post_review
  └─→ format_review → post_review → END
```

### 4. Prompts & Tool Schema（`src/agent/prompts.py`）
- `EVALUATE_SYSTEM` / `EVALUATE_USER`：evaluator prompt
- `EVALUATE_TOOL` / `EVALUATE_TOOL_CONFIG`：`submit_evaluation` function（score, feedback, is_high_risk）
- `REVISE_USER`：注入 evaluator feedback 的 re-analysis prompt，復用 `ANALYZE_TOOL` 做輸出

### 5. 測試（35 tests passing）
- `test_router.py`：9 個 routing 測試（score 門檻、retry 上限、high-risk 分支、優先級）
- `test_evaluate.py`：6 個 evaluate/revise 測試（mock LLM、fallback、retry_count 遞增）

## 設計決策

| 決策 | 選擇 | 原因 |
|------|------|------|
| Evaluator LLM | 同一個 Gemini model | 簡化部署，避免多 API key；用 prompt 區分角色 |
| Retry 上限 | 2 次 | 防止無限 loop，route function 保證終止 |
| Routing 優先級 | retry > HitL | 先確保品質，再做人工審核 |

## 驗證方式

1. 35 個測試全部通過
2. 部署到 Railway 成功
3. 觸發 PR webhook，完整 review 貼回 GitHub
