from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List, Set, Optional
import json, os, math

@dataclass
class RuleCard:
    id: str
    topic: str
    tags: List[str]
    priority: float = 0.0
    trigger: Optional[str] = None
    mechanism: Optional[str] = None
    interpretation: Optional[str] = None
    action: Optional[str] = None
    cautions: Optional[List[str]] = None

TAG_NORMALIZE = {
    "정제": "정재",
    "편제": "편재",
    "겁제": "겁재",
    "식신생제": "식신생재",
    "상관생제": "상관생재",
    "식상생제": "식상생재",
    "간목": "인목",
    "신지금": "신금",
}

def canon_tag(t: str) -> str:
    s = " ".join(str(t).strip().split())
    return TAG_NORMALIZE.get(s, s)

def explode_tag_tokens(t: str) -> List[str]:
    """
    카드 태그를 토큰화해서 매칭 안정성을 높임.
    - "현금 흐름" 같은 태그가 있으면 ["현금 흐름","현금","흐름"] 모두로 취급
    """
    c = canon_tag(t)
    parts = [canon_tag(p) for p in c.split(" ") if len(p) >= 2]
    out, seen = [], set()
    for x in [c] + parts:
        if x and x not in seen:
            seen.add(x)
            out.append(x)
    return out

def safe_priority(p) -> float:
    try:
        v = float(p)
    except Exception:
        return 0.0
    # 0~10 or 0~100 모두 대응
    return min(v, 10.0) if v <= 10 else min(v, 100.0) / 10.0

class RuleCardStore:
    """
    JSONL 룰카드 로드 + 토픽 인덱스 + IDF(희소 태그 가중치) 생성
    """
    def __init__(self, path: str):
        self.path = path
        self.cards: List[RuleCard] = []
        self.by_topic: Dict[str, List[RuleCard]] = {}
        self.idf: Dict[str, float] = {}

    def load(self) -> None:
        p = self.path
        if not os.path.exists(p):
            raise FileNotFoundError(f"Rulecards JSONL not found: {p}")

        cards: List[RuleCard] = []
        with open(p, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    continue

                if not obj.get("id") or not obj.get("topic") or not obj.get("tags"):
                    continue

                cards.append(RuleCard(
                    id=obj["id"],
                    topic=obj["topic"],
                    tags=[canon_tag(x) for x in obj.get("tags", [])],
                    priority=safe_priority(obj.get("priority", 0)),
                    trigger=obj.get("trigger"),
                    mechanism=obj.get("mechanism"),
                    interpretation=obj.get("interpretation"),
                    action=obj.get("action"),
                    cautions=obj.get("cautions"),
                ))

        self.cards = cards
        self.by_topic = self._build_topic_index(cards)
        self.idf = self._build_idf(cards)

    def _build_topic_index(self, cards: List[RuleCard]) -> Dict[str, List[RuleCard]]:
        m: Dict[str, List[RuleCard]] = {}
        for c in cards:
            m.setdefault(c.topic, []).append(c)
        for k in list(m.keys()):
            m[k].sort(key=lambda x: x.priority, reverse=True)
        return m

    def _build_idf(self, cards: List[RuleCard]) -> Dict[str, float]:
        df: Dict[str, int] = {}
        N = len(cards)
        for c in cards:
            token_set: Set[str] = set()
            for t in c.tags:
                for x in explode_tag_tokens(t):
                    token_set.add(x)
            for t in token_set:
                df[t] = df.get(t, 0) + 1

        idf: Dict[str, float] = {}
        for t, d in df.items():
            idf[t] = math.log((N + 1) / (d + 1)) + 1.0
        return idf
