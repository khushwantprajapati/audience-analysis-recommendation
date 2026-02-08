"""Analysis layer: rule-based explanations (no AI needed), with optional Claude upgrade."""
import json
import uuid
from typing import Any, Optional

from app.config import get_settings
from app.models import ActionLog, Audience, Recommendation
from app.services.rules import run_rules_for_audience


# ---------------------------------------------------------------------------
# Rule-based explanation generator (no API key needed)
# ---------------------------------------------------------------------------

def _generate_reasons(rule_output: dict, audience: Audience, age_days: int) -> list[str]:
    """Build 2-3 plain-English reasons from raw metrics and rule engine output."""
    metrics = rule_output.get("metrics") or {}
    time_metrics = rule_output.get("time_metrics") or {}
    bucket = rule_output.get("performance_bucket", "")
    trend = rule_output.get("trend_state", "")
    action = rule_output.get("action", "HOLD")
    norm_roas = metrics.get("normalized_roas") or 0
    roas = metrics.get("roas")
    cpa = metrics.get("cpa")
    spend = metrics.get("spend") or 0
    purchases = metrics.get("purchases") or 0
    reasons: list[str] = []

    # Reason 1: ROAS vs account average
    if roas is not None:
        if norm_roas >= 1.2:
            reasons.append(f"ROAS {roas:.2f} is {norm_roas:.1f}x the account average — strong performer")
        elif norm_roas >= 0.9:
            reasons.append(f"ROAS {roas:.2f} is near the account average ({norm_roas:.1f}x) — average performer")
        else:
            reasons.append(f"ROAS {roas:.2f} is only {norm_roas:.1f}x the account average — underperforming")
    else:
        reasons.append("No ROAS data available yet")

    # Reason 2: Trend context
    roas_slope = time_metrics.get("roas_slope") or 0
    cpa_vol = time_metrics.get("cpa_volatility") or 0
    if trend == "IMPROVING":
        reasons.append(f"Performance is improving (ROAS slope: +{roas_slope:.3f})")
    elif trend == "DECLINING":
        reasons.append(f"Performance is declining (ROAS slope: {roas_slope:.3f})")
    elif trend == "VOLATILE":
        reasons.append(f"CPA is volatile (volatility: {cpa_vol:.2f}) — inconsistent results")
    else:
        reasons.append("Performance is stable with consistent metrics")

    # Reason 3: Spend / volume context
    if action == "SCALE" and purchases >= 3:
        reasons.append(f"{purchases} purchases on {spend:,.0f} spend — enough volume to justify scaling")
    elif action == "PAUSE":
        if cpa is not None:
            reasons.append(f"CPA of {cpa:,.0f} is too high relative to returns — pausing to cut losses")
        else:
            reasons.append("Insufficient returns relative to spend — pausing to cut losses")
    elif action == "HOLD":
        reasons.append(f"{purchases} purchases on {spend:,.0f} spend — monitoring before making changes")

    return reasons


def _generate_risks(rule_output: dict, audience: Audience, age_days: int) -> list[str]:
    """Flag 0-3 risks from metrics data."""
    metrics = rule_output.get("metrics") or {}
    time_metrics = rule_output.get("time_metrics") or {}
    settings = get_settings()
    risks: list[str] = []

    spend = metrics.get("spend") or 0
    median_spend = metrics.get("median_spend") or settings.min_spend
    cpa_vol = time_metrics.get("cpa_volatility") or 0
    norm_roas = metrics.get("normalized_roas") or 0
    audience_type = audience.audience_type

    # Fatigue risk: spend much higher than median
    if spend > median_spend * 2:
        risks.append(f"Spend ({spend:,.0f}) is {spend / median_spend:.1f}x the median — possible audience fatigue")

    # Volatility risk
    if cpa_vol > settings.volatile_cpa_std * 0.7:
        risks.append(f"CPA volatility ({cpa_vol:.2f}) is elevated — results may be inconsistent")

    # Young audience risk
    if age_days < 5:
        risks.append(f"Audience is only {age_days} days old — limited data for high-confidence decisions")

    # LLA fatigue
    if audience_type == "LLA" and spend > median_spend * settings.lla_fatigue_spend_multiplier:
        risks.append("Lookalike audience may be saturating at this spend level")

    # Creative dependency for custom audiences
    if audience_type == "CUSTOM":
        risks.append("Custom audience performance is heavily creative-dependent")

    # Declining trend on a winner
    if rule_output.get("performance_bucket") == "WINNER" and rule_output.get("trend_state") == "DECLINING":
        risks.append("Winner with declining trend — may be approaching fatigue")

    return risks[:3]  # Cap at 3


def _determine_confidence(rule_output: dict, age_days: int) -> str:
    """Determine HIGH / MEDIUM / LOW confidence from data sufficiency."""
    metrics = rule_output.get("metrics") or {}
    purchases = metrics.get("purchases") or 0
    spend = metrics.get("spend") or 0
    settings = get_settings()

    if purchases >= 10 and spend >= settings.min_spend * 3 and age_days >= 7:
        return "HIGH"
    if purchases >= settings.min_purchases and spend >= settings.min_spend and age_days >= settings.min_age_days:
        return "MEDIUM"
    return "LOW"


def analyze_one(
    db,
    rule_output: dict,
    audience: Audience,
) -> Optional[dict]:
    """
    Analyze one audience. Uses rule-based explanations by default.
    If ANTHROPIC_API_KEY is set, upgrades to Claude analysis.
    """
    age_days = 0
    if audience.launched_at:
        from datetime import datetime, timezone
        then = audience.launched_at
        if then.tzinfo is None:
            then = then.replace(tzinfo=timezone.utc)
        age_days = (datetime.now(timezone.utc) - then).days

    settings = get_settings()

    # Try Claude if API key is available
    if settings.anthropic_api_key:
        claude_result = _analyze_with_claude(rule_output, audience, age_days)
        if claude_result:
            return claude_result

    # Rule-based fallback (fully functional, no AI)
    action = rule_output.get("action", "HOLD")
    return {
        "action": action,
        "confidence": _determine_confidence(rule_output, age_days),
        "reasons": _generate_reasons(rule_output, audience, age_days),
        "risks": _generate_risks(rule_output, audience, age_days),
        "scale_percentage": rule_output.get("scale_percentage"),
    }


# ---------------------------------------------------------------------------
# Optional Claude upgrade (only used if ANTHROPIC_API_KEY is set)
# ---------------------------------------------------------------------------

ANALYSIS_PROMPT_V1 = """You are a Meta Ads performance analyst. Given the following audience data and the rule engine's recommendation, validate the decision and provide a structured analysis.

## Audience: {audience_name}
- Type: {audience_type} | Age: {age_days} days | Budget: {budget}
- ROAS: {roas} (normalized: {norm_roas}) | CPA: {cpa} | CVR: {cvr}
- Trend: {trend_state} | ROAS slope: {roas_slope} | CPA volatility: {cpa_vol}
- Account avg ROAS: {account_avg_roas}

## Rule Engine Decision: {action}
Performance bucket: {bucket} | Trend state: {trend_state}

Respond with a single JSON object (no markdown, no code block) with exactly these keys:
- "action": one of SCALE, HOLD, PAUSE, RETEST (you may keep or suggest RETEST if appropriate)
- "confidence": one of HIGH, MEDIUM, LOW (based on data sufficiency)
- "reasons": array of 2-3 short plain-English bullet points explaining why this action
- "risks": array of 0-3 short risk flags (fatigue, saturation, volatility, creative dependency)
- "scale_percentage": number 10-30 only if action is SCALE, else null
"""


def _analyze_with_claude(rule_output: dict, audience: Audience, age_days: int) -> Optional[dict]:
    """Call Claude API. Returns dict or None if it fails."""
    try:
        from anthropic import Anthropic
    except ImportError:
        return None

    settings = get_settings()
    metrics = rule_output.get("metrics") or {}
    time_metrics = rule_output.get("time_metrics") or {}
    prompt = ANALYSIS_PROMPT_V1.format(
        audience_name=rule_output.get("audience_name", audience.name),
        audience_type=rule_output.get("audience_type", audience.audience_type),
        age_days=age_days,
        budget=f"{audience.current_budget}" if audience.current_budget is not None else "N/A",
        roas=metrics.get("roas") or "N/A",
        norm_roas=round(metrics.get("normalized_roas") or 0, 2),
        cpa=metrics.get("cpa") or "N/A",
        cvr=metrics.get("cvr") or "N/A",
        trend_state=rule_output.get("trend_state", "N/A"),
        roas_slope=time_metrics.get("roas_slope", "N/A"),
        cpa_vol=time_metrics.get("cpa_volatility", "N/A"),
        account_avg_roas=rule_output.get("account_avg_roas") or "N/A",
        action=rule_output.get("action", "HOLD"),
        bucket=rule_output.get("performance_bucket", "N/A"),
    )
    try:
        client = Anthropic(api_key=settings.anthropic_api_key)
        resp = client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        text = resp.content[0].text if resp.content else ""
        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            end = next((i for i, L in enumerate(lines) if i > 0 and L.strip() == "```"), len(lines))
            text = "\n".join(lines[1:end])
        parsed = json.loads(text)
        action = parsed.get("action") or rule_output.get("action")
        if action not in ("SCALE", "HOLD", "PAUSE", "RETEST"):
            action = rule_output.get("action", "HOLD")
        return {
            "action": action,
            "confidence": parsed.get("confidence") or "MEDIUM",
            "reasons": parsed.get("reasons") or [],
            "risks": parsed.get("risks") or [],
            "scale_percentage": parsed.get("scale_percentage") if action == "SCALE" else rule_output.get("scale_percentage"),
        }
    except Exception:
        return None  # Fall back to rule-based


def generate_recommendations_for_account(db, account_id: str) -> list[dict]:
    """
    Run rules for account, then Claude for each, save Recommendation rows, return list of recommendation dicts.
    """
    from app.services.rules import run_rules_for_account
    from app.models import Recommendation as RecModel

    rule_results = run_rules_for_account(db, account_id)
    out = []
    for rr in rule_results:
        audience = db.query(Audience).filter(Audience.id == rr["audience_id"]).first()
        if not audience:
            continue
        claude_result = analyze_one(db, rr, audience)
        action = claude_result.get("action") or rr["action"]
        metrics = rr.get("metrics") or {}
        metrics_snapshot = {
            "roas": metrics.get("roas"),
            "cpa": metrics.get("cpa"),
            "spend": metrics.get("spend"),
            "revenue": metrics.get("revenue"),
            "purchases": metrics.get("purchases"),
            "cvr": metrics.get("cvr"),
            "clicks": metrics.get("clicks"),
            "impressions": metrics.get("impressions"),
        }
        rec_id = str(uuid.uuid4())
        rec = RecModel(
            id=rec_id,
            audience_id=rr["audience_id"],
            action=action,
            scale_percentage=claude_result.get("scale_percentage") or rr.get("scale_percentage"),
            confidence=claude_result.get("confidence", "MEDIUM"),
            performance_bucket=rr.get("performance_bucket", ""),
            trend_state=rr.get("trend_state", ""),
            composite_score=rr.get("composite_score"),
            reasons=claude_result.get("reasons") or [],
            risks=claude_result.get("risks") or [],
            metrics_snapshot=metrics_snapshot,
        )
        db.add(rec)
        action_log = ActionLog(
            id=str(uuid.uuid4()),
            audience_id=rr["audience_id"],
            account_id=account_id,
            input_metrics=metrics_snapshot,
            decision=action,
            confidence=claude_result.get("confidence"),
            reasons=claude_result.get("reasons"),
        )
        db.add(action_log)
        db.flush()
        out.append({
            "id": rec_id,
            "audience_id": rr["audience_id"],
            "audience_name": rr.get("audience_name"),
            "audience_type": rr.get("audience_type"),
            "action": action,
            "scale_percentage": rec.scale_percentage,
            "confidence": rec.confidence,
            "performance_bucket": rec.performance_bucket,
            "trend_state": rec.trend_state,
            "composite_score": float(rec.composite_score) if rec.composite_score else None,
            "reasons": rec.reasons,
            "risks": rec.risks,
            "metrics_snapshot": metrics_snapshot,
            "generated_at": rec.generated_at.isoformat() if rec.generated_at else None,
        })
    db.commit()
    return out
