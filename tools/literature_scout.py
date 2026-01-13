#!/usr/bin/env python3
"""Best-effort literature scout with provenance, caching, and offline safety."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import unicodedata
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import quote_plus
from urllib.request import Request, urlopen

DEFAULT_MAX_RESULTS = int(os.getenv("LITERATURE_SCOUT_MAX_RESULTS", "5"))
DEFAULT_MAX_CANDIDATES = int(os.getenv("LITERATURE_SCOUT_MAX_CANDIDATES", "20"))
DEFAULT_CACHE_TTL_DAYS = int(os.getenv("LITERATURE_SCOUT_CACHE_TTL_DAYS", "14"))

STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "has",
    "in",
    "is",
    "it",
    "its",
    "of",
    "on",
    "or",
    "that",
    "the",
    "their",
    "this",
    "to",
    "was",
    "were",
    "with",
    "without",
    "true",
}

CHATGPT_PROMPT_VERSION = "v1"


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def ascii_safe(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    return normalized.encode("ascii", "ignore").decode("ascii")


def normalize_title(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def detect_offline(explicit_offline: bool) -> bool:
    if explicit_offline:
        return True
    env_flags = {
        os.getenv("LITERATURE_SCOUT_OFFLINE", "").lower(),
        os.getenv("NO_NETWORK", "").lower(),
    }
    if env_flags & {"1", "true", "yes"}:
        return True
    ci_flag = os.getenv("CI")
    return bool(ci_flag) and ci_flag.lower() not in {"0", "false", "no"}


def tokenise(text: str) -> List[str]:
    tokens = re.findall(r"[A-Za-z0-9]+", text.lower())
    return [token for token in tokens if token and token not in STOPWORDS]


def extract_keywords(text: Optional[str], limit: int = 8) -> List[str]:
    if not text:
        return []
    cleaned = re.sub(r"\$[^$]*\$", " ", text)
    cleaned = re.sub(r"\\[A-Za-z]+", " ", cleaned)
    counts: Dict[str, int] = {}
    for token in tokenise(cleaned):
        if len(token) < 4:
            continue
        counts[token] = counts.get(token, 0) + 1
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return [token for token, _ in ranked[:limit]]


def build_queries(problem_number: int, title: Optional[str], keywords: List[str]) -> List[str]:
    queries: List[str] = []
    if title:
        queries.append(title)
    if keywords:
        queries.append(" ".join(keywords[:6]))
    queries.append(f"Erdos problem {problem_number}")
    unique: List[str] = []
    seen = set()
    for query in queries:
        cleaned = " ".join(query.split())
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            unique.append(cleaned)
    return unique


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def cache_path(cache_dir: Path, provider: str, query: str) -> Path:
    digest = hashlib.sha256(f"{provider}\n{query}".encode("utf-8")).hexdigest()
    return cache_dir / provider / f"{digest}.json"


def load_cache(path: Path, ttl_days: int) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    fetched_at = data.get("fetched_at")
    if not isinstance(fetched_at, str):
        return None
    try:
        fetched_dt = dt.datetime.fromisoformat(fetched_at.replace("Z", "+00:00"))
    except Exception:
        return None
    if dt.datetime.now(dt.timezone.utc) - fetched_dt > dt.timedelta(days=ttl_days):
        return None
    return data


def save_cache(path: Path, payload: Dict[str, Any]) -> None:
    ensure_dir(path.parent)
    path.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8")


def log_event(log_path: Path, message: str) -> None:
    ensure_dir(log_path.parent)
    timestamp = now_iso()
    with log_path.open("a", encoding="utf-8", errors="ignore") as handle:
        handle.write(f"[{timestamp}] {message}\n")


def http_get(url: str, timeout: int = 10, headers: Optional[Dict[str, str]] = None) -> bytes:
    base_headers = {"User-Agent": "ErdosLab literature scout"}
    if headers:
        base_headers.update(headers)
    req = Request(url, headers=base_headers)
    with urlopen(req, timeout=timeout) as response:
        return response.read()


def fetch_cached(
    provider: str,
    query: str,
    url: str,
    cache_dir: Path,
    offline: bool,
    ttl_days: int,
    expect: str,
    headers: Optional[Dict[str, str]] = None,
) -> Tuple[Optional[Any], bool, Optional[str]]:
    path = cache_path(cache_dir, provider, query)
    cached = load_cache(path, ttl_days)
    if cached is not None:
        return cached.get("payload"), True, None
    if offline:
        return None, False, "offline/no cache"
    try:
        raw = http_get(url, headers=headers)
    except Exception as exc:
        return None, False, str(exc)
    if expect == "json":
        try:
            payload = json.loads(raw.decode("utf-8", errors="replace"))
        except Exception as exc:
            return None, False, f"json decode error: {exc}"
    else:
        payload = raw.decode("utf-8", errors="replace")
    save_cache(
        path,
        {
            "fetched_at": now_iso(),
            "url": url,
            "payload": payload,
        },
    )
    return payload, False, None


def doi_to_id(doi: Optional[str]) -> Optional[str]:
    if not doi:
        return None
    doi = doi.strip()
    if doi.startswith("http"):
        doi = doi.split("doi.org/")[-1]
    return doi.lower()


def compute_confidence(title: str, keywords: List[str], id_type: str) -> Tuple[float, List[str]]:
    title_lower = title.lower()
    matched = [kw for kw in keywords if kw.lower() in title_lower]
    reasons: List[str] = []
    if matched:
        reasons.append(f"keyword match: {', '.join(matched[:4])}")
    else:
        reasons.append("no keyword match in title")
    reasons.append(f"identifier: {id_type}")
    base = 0.35 + (0.1 if id_type in {"doi", "arxiv"} else 0.05)
    score = min(0.95, base + 0.05 * len(matched))
    return score, reasons


def build_candidate(
    *,
    candidate_id: str,
    id_type: str,
    title: str,
    authors: List[str],
    year: Optional[str],
    url: Optional[str],
    provider: str,
    query: str,
    source_url: str,
    cache_hit: bool,
    keywords: List[str],
) -> Dict[str, Any]:
    safe_title = ascii_safe(title)
    safe_authors = [ascii_safe(author) for author in authors]
    confidence, reasons = compute_confidence(safe_title, keywords, id_type)
    return {
        "id": candidate_id,
        "id_type": id_type,
        "title": safe_title,
        "authors": safe_authors,
        "year": year,
        "url": url,
        "confidence": confidence,
        "reasons": reasons,
        "status": "NEEDS_REVIEW",
        "provenance": [
            {
                "provider": provider,
                "query": query,
                "source_url": source_url,
                "fetched_at": now_iso(),
                "cache_hit": cache_hit,
            }
        ],
    }


def query_openalex(
    query: str,
    cache_dir: Path,
    offline: bool,
    ttl_days: int,
    keywords: List[str],
) -> Tuple[List[Dict[str, Any]], Dict[str, Any], Optional[str]]:
    url = (
        "https://api.openalex.org/works?search="
        f"{quote_plus(query)}&per_page={DEFAULT_MAX_RESULTS}"
    )
    payload, cache_hit, error = fetch_cached(
        "openalex", query, url, cache_dir, offline, ttl_days, "json"
    )
    info = {
        "provider": "openalex",
        "query": query,
        "url": url,
        "cache_hit": cache_hit,
        "status": "ok" if error is None else "error",
        "error": error,
        "timestamp": now_iso(),
    }
    if error or not isinstance(payload, dict):
        return [], info, error
    results = payload.get("results")
    if not isinstance(results, list):
        return [], info, "unexpected payload"
    candidates: List[Dict[str, Any]] = []
    for item in results:
        if not isinstance(item, dict):
            continue
        title = item.get("display_name")
        if not isinstance(title, str):
            continue
        ids = item.get("ids") or {}
        doi = doi_to_id(ids.get("doi") if isinstance(ids, dict) else None)
        openalex_id = item.get("id")
        candidate_id = doi or openalex_id
        if not candidate_id:
            continue
        id_type = "doi" if doi else "openalex"
        year = item.get("publication_year")
        authors = []
        for author in item.get("authorships", []) or []:
            name = author.get("author", {}).get("display_name")
            if isinstance(name, str):
                authors.append(name)
        url_value = None
        if doi:
            url_value = f"https://doi.org/{doi}"
        elif isinstance(openalex_id, str):
            url_value = openalex_id
        candidates.append(
            build_candidate(
                candidate_id=candidate_id,
                id_type=id_type,
                title=title,
                authors=authors[:5],
                year=str(year) if year else None,
                url=url_value,
                provider="openalex",
                query=query,
                source_url=url,
                cache_hit=cache_hit,
                keywords=keywords,
            )
        )
    return candidates, info, None


def query_crossref(
    query: str,
    cache_dir: Path,
    offline: bool,
    ttl_days: int,
    keywords: List[str],
) -> Tuple[List[Dict[str, Any]], Dict[str, Any], Optional[str]]:
    url = (
        "https://api.crossref.org/works?query="
        f"{quote_plus(query)}&rows={DEFAULT_MAX_RESULTS}"
    )
    payload, cache_hit, error = fetch_cached(
        "crossref", query, url, cache_dir, offline, ttl_days, "json"
    )
    info = {
        "provider": "crossref",
        "query": query,
        "url": url,
        "cache_hit": cache_hit,
        "status": "ok" if error is None else "error",
        "error": error,
        "timestamp": now_iso(),
    }
    if error or not isinstance(payload, dict):
        return [], info, error
    message = payload.get("message")
    items = message.get("items") if isinstance(message, dict) else None
    if not isinstance(items, list):
        return [], info, "unexpected payload"
    candidates: List[Dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        doi = doi_to_id(item.get("DOI"))
        if not doi:
            continue
        title_list = item.get("title")
        title = title_list[0] if isinstance(title_list, list) and title_list else None
        if not isinstance(title, str):
            continue
        authors = []
        for author in item.get("author", []) or []:
            given = author.get("given", "")
            family = author.get("family", "")
            name = " ".join(part for part in [given, family] if part)
            if name:
                authors.append(name)
        year = None
        issued = item.get("issued", {}).get("date-parts")
        if isinstance(issued, list) and issued and isinstance(issued[0], list):
            if issued[0]:
                year = str(issued[0][0])
        candidates.append(
            build_candidate(
                candidate_id=doi,
                id_type="doi",
                title=title,
                authors=authors[:5],
                year=year,
                url=f"https://doi.org/{doi}",
                provider="crossref",
                query=query,
                source_url=url,
                cache_hit=cache_hit,
                keywords=keywords,
            )
        )
    return candidates, info, None


def parse_arxiv_id(entry_id: str) -> Optional[str]:
    match = re.search(r"arxiv.org/abs/(.+)", entry_id)
    if not match:
        return None
    arxiv_id = match.group(1).strip()
    return arxiv_id if re.search(r"\d", arxiv_id) else None


def query_arxiv(
    query: str,
    cache_dir: Path,
    offline: bool,
    ttl_days: int,
    keywords: List[str],
) -> Tuple[List[Dict[str, Any]], Dict[str, Any], Optional[str]]:
    url = (
        "http://export.arxiv.org/api/query?search_query=all:"
        f"{quote_plus(query)}&start=0&max_results={DEFAULT_MAX_RESULTS}"
    )
    payload, cache_hit, error = fetch_cached(
        "arxiv", query, url, cache_dir, offline, ttl_days, "xml"
    )
    info = {
        "provider": "arxiv",
        "query": query,
        "url": url,
        "cache_hit": cache_hit,
        "status": "ok" if error is None else "error",
        "error": error,
        "timestamp": now_iso(),
    }
    if error or not isinstance(payload, str):
        return [], info, error
    try:
        root = ET.fromstring(payload)
    except Exception as exc:
        return [], info, f"xml parse error: {exc}"
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    candidates: List[Dict[str, Any]] = []
    for entry in root.findall("atom:entry", ns):
        entry_id = entry.findtext("atom:id", default="", namespaces=ns)
        arxiv_id = parse_arxiv_id(entry_id)
        if not arxiv_id:
            continue
        title = entry.findtext("atom:title", default="", namespaces=ns).strip()
        if not title:
            continue
        authors = []
        for author in entry.findall("atom:author", ns):
            name = author.findtext("atom:name", default="", namespaces=ns)
            if name:
                authors.append(name.strip())
        published = entry.findtext("atom:published", default="", namespaces=ns)
        year = published[:4] if published else None
        candidates.append(
            build_candidate(
                candidate_id=arxiv_id,
                id_type="arxiv",
                title=title,
                authors=authors[:5],
                year=year,
                url=f"https://arxiv.org/abs/{arxiv_id}",
                provider="arxiv",
                query=query,
                source_url=url,
                cache_hit=cache_hit,
                keywords=keywords,
            )
        )
    return candidates, info, None


def query_zbmath(
    query: str,
    cache_dir: Path,
    offline: bool,
    ttl_days: int,
    keywords: List[str],
) -> Tuple[List[Dict[str, Any]], Dict[str, Any], Optional[str]]:
    url = (
        "https://api.zbmath.org/v1/document/_search?search_string="
        f"{quote_plus(query)}&results_per_page={DEFAULT_MAX_RESULTS}"
    )
    payload, cache_hit, error = fetch_cached(
        "zbmath", query, url, cache_dir, offline, ttl_days, "json"
    )
    info = {
        "provider": "zbmath",
        "query": query,
        "url": url,
        "cache_hit": cache_hit,
        "status": "ok" if error is None else "error",
        "error": error,
        "timestamp": now_iso(),
    }
    if error or not isinstance(payload, dict):
        return [], info, error
    results = payload.get("result")
    if not isinstance(results, list):
        return [], info, "unexpected payload"
    candidates: List[Dict[str, Any]] = []
    for item in results:
        if not isinstance(item, dict):
            continue
        zb_id = item.get("id")
        if not zb_id:
            continue
        title = item.get("title", {}).get("title")
        if not isinstance(title, str):
            continue
        authors = []
        contributors = item.get("contributors", {}).get("authors") or []
        for author in contributors:
            name = author.get("name")
            if isinstance(name, str):
                authors.append(name)
        year = item.get("year")
        zb_url = item.get("zbmath_url")
        candidates.append(
            build_candidate(
                candidate_id=str(zb_id),
                id_type="zbmath",
                title=title,
                authors=authors[:5],
                year=str(year) if year else None,
                url=zb_url if isinstance(zb_url, str) else None,
                provider="zbmath",
                query=query,
                source_url=url,
                cache_hit=cache_hit,
                keywords=keywords,
            )
        )
    return candidates, info, None


def query_semantic_scholar(
    query: str,
    cache_dir: Path,
    offline: bool,
    ttl_days: int,
    keywords: List[str],
    api_key: Optional[str],
) -> Tuple[List[Dict[str, Any]], Dict[str, Any], Optional[str]]:
    if not api_key:
        info = {
            "provider": "semantic_scholar",
            "query": query,
            "url": None,
            "cache_hit": False,
            "status": "skipped",
            "error": "missing SEMANTIC_SCHOLAR_API_KEY",
            "timestamp": now_iso(),
        }
        return [], info, "missing api key"
    url = (
        "https://api.semanticscholar.org/graph/v1/paper/search?"
        f"query={quote_plus(query)}&limit={DEFAULT_MAX_RESULTS}"
        "&fields=title,authors,year,externalIds,url"
    )
    payload, cache_hit, error = fetch_cached(
        "semantic_scholar",
        query,
        url,
        cache_dir,
        offline,
        ttl_days,
        "json",
        headers={"x-api-key": api_key},
    )
    info = {
        "provider": "semantic_scholar",
        "query": query,
        "url": url,
        "cache_hit": cache_hit,
        "status": "ok" if error is None else "error",
        "error": error,
        "timestamp": now_iso(),
    }
    if error or not isinstance(payload, dict):
        return [], info, error
    candidates: List[Dict[str, Any]] = []
    for item in payload.get("data", []) or []:
        if not isinstance(item, dict):
            continue
        external = item.get("externalIds", {}) if isinstance(item.get("externalIds"), dict) else {}
        doi = doi_to_id(external.get("DOI"))
        arxiv_id = external.get("ArXiv")
        candidate_id = doi or arxiv_id
        if not candidate_id:
            continue
        id_type = "doi" if doi else "arxiv"
        title = item.get("title")
        if not isinstance(title, str):
            continue
        authors = []
        for author in item.get("authors", []) or []:
            name = author.get("name")
            if isinstance(name, str):
                authors.append(name)
        year = item.get("year")
        url_value = item.get("url")
        candidates.append(
            build_candidate(
                candidate_id=candidate_id,
                id_type=id_type,
                title=title,
                authors=authors[:5],
                year=str(year) if year else None,
                url=url_value if isinstance(url_value, str) else None,
                provider="semantic_scholar",
                query=query,
                source_url=url,
                cache_hit=cache_hit,
                keywords=keywords,
            )
        )
    return candidates, info, None


def merge_provenance(existing: Dict[str, Any], incoming: Dict[str, Any]) -> None:
    prov = existing.get("provenance")
    incoming_prov = incoming.get("provenance") or []
    if not isinstance(prov, list):
        prov = []
    for entry in incoming_prov:
        if entry not in prov:
            prov.append(entry)
    existing["provenance"] = prov
    if incoming.get("confidence", 0.0) > existing.get("confidence", 0.0):
        existing["confidence"] = incoming["confidence"]
        existing["reasons"] = incoming.get("reasons", existing.get("reasons", []))


def dedupe_candidates(candidates: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    deduped: Dict[str, Dict[str, Any]] = {}
    for candidate in candidates:
        candidate_id = candidate.get("id")
        id_type = candidate.get("id_type")
        if candidate_id and id_type:
            key = f"{id_type}:{str(candidate_id).lower()}"
        else:
            title = candidate.get("title", "")
            year = candidate.get("year", "")
            author = candidate.get("authors", [""])[0] if candidate.get("authors") else ""
            key = f"title:{normalize_title(title)}:{year}:{normalize_title(author)}"
        existing = deduped.get(key)
        if existing:
            merge_provenance(existing, candidate)
        else:
            deduped[key] = candidate
    return list(deduped.values())


def write_candidates_md(
    path: Path,
    candidates: List[Dict[str, Any]],
    generated_at: str,
    offline: bool,
    errors: List[str],
) -> None:
    lines = [
        "# Literature Candidates (UNVERIFIED)",
        "",
        f"Generated: {generated_at}",
        f"Offline: {'yes' if offline else 'no'}",
        "Status: discovery-only; NO results are verified.",
        "",
    ]
    if not candidates:
        lines.append("No verified candidates returned.")
        if errors:
            lines.append("Errors:")
            for err in errors:
                lines.append(f"- {ascii_safe(err)}")
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return
    lines.append("Candidates (ranked):")
    for idx, cand in enumerate(candidates, start=1):
        title = cand.get("title", "unknown title")
        url = cand.get("url") or ""
        identifier = f"{cand.get('id_type')}:{cand.get('id')}"
        year = cand.get("year") or "unknown year"
        confidence = cand.get("confidence", 0.0)
        lines.append(f"{idx}. {title} ({year})")
        if url:
            lines.append(f"   url: {url}")
        lines.append(f"   id: {identifier}")
        lines.append(f"   confidence: {confidence:.2f}")
        reasons = cand.get("reasons") or []
        if reasons:
            lines.append(f"   reasons: {', '.join(reasons)}")
        lines.append(f"   status: {cand.get('status', 'NEEDS_REVIEW')}")
    if errors:
        lines.append("")
        lines.append("Errors:")
        for err in errors:
            lines.append(f"- {ascii_safe(err)}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_queries_json(path: Path, queries: List[Dict[str, Any]], generated_at: str) -> None:
    payload = {"generated_at": generated_at, "queries": queries}
    path.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8")


def write_candidates_json(
    path: Path,
    problem_id: str,
    generated_at: str,
    offline: bool,
    candidates: List[Dict[str, Any]],
    queries: List[Dict[str, Any]],
    errors: List[str],
    solver_used_scout: bool = False,
) -> None:
    payload = {
        "problem_id": problem_id,
        "generated_at": generated_at,
        "offline": offline,
        "solver_used_scout": solver_used_scout,
        "queries": queries,
        "candidates": candidates,
        "errors": errors,
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8")


def write_triage_md(path: Path, candidates: List[Dict[str, Any]], generated_at: str) -> None:
    lines = [
        "# Literature Triage",
        "",
        f"Generated: {generated_at}",
        "",
    ]
    if not candidates:
        lines.append("No candidates to triage.")
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return
    for cand in candidates:
        identifier = f"{cand.get('id_type')}:{cand.get('id')}"
        title = cand.get("title", "unknown title")
        year = cand.get("year") or "unknown year"
        lines.append(f"- [ ] {identifier} ({year}) - {title} [NEEDS_REVIEW]")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def render_chatgpt_prompt(
    *,
    problem_id: str,
    problem_number: int,
    title: Optional[str],
    problem_url: str,
    forum_url: str,
    statement_text: Optional[str],
) -> str:
    keywords = extract_keywords(statement_text, limit=10)
    keyword_line = ", ".join(keywords) if keywords else "none"
    statement = statement_text or "TBD (statement unavailable)."
    title_line = title or f"Erdos Problem #{problem_number}"
    return (
        "# ChatGPT Pro Literature Scout Prompt (manual)\n"
        f"\nVersion: {CHATGPT_PROMPT_VERSION}\n"
        "\nYou are assisting a literature scout for an Erdos problem. "
        "Your task is to find candidate references in the mathematical literature. "
        "Do NOT claim the problem is solved. Do NOT mark anything as verified. "
        "Only output candidates with verifiable identifiers (DOI/arXiv/zbMATH/OpenAlex). "
        "If you cannot find suitable candidates, return an empty list and include an error note.\n"
        "\nProblem context:\n"
        f"- problem_id: {problem_id}\n"
        f"- title: {title_line}\n"
        f"- problem_url: {problem_url}\n"
        f"- forum_url: {forum_url}\n"
        f"- keywords: {keyword_line}\n"
        "\nFrozen statement:\n"
        f"{statement}\n"
        "\nOutput format (STRICT): return exactly one JSON object in a single ```json``` block.\n"
        "Do not include extra prose outside the JSON.\n"
        "\nRequired JSON schema:\n"
        "{\n"
        f'  \"problem_id\": \"{problem_id}\",\n'
        "  \"generated_at\": \"YYYY-MM-DD\",\n"
        "  \"solver_used_scout\": false,\n"
        "  \"queries\": [\n"
        "    {\"query\": \"...\", \"notes\": \"...\"}\n"
        "  ],\n"
        "  \"candidates\": [\n"
        "    {\n"
        "      \"id\": \"10.1234/abcd\" | \"2101.01234\" | \"3138648\" | \"https://openalex.org/W...\",\n"
        "      \"id_type\": \"doi\" | \"arxiv\" | \"zbmath\" | \"openalex\",\n"
        "      \"title\": \"...\",\n"
        "      \"authors\": [\"...\"],\n"
        "      \"year\": \"YYYY\",\n"
        "      \"url\": \"https://...\",\n"
        "      \"confidence\": 0.0,\n"
        "      \"reasons\": [\"why this might be relevant\"],\n"
        "      \"status\": \"NEEDS_REVIEW\"\n"
        "    }\n"
        "  ],\n"
        "  \"errors\": [\"... optional ...\"]\n"
        "}\n"
        "\nRules:\n"
        "- Include ONLY candidates with verifiable identifiers.\n"
        "- Provide at least one explicit reason per candidate.\n"
        "- Keep status = NEEDS_REVIEW.\n"
        "- Max 20 candidates.\n"
    )


def write_chatgpt_files(
    literature_dir: Path,
    prompt_text: str,
) -> None:
    ensure_dir(literature_dir)
    prompt_path = literature_dir / "chatgpt_prompt.md"
    response_path = literature_dir / "chatgpt_response.md"
    prompt_path.write_text(prompt_text.rstrip() + "\n", encoding="utf-8")
    if not response_path.exists():
        response_path.write_text(
            "# Paste ChatGPT Pro output below\n\n",
            encoding="utf-8",
        )


def run_literature_scout(
    *,
    problem_dir: Path,
    problem_id: str,
    problem_number: int,
    title: Optional[str],
    statement_text: Optional[str],
    offline: bool,
    cache_dir: Path,
    log_path: Path,
) -> None:
    generated_at = now_iso()
    offline = detect_offline(offline)
    ensure_dir(problem_dir / "literature")

    keywords = extract_keywords(statement_text, limit=10)
    queries = build_queries(problem_number, title, keywords)

    all_candidates: List[Dict[str, Any]] = []
    queries_log: List[Dict[str, Any]] = []
    errors: List[str] = []
    ttl_days = DEFAULT_CACHE_TTL_DAYS
    api_key = os.getenv("SEMANTIC_SCHOLAR_API_KEY")

    providers = [
        ("openalex", query_openalex),
        ("crossref", query_crossref),
        ("arxiv", query_arxiv),
        ("zbmath", query_zbmath),
    ]
    for query in queries:
        for name, handler in providers:
            results, info, error = handler(
                query=query,
                cache_dir=cache_dir,
                offline=offline,
                ttl_days=ttl_days,
                keywords=keywords,
            )
            queries_log.append(info)
            if error:
                errors.append(f"{name} query '{query}': {error}")
                log_event(log_path, f"{name} query '{query}' failed: {error}")
            else:
                log_event(log_path, f"{name} query '{query}' ok ({len(results)} results)")
            all_candidates.extend(results)
        results, info, error = query_semantic_scholar(
            query=query,
            cache_dir=cache_dir,
            offline=offline,
            ttl_days=ttl_days,
            keywords=keywords,
            api_key=api_key,
        )
        queries_log.append(info)
        if error and info.get("status") != "skipped":
            errors.append(f"semantic_scholar query '{query}': {error}")
            log_event(log_path, f"semantic_scholar query '{query}' failed: {error}")
        elif info.get("status") == "skipped":
            log_event(log_path, "semantic_scholar skipped (missing API key)")
        else:
            log_event(log_path, f"semantic_scholar query '{query}' ok ({len(results)} results)")
        all_candidates.extend(results)

    deduped = dedupe_candidates(all_candidates)
    deduped.sort(key=lambda cand: (-cand.get("confidence", 0.0), cand.get("year") or ""))
    deduped = deduped[:DEFAULT_MAX_CANDIDATES]

    literature_dir = problem_dir / "literature"
    write_candidates_md(
        literature_dir / "candidates.md",
        deduped,
        generated_at,
        offline,
        errors,
    )
    write_candidates_json(
        literature_dir / "candidates.json",
        problem_id,
        generated_at,
        offline,
        deduped,
        queries_log,
        errors,
        solver_used_scout=False,
    )
    write_queries_json(literature_dir / "queries.json", queries_log, generated_at)
    write_triage_md(literature_dir / "triage.md", deduped, generated_at)
