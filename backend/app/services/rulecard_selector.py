from __future__ import annotations
from typing import Dict, List, Set, Tuple
from .rulecards_store import RuleCardStore, RuleCard, canon_tag, explode_tag_tokens

def score_card(store: RuleCardStore, card: RuleCard, user_tags: Set[str], focus_tags: Set[str]) -> Dict:
    tokens = set()
    for t in card.tags:
        for x in explode_tag_tokens(t):
            tokens.add(x)

    overlap = 0
    match_score = 0.0
    focus_hit = 0

    for t in tokens:
        if t in user_tags:
            overlap += 1
            match_score += store.idf.get(t, 1.0)
        if t in focus_tags:
            focus_hit += 1

    total = match_score + (focus_hit * 0.35) + (card.priority * 0.25)
    return {"overlap": overlap, "matchScore": match_score, "focusHit": focus_hit, "total": total}

def select_cards_for_preset(store: RuleCardStore, preset: Dict, feature_tags: List[str]) -> Dict:
    used: Set[str] = set()
    user_tags: Set[str] = set()
    for t in feature_tags:
        for x in explode_tag_tokens(t):
            user_tags.add(x)

    out_sections = []
    for sec in preset["sections"]:
        focus = set(canon_tag(x) for x in sec["focusTags"])
        sec_cards: List[RuleCard] = []
        by_stage = {"s1":0,"s2":0,"s3":0,"s4":0}

        for tq in sec["perTopic"]:
            topic = tq["topic"]
            k = int(tq["k"])

            pool = [c for c in store.by_topic.get(topic, []) if c.id not in used]

            # HEALTH 토픽이 부족하면 ELEMENTS에서 보충
            if topic == "HEALTH" and len(pool) < k:
                pool = [c for c in store.by_topic.get("ELEMENTS", []) if c.id not in used]

            ranked: List[Tuple[RuleCard, Dict]] = []
            for c in pool:
                s = score_card(store, c, user_tags, focus)
                ranked.append((c, s))
            ranked.sort(key=lambda x: x[1]["total"], reverse=True)

            s1 = [x for x in ranked if x[1]["overlap"] >= 2]        # 정밀
            s2 = [x for x in ranked if x[1]["overlap"] >= 1]        # 완화
            s3 = [x for x in ranked if x[1]["focusHit"] >= 1]       # 섹션 포커스
            need = k
            got = 0

            def pick(lst, stage):
                nonlocal got
                for c, _s in lst:
                    if got >= need: break
                    if c.id in used: continue
                    used.add(c.id)
                    sec_cards.append(c)
                    by_stage[stage] += 1
                    got += 1

            pick(s1, "s1")
            pick(s2, "s2")
            pick(s3, "s3")
            pick(ranked, "s4")

        overlaps = [score_card(store, c, user_tags, focus)["overlap"] for c in sec_cards]
        avg_overlap = round(sum(overlaps)/len(overlaps), 2) if overlaps else 0.0

        out_sections.append({
            "key": sec["key"],
            "title": sec["title"],
            "cards": [c.__dict__ for c in sec_cards],
            "meta": {
                "target": sec["totalTarget"],
                "picked": len(sec_cards),
                "byStage": by_stage,
                "avgOverlap": avg_overlap,
            }
        })

    return {"preset": preset["name"], "sections": out_sections}
