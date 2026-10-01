from dataclasses import dataclass
from datetime import date
import re


ATTRIBUTES = "deadline|due date|exam date|meeting date|location|status|room"
PREDICATES = "has been extended to|was extended to|has been postponed to|was postponed to|has changed to|was changed to|has been updated to|was updated to|is now|changed to|moved to|is not|is|was|:|="
FACT_RE = re.compile(rf"^(?P<subject>.+?)\s+(?P<attribute>{ATTRIBUTES})\s*(?P<predicate>{PREDICATES})\s*(?P<value>.+)$", re.I)
MONTHS = {name: number for number, name in enumerate(
    "january february march april may june july august september october november december".split(), 1
)}
DATE_RE = re.compile(r"\b(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+(20\d{2})\b", re.I)
UPDATE_CUES = ("extended", "postponed", "changed", "updated", "now", "moved")


@dataclass(frozen=True)
class Fact:
    subject: str
    attribute: str
    value: str
    norm_value: str
    explicit_update: bool


def normalize_value(value: str) -> str:
    value = " ".join(value.casefold().strip().rstrip(" .;!").split())

    def convert(match: re.Match[str]) -> str:
        try:
            return date(int(match[3]), MONTHS[match[2].lower()], int(match[1])).isoformat()
        except ValueError:
            return match[0].lower()

    return DATE_RE.sub(convert, value)


def extract_facts(text: str) -> list[Fact]:
    # V0 intentionally recognizes an explicit, narrow set of key/value facts.
    sentences = re.split(r"(?<=[.!?])\s+|\n+", text)
    facts: list[Fact] = []
    seen: set[tuple[str, str, str]] = set()
    for sentence in sentences:
        sentence = sentence.strip().rstrip(" .;!")
        sentence = re.sub(r"^(?:the|a|an)\s+", "", sentence, flags=re.I)
        match = FACT_RE.match(sentence)
        if not match:
            continue
        subject = " ".join(match["subject"].strip().split()).casefold()
        attribute = match["attribute"].casefold()
        attribute = {"due date": "deadline"}.get(attribute, attribute)
        value = match["value"].strip()
        if not subject or len(subject) > 120 or not value or len(value) > 160:
            continue
        predicate = match["predicate"].casefold()
        if predicate == "is not":
            value = "not " + value
        fact = Fact(subject, attribute, value, normalize_value(value), any(cue in predicate for cue in UPDATE_CUES))
        key = (fact.subject, fact.attribute, fact.norm_value)
        if key not in seen:
            seen.add(key)
            facts.append(fact)
    return facts


def classify(existing: Fact | None, new: Fact, related: bool = False) -> tuple[str, float, str]:
    if existing is None:
        if related:
            return "RELATED_INFORMATION", 0.8, "Same subject, different attribute; both facts can coexist."
        return "NEW_INFORMATION", 1.0, "No existing structured fact uses this subject and attribute."
    if existing.norm_value == new.norm_value:
        return "DUPLICATE", 1.0, "Same normalized subject, attribute, and value."
    if new.explicit_update:
        return "POTENTIAL_UPDATE", 0.95, "Same subject and attribute, different value, with an explicit change cue; review before replacing."
    return "CONTRADICTION", 0.9, "Same subject and attribute but different values, without an explicit update cue; review both sources."
