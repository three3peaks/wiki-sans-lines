"""Synonym graph: walk nearby senses until a lexicon word is found."""

from __future__ import annotations

from collections import deque

from wiki_sans.nltk_setup import get_wn, wordnet_ready

# Compact groups of near-synonyms. Shared words stitch the groups into a graph.
_FALLBACK_GROUPS = (
    ("want", "wish", "desire", "need"),
    ("go", "leave", "walk", "move", "head"),
    ("come", "arrive", "return"),
    ("see", "look", "watch", "notice"),
    ("say", "tell", "speak", "talk"),
    ("think", "believe", "guess", "suppose"),
    ("know", "understand", "realize"),
    ("get", "take", "grab", "receive"),
    ("give", "offer", "hand"),
    ("make", "create", "build"),
    ("kill", "destroy", "murder", "slay"),
    ("fight", "battle", "attack"),
    ("help", "aid", "save"),
    ("hurt", "harm", "pain", "injure"),
    ("like", "love", "enjoy"),
    ("hate", "dislike", "despise"),
    ("try", "attempt"),
    ("start", "begin"),
    ("stop", "end", "finish", "quit"),
    ("stay", "remain", "wait"),
    ("run", "flee", "escape"),
    ("eat", "devour", "consume"),
    ("sleep", "rest", "nap"),
    ("die", "perish"),
    ("live", "exist"),
    ("feel", "sense"),
    ("hear", "listen"),
    ("find", "discover"),
    ("keep", "hold", "save"),
    ("let", "allow"),
    ("ask", "question"),
    ("answer", "reply"),
    ("please", "kindly"),
    ("sorry", "apologize"),
    ("home", "house", "place"),
    ("friend", "pal", "buddy", "partner", "chap", "fellow"),
    ("enemy", "foe"),
    ("kid", "child", "human"),
    ("person", "someone", "somebody"),
    ("monster", "creature"),
    ("soul", "spirit"),
    ("power", "strength"),
    ("fear", "terror", "dread"),
    ("hope", "wish"),
    ("truth", "fact"),
    ("lie", "untruth"),
    ("story", "tale"),
    ("room", "place"),
    ("door", "gate"),
    ("path", "way", "road"),
    ("world", "surface", "earth"),
    ("time", "moment"),
    ("day", "night"),
    ("good", "nice", "kind", "great"),
    ("bad", "awful", "terrible", "wrong"),
    ("big", "huge", "great", "large"),
    ("small", "little", "tiny"),
    ("happy", "glad", "pleased"),
    ("sad", "unhappy", "miserable"),
    ("angry", "mad"),
    ("scared", "afraid", "frightened", "frighten"),
    ("enormous", "huge", "giant", "big"),
    ("beast", "monster", "creature"),
    ("strange", "weird", "odd"),
    ("true", "real"),
    ("false", "wrong"),
    ("fast", "quick", "quickly"),
    ("slow", "slowly"),
    ("very", "really", "quite"),
    ("maybe", "perhaps", "possibly"),
    ("yes", "yeah", "yep"),
    ("no", "nope"),
    ("hello", "hi", "hey"),
    ("goodbye", "bye", "farewell"),
    ("because", "since"),
    ("but", "however"),
    ("also", "too"),
    ("now", "currently"),
    ("never", "not"),
    ("always", "forever"),
    ("here", "there"),
    ("how", "why"),
    ("something", "anything"),
    ("nothing", "none"),
    ("everyone", "everybody"),
    ("everything", "all"),
    ("method", "way", "process", "plan", "system", "idea"),
    ("algorithm", "method", "process", "plan", "system", "way"),
    ("photosynthesis", "plant", "light", "life", "power"),
    ("science", "study", "knowledge"),
    ("machine", "thing", "system"),
    ("computer", "machine"),
    ("problem", "trouble", "issue"),
    ("reason", "cause", "why"),
    ("work", "job", "task"),
    ("play", "game"),
    ("remember", "memory", "think"),
    ("dream", "sleep", "hope"),
    ("magic", "power"),
    ("dark", "night"),
    ("hot", "fire", "burn"),
    ("cold", "ice"),
    ("food", "meal", "eat"),
    ("water", "drink"),
    ("gold", "money"),
    ("song", "music"),
    ("family", "home"),
    ("city", "town", "place"),
    ("body", "form"),
    ("voice", "sound", "speak"),
    ("choice", "pick", "choose"),
    ("change", "turn"),
    ("protect", "save", "guard"),
    ("break", "smash", "destroy"),
    ("open", "unlock"),
    ("close", "shut"),
    ("old", "ancient"),
    ("new", "fresh"),
    ("empty", "nothing"),
    ("full", "all"),
    ("quiet", "silent"),
    ("loud", "noise"),
    ("pretty", "beautiful", "nice"),
    ("ugly", "awful"),
    ("smart", "clever", "know"),
    ("stupid", "dumb"),
    ("strong", "power", "strength"),
    ("weak", "frail"),
    ("safe", "protect"),
    ("danger", "risk", "fear"),
    ("secret", "hidden"),
    ("free", "open"),
    ("catch", "grab", "get"),
    ("lose", "miss"),
    ("win", "beat"),
    ("learn", "study", "know"),
    ("teach", "show", "tell"),
    ("bring", "carry", "take"),
    ("put", "place", "set"),
    ("call", "name", "say"),
    ("use", "need"),
    ("wait", "stay"),
    ("follow", "go"),
    ("lead", "guide", "head"),
    ("stand", "stay"),
    ("sit", "rest"),
    ("fall", "drop"),
    ("alone", "only"),
    ("again", "more"),
    ("enough", "plenty"),
    ("almost", "near"),
    ("still", "yet"),
    ("already", "now"),
    ("soon", "later"),
    ("today", "day"),
    ("tomorrow", "day"),
    ("yesterday", "day"),
    ("people", "person", "human"),
    ("word", "name", "say"),
    ("number", "count"),
    ("part", "piece"),
    ("kind", "type", "sort"),
    ("thing", "stuff", "item"),
)

_FALLBACK: dict[str, list[str]] = {}
for group in _FALLBACK_GROUPS:
    for word in group:
        bucket = _FALLBACK.setdefault(word, [])
        for item in group:
            if item != word and item not in bucket:
                bucket.append(item)

_WN_POS = {
    "JJ": "a",
    "JJR": "a",
    "JJS": "a",
    "NN": "n",
    "NNP": "n",
    "NNPS": "n",
    "NNS": "n",
    "RB": "r",
    "RBR": "r",
    "RBS": "r",
    "VB": "v",
    "VBD": "v",
    "VBG": "v",
    "VBN": "v",
    "VBP": "v",
    "VBZ": "v",
}

_RELATION_RANK = {
    "synonym": 0,
    "similar": 1,
    "near": 2,
    "hypernym": 3,
}

MAX_DEPTH = 4
MAX_VISITS = 280

_wn_neighbor_cache: dict[tuple[str, str], list[tuple[str, str]]] = {}


def related_words(word: str, tag: str) -> list[tuple[str, str]]:
    seen: set[str] = {word.casefold()}
    related: list[tuple[str, str]] = []

    def add(name: str, via: str) -> None:
        cleaned = name.replace("_", " ").casefold()
        if " " in cleaned or cleaned in seen:
            return
        seen.add(cleaned)
        related.append((cleaned, via))

    for item, via in _neighbors(word, tag):
        add(item, via)
    return related


def closest_in_lexicon(word: str, tag: str, lexicon) -> tuple[str, str] | None:
    """Walk the synonym graph until a corpus word is found."""
    start = word.casefold()
    if lexicon.get(start) is not None:
        return start, "corpus"

    queue: deque[tuple[str, int, str]] = deque([(start, 0, "synonym")])
    seen = {start}
    best_at_depth: list[tuple[str, str]] | None = None
    found_depth: int | None = None
    visits = 0

    while queue:
        current, depth, via = queue.popleft()
        visits += 1
        if visits > MAX_VISITS:
            break
        if depth > 0 and lexicon.get(current) is not None:
            if found_depth is None:
                found_depth = depth
                best_at_depth = [(current, via)]
            elif depth == found_depth:
                best_at_depth.append((current, via))
            continue
        if found_depth is not None and depth >= found_depth:
            continue
        if depth >= MAX_DEPTH:
            continue
        for nxt, rel in _neighbors(current, tag):
            if nxt in seen:
                continue
            seen.add(nxt)
            hop = rel if depth == 0 else ("near" if rel == "synonym" else rel)
            queue.append((nxt, depth + 1, hop))

    if not best_at_depth:
        return None
    best_at_depth.sort(key=lambda item: _RELATION_RANK.get(item[1], 9))
    chosen, via = best_at_depth[0]
    if found_depth and found_depth > 1 and via == "synonym":
        via = "near"
    return chosen, via


def _neighbors(word: str, tag: str) -> list[tuple[str, str]]:
    folded = word.casefold()
    items: list[tuple[str, str]] = []
    seen = {folded}
    for item in _FALLBACK.get(folded, ()):
        if item not in seen:
            seen.add(item)
            items.append((item, "synonym"))
    for item, via in _wordnet_neighbors(folded, tag):
        if item not in seen:
            seen.add(item)
            items.append((item, via))
    return items


def _wordnet_neighbors(word: str, tag: str) -> list[tuple[str, str]]:
    wordnet = get_wn()
    if not wordnet_ready() or wordnet is None:
        return []
    key = (word, _WN_POS.get(tag, ""))
    cached = _wn_neighbor_cache.get(key)
    if cached is not None:
        return cached

    found: list[tuple[str, str]] = []
    seen = {word}

    def add(name: str, via: str) -> None:
        cleaned = name.replace("_", " ").casefold()
        if " " in cleaned or cleaned in seen:
            return
        seen.add(cleaned)
        found.append((cleaned, via))

    try:
        pos = _WN_POS.get(tag)
        synsets = list(wordnet.synsets(word, pos=pos)[:8]) if pos else []
        if not synsets:
            synsets = list(wordnet.synsets(word)[:8])
        for syn in synsets:
            for lemma in syn.lemmas():
                add(lemma.name(), "synonym")
                for related in lemma.derivationally_related_forms()[:3]:
                    add(related.name(), "near")
            for other in syn.similar_tos()[:4]:
                for lemma in other.lemmas():
                    add(lemma.name(), "similar")
            for other in syn.also_sees()[:3]:
                for lemma in other.lemmas():
                    add(lemma.name(), "near")
            for other in syn.verb_groups()[:3]:
                for lemma in other.lemmas():
                    add(lemma.name(), "near")
            for hyper in syn.hypernyms()[:3]:
                for lemma in hyper.lemmas():
                    add(lemma.name(), "hypernym")
    except LookupError:
        found = []

    _wn_neighbor_cache[key] = found
    return found
