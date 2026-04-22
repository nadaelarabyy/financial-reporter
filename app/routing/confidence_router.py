from app.config import HIGH_CONFIDENCE_THRESHOLD, MEDIUM_CONFIDENCE_THRESHOLD
from app.schemas import TableQualityScore, RoutingDecision


def route_table(score: TableQualityScore) -> RoutingDecision:
    if score.overall_confidence >= HIGH_CONFIDENCE_THRESHOLD:
        return RoutingDecision(
            route="DETERMINISTIC_ONLY",
            reason=f"High confidence ({score.overall_confidence})"
        )

    if score.overall_confidence >= MEDIUM_CONFIDENCE_THRESHOLD:
        return RoutingDecision(
            route="DETERMINISTIC_PLUS_AI_NORMALIZATION",
            reason=f"Medium confidence ({score.overall_confidence})"
        )

    return RoutingDecision(
        route="AI_FALLBACK",
        reason=f"Low confidence ({score.overall_confidence})"
    )