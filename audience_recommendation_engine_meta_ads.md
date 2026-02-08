# Audience Recommendation Engine for Meta Ads (ROAS-First)

## 1. Purpose
This system automates audience-level decision-making for Meta Ads accounts with ROAS as the primary metric.
It converts raw performance data into clear, explainable actions such as scaling, holding, pausing, or retesting audiences.

The system is designed to:
- Reduce manual analysis time
- Prevent noisy or emotional decisions
- Encode proven media-buying heuristics
- Allow gradual automation (analysis → recommendations → execution)

This document is intended as a **starting spec for implementation in Cursor**.

---

## 2. Scope
**Level of automation**: Semi-automated decision engine  
**Primary entity**: Ad Set / Audience  
**Execution**: Recommendation-first, API execution optional  

---

## 3. High-Level Architecture

```
Meta Ads API
     ↓
Data Ingestion Layer
     ↓
Metrics & Normalization Layer
     ↓
Rule Engine (Deterministic)
     ↓
Claude Analysis Layer
     ↓
Recommendation Output
     ↓
(Optional) Execution via Meta API
```

---

## 4. Core Inputs

### 4.1 Performance Metrics (per audience)
- Spend
- Purchases
- Revenue
- ROAS
- CPA
- CTR
- CVR

### 4.2 Time-Based Metrics
- Last 1 / 3 / 7 day aggregates
- Day-over-day ROAS change
- ROAS trend slope
- CPA volatility (std deviation)

### 4.3 Account Benchmarks
- Account average ROAS
- Campaign average ROAS
- Target CPA
- Median audience spend

### 4.4 Audience Metadata
- Audience type: Broad / Interest / LLA / Custom
- Lookalike % (if applicable)
- Source quality (Purchasers, ATC, VC)
- Audience age (days since launch)
- Current budget

---

## 5. Noise Filtering Layer

Audiences are excluded from decisions if:
- Spend < MIN_SPEND_THRESHOLD
- Purchases < MIN_PURCHASE_THRESHOLD
- Audience age < MIN_AGE_DAYS

Example defaults:
```
MIN_SPEND = ₹3,000
MIN_PURCHASES = 2
MIN_AGE = 2 days
```

---

## 6. Normalization & Scoring

### 6.1 Normalized Metrics
Each metric is normalized against account or campaign benchmarks.

Example:
```
normalized_roas = audience_roas / account_avg_roas
normalized_spend = audience_spend / median_spend
```

### 6.2 Composite Score (example)
```
Audience Score =
  (normalized_roas * 0.5)
+ (normalized_spend * 0.2)
+ (normalized_cvr * 0.2)
+ (purchase_volume_score * 0.1)
```

Scores are used for ranking, not direct execution.

---

## 7. Rule Engine (Deterministic)

### 7.1 Performance Buckets
```
WINNER   : normalized_roas >= 1.2
AVERAGE  : 0.9 <= normalized_roas < 1.2
LOSER    : normalized_roas < 0.9
```

### 7.2 Trend States
- STABLE
- IMPROVING
- DECLINING
- VOLATILE

Derived from:
- ROAS slope
- CPA variance
- Spend acceleration

---

## 8. Decision Matrix

| Performance | Trend       | Action |
|-----------|-------------|--------|
| Winner    | Stable      | Scale  |
| Winner    | Volatile    | Hold   |
| Average   | Improving   | Hold   |
| Average   | Declining   | Pause  |
| Loser     | Low Spend   | Hold   |
| Loser     | Enough Data | Pause  |

---

## 9. Audience-Specific Modifiers

### Broad
- Higher spend tolerance
- Slower pause trigger
- Lower ROAS threshold

### Lookalike 1%
- Faster scale
- Faster fatigue detection
- Lower max scale ceiling

### Interests
- Lower patience
- Faster pause if ROAS drops

### Custom Audiences
- Lower scale caps
- Strong creative dependency

---

## 10. Guardrails

Hard constraints applied before any action:
- Max scale per action: 20–30%
- Cooldown after scale: 48–72h
- Max daily budget increase cap
- No pauses under minimum spend

Claude cannot override guardrails.

---

## 11. Claude Analysis Layer

### Inputs to Claude
- Aggregated metrics
- Rule engine outputs
- Historical context (optional)

### Responsibilities
- Validate rule-based decisions
- Explain rationale in plain English
- Flag risks (fatigue, saturation, volatility)
- Suggest alternatives (duplicate, retest, creative swap)

Claude does **not**:
- Pull data
- Execute changes
- Modify guardrails

---

## 12. Recommendation Output Schema

```json
{
  "audience_id": "string",
  "audience_name": "string",
  "action": "SCALE | HOLD | PAUSE | RETEST",
  "scale_percentage": 20,
  "confidence": "HIGH | MEDIUM | LOW",
  "reasons": [
    "ROAS 1.4x account average",
    "Spend above noise threshold",
    "Stable performance last 3 days"
  ],
  "risks": [
    "Possible fatigue beyond ₹25k spend"
  ]
}
```

---

## 13. Optional Execution Layer

### Flow
1. Recommendations generated
2. Human approval (UI / Slack / CLI)
3. Approved actions executed via Meta API

### Executable Actions
- Budget increase/decrease
- Ad set pause/unpause
- Ad set duplication

---

## 14. Logging & Feedback Loop

Each action is logged with:
- Input metrics
- Decision
- Outcome after X days

Claude can analyze:
- False positives
- Missed winners
- Bad pauses

Used to refine rules over time.

---

## 15. Implementation Roadmap

### Phase 1
- Data ingestion
- Metrics + scoring
- Manual review

### Phase 2
- Claude recommendations
- Structured outputs
- Slack / dashboard delivery

### Phase 3
- MCP + semi-automation
- Approval-based execution

---

## 16. Non-Goals
- No black-box ML
- No full autonomy without human review
- No creative generation (out of scope)

---

## 17. Design Philosophy
- ROAS-first
- Safety over aggression
- Explainability over automation
- Gradual trust-building

---

## 18. Cursor Usage Notes
- Use this doc as the system blueprint
- Implement layers as separate modules
- Keep rules configurable via constants
- Keep Claude prompts versioned

---

End of document.
