def weighted_total(marks, weights):
    # marks: {criterion_id: mark}, weights: {criterion_id: weight}
    total_weight = sum(weights.values())
    if total_weight == 0:
        return 0.0
    return sum(marks.get(cid, 0) * w for cid, w in weights.items()) / total_weight


def build_ranking(candidates, criteria, scores):
    weights = {c.id: c.weight for c in criteria}

    # candidate -> judge -> {criterion: marks}
    grouped = {}
    for s in scores:
        grouped.setdefault(s.candidate_id, {}).setdefault(s.judge_id, {})[s.criterion_id] = s.marks

    results = []
    for cand in candidates:
        totals = [weighted_total(m, weights) for m in grouped.get(cand.id, {}).values()]
        avg = sum(totals) / len(totals) if totals else None
        results.append({
            "candidate_id": cand.id,
            "name": cand.name,
            "position": cand.position,
            "judges_scored": len(totals),
            "final_score": round(avg, 2) if avg is not None else None,
        })

    # highest score first, unscored candidates last
    results.sort(key=lambda r: (r["final_score"] is None, -(r["final_score"] or 0)))
    rank = 1
    for r in results:
        if r["final_score"] is None:
            r["rank"] = None
        else:
            r["rank"] = rank
            rank += 1
    return results