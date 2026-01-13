#!/usr/bin/env python3
"""Automate problem setup, freezing, and optional Lean import."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import html
import json
import re
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import Iterable, Optional, Tuple
from urllib.request import urlopen

import literature_scout
import solver_scaffold


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Automate Erdos problem setup and validation."
    )
    parser.add_argument(
        "problem",
        help="Problem id (e.g. 379 or P0379).",
    )
    parser.add_argument("--title", help="Optional problem title.")
    parser.add_argument(
        "--problem-url",
        help="Override the problem page URL.",
    )
    parser.add_argument(
        "--latex-url",
        help="Override the LaTeX snapshot URL.",
    )
    parser.add_argument(
        "--forum-url",
        help="Override the forum thread URL.",
    )
    parser.add_argument(
        "--lean-url",
        help="Override the external Lean file URL to import.",
    )
    parser.add_argument(
        "--theorem",
        help="Override the Lean theorem name for evidence.",
    )
    parser.add_argument(
        "--no-fetch",
        action="store_true",
        help="Skip network fetches; create placeholders.",
    )
    parser.add_argument(
        "--no-lean",
        action="store_true",
        help="Skip importing external Lean files.",
    )
    parser.add_argument(
        "--skip-checks",
        action="store_true",
        help="Skip policy/build checks.",
    )
    parser.add_argument(
        "--no-forum",
        action="store_true",
        help="Skip generating the forum post template.",
    )
    parser.add_argument(
        "--keep-active",
        action="store_true",
        help="Do not update problems/ACTIVE.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Allow overwriting an existing Lean file.",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Reuse an existing problem directory instead of failing.",
    )
    return parser.parse_args()


def normalize_problem_id(raw: str) -> Tuple[str, int]:
    match = re.fullmatch(r"[Pp]?(\d+)", raw.strip())
    if not match:
        raise ValueError(f"Invalid problem id: {raw!r}")
    number_str = match.group(1)
    number = int(number_str)
    width = max(4, len(number_str))
    return f"P{number:0{width}d}", number


def fetch_url(url: str) -> Tuple[bytes, str]:
    with urlopen(url) as response:
        data = response.read()
    text = data.decode("utf-8", errors="replace")
    return data, text


def extract_statement(html_text: str) -> Tuple[Optional[str], Optional[str]]:
    match = re.search(r'<div id="content"[^>]*>(.*?)</div>', html_text, re.S)
    if not match:
        return None, None
    raw_html = match.group(1).strip()
    text = html.unescape(raw_html)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    return raw_html, text.strip()


def extract_lean_links(html_text: str) -> list[str]:
    links = re.findall(r'href="([^"]+\.lean)"', html_text)
    cleaned = [html.unescape(link) for link in links]
    seen = set()
    unique = []
    for link in cleaned:
        if link not in seen:
            seen.add(link)
            unique.append(link)
    return unique


def find_cite_key(html_text: str) -> Optional[str]:
    match = re.search(r"addNewBox\('([^']+)'", html_text)
    if match:
        return match.group(1)
    match = re.search(r"#cite-([A-Za-z0-9_-]+)", html_text)
    if match:
        return match.group(1)
    return None


def pick_lean_links(links: Iterable[str], number: int) -> Tuple[Optional[str], Optional[str]]:
    proof = None
    statement = None
    pattern = re.compile(rf"erdos[_-]?{number}\.lean")
    for link in links:
        if "FormalConjectures/ErdosProblems" in link:
            statement = link
        if pattern.search(link):
            proof = link
    if proof is None and links:
        proof = next(iter(links))
    return proof, statement


def find_theorem_name(text: str, number: int) -> Optional[str]:
    match = re.search(rf"\btheorem\s+(erdos[_-]?{number})\b", text)
    if match:
        return match.group(1)
    return None


def run(cmd: list[str], root: Path) -> None:
    subprocess.run(cmd, check=True, cwd=root)


def run_capture(cmd: list[str], root: Path) -> Optional[str]:
    try:
        result = subprocess.run(
            cmd,
            check=True,
            cwd=root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except subprocess.CalledProcessError:
        return None
    return result.stdout.strip()


def write_text(path: Path, content: str) -> None:
    path.write_text(content.rstrip() + "\n", encoding="utf-8")


def render_frozen_statement(
    number: int,
    problem_url: str,
    latex_url: Optional[str],
    accessed: str,
    statement_text: Optional[str],
    latex_hash: Optional[str],
) -> str:
    hash_line = ""
    if latex_url and latex_hash:
        hash_line = f"- latex snapshot: {latex_url} (sha256: {latex_hash})\n"
    elif latex_url:
        hash_line = f"- latex snapshot: {latex_url} (sha256: unavailable)\n"
    else:
        hash_line = "- latex snapshot: unavailable\n"

    statement = statement_text or "TBD (fetch the statement from the source URL)."
    return textwrap.dedent(
        f"""\
        # Erdos Problem #{number} (frozen_v1)

        ## Source
        - {problem_url} (accessed {accessed})
        {hash_line.rstrip()}

        ## Definitions
        - None.

        ## Statement
        {statement}

        ## Edge cases
        - None.
        """
    )


def render_writeup(
    problem_url: str,
    forum_url: str,
    accessed: str,
    proof_link: Optional[str],
    statement_link: Optional[str],
    evidence_note: str,
) -> str:
    proof = proof_link or "none found"
    statement = statement_link or "none found"
    summary_lines = [f"- TODO (line {i})" for i in range(1, 11)]
    lines = [
        "# Writeup",
        "",
        "Summary (10-20 lines):",
        *summary_lines,
        "",
        "Sources:",
        f"- Problem page: {problem_url} (accessed {accessed})",
        f"- Forum thread: {forum_url}",
        f"- External Lean proof: {proof}",
        f"- External Lean statement: {statement}",
        "- Paper reference: NO VERIFICADO",
        "",
        "Evidence status:",
        f"- {evidence_note}",
    ]
    return "\n".join(lines) + "\n"


def render_primary_sources(
    problem_url: str,
    forum_url: str,
    accessed: str,
    cite_key: Optional[str],
    bib_entry: Optional[str],
    proof_link: Optional[str],
    statement_link: Optional[str],
) -> str:
    lines = [
        "# Primary Sources",
        "",
        f"- Problem page: {problem_url} (accessed {accessed}).",
        f"- Forum thread: {forum_url}.",
    ]
    if cite_key:
        lines.append(f"- Erdos Problems citation key: {cite_key}.")
    if bib_entry:
        lines.extend(["", "Bib entry (from erdosproblems):", f"> {bib_entry}"])
    if proof_link:
        lines.append(f"- External Lean proof: {proof_link}.")
    if statement_link:
        lines.append(f"- External Lean statement: {statement_link}.")
    lines.append("- Paper reference: NO VERIFICADO.")
    return "\n".join(lines) + "\n"


def render_mapping() -> str:
    return textwrap.dedent(
        """\
        # Literature Mapping

        - TODO: map primary sources to proof steps.
        """
    )


def render_blueprint() -> str:
    return textwrap.dedent(
        """\
        # Blueprint

        ## Goal theorem
        - See frozen statement.

        ## Lemmas (expected)
        1) TODO
        2) TODO
        3) TODO

        ## Notes
        - TODO
        """
    )


def render_forum_post(
    number: int,
    problem_url: str,
    forum_url: str,
    accessed: str,
    latex_url: Optional[str],
    latex_hash: Optional[str],
    statement_text: Optional[str],
    lean_file: Optional[str],
    lean_url: Optional[str],
    theorem_name: Optional[str],
    claim_state: str,
    commit_sha: Optional[str],
) -> str:
    statement = statement_text or "TBD (fill from frozen statement)."
    latex_line = "unavailable"
    if latex_url:
        latex_line = f"{latex_url} (sha256: {latex_hash or 'unavailable'})"
    lean_file_line = lean_file or "none"
    lean_source_line = lean_url or "none"
    theorem_line = theorem_name or "unknown"
    commit_line = commit_sha or "unknown"
    return textwrap.dedent(
        f"""\
        # Forum post draft: Erdos Problem #{number}

        Status:
        - claim.state: {claim_state}
        - repo commit: {commit_line}

        Sources:
        - problem page: {problem_url} (accessed {accessed})
        - forum thread: {forum_url}
        - latex snapshot: {latex_line}

        Statement (from frozen_v1):
        {statement}

        Evidence:
        - Lean file: {lean_file_line}
        - Lean source: {lean_source_line}
        - theorem: {theorem_line}
        - reproducible build: `bash tools/check.sh`
        - policy check: `python3 tools/policy/check_repo.py`

        Manual checklist before posting:
        - [ ] Statement matches frozen_v1 (compare hash if available).
        - [ ] Bibliography verified (replace NO VERIFICADO).
        - [ ] Lean proof corresponds to the frozen statement.
        - [ ] CI green for the PR.
        """
    )


def main() -> int:
    args = parse_args()
    root = Path(__file__).resolve().parent.parent
    try:
        problem_id, number = normalize_problem_id(args.problem)
    except ValueError as exc:
        print(f"ERROR: {exc}")
        return 2

    problem_url = args.problem_url or f"https://www.erdosproblems.com/{number}"
    latex_url = args.latex_url or f"https://www.erdosproblems.com/latex/{number}"
    forum_url = args.forum_url or f"https://www.erdosproblems.com/forum/thread/{number}"
    accessed = dt.date.today().isoformat()

    problem_dir = root / "problems" / problem_id
    if not problem_dir.exists() or not args.resume:
        run(
            [
                sys.executable,
                "tools/new_problem.py",
                problem_id,
                *( [args.title] if args.title else [] ),
            ],
            root,
        )

    if not args.keep_active:
        run([sys.executable, "tools/set_active.py", "--yes", problem_id], root)

    statement_dir = problem_dir / "statement"
    literature_dir = problem_dir / "literature"
    report_dir = problem_dir / "report"

    statement_raw_html = None
    statement_text = None
    lean_links: list[str] = []
    bib_entry = None
    cite_key = None
    latex_hash = None

    if not args.no_fetch:
        try:
            latex_bytes, latex_html = fetch_url(latex_url)
        except Exception as exc:
            print(f"ERROR: failed to fetch LaTeX URL: {latex_url}\n{exc}")
            return 1

        latex_hash = hashlib.sha256(latex_bytes).hexdigest()
        statement_raw_html, statement_text = extract_statement(latex_html)

        if statement_raw_html:
            (statement_dir / "latex_source.html").write_bytes(latex_bytes)
        else:
            print("ERROR: failed to locate statement in the LaTeX HTML snapshot.")
            return 1

        lean_links = extract_lean_links(latex_html)
        cite_key = find_cite_key(latex_html)

        if cite_key:
            bib_url = f"https://www.erdosproblems.com/bibs/{cite_key}"
            try:
                _, bib_html = fetch_url(bib_url)
                bib_entry = html.unescape(re.sub(r"<[^>]+>", "", bib_html)).strip()
            except Exception as exc:
                print(f"WARNING: failed to fetch bib entry {bib_url}: {exc}")

    proof_link, statement_link = pick_lean_links(lean_links, number)
    lean_url = args.lean_url or proof_link

    evidence_note = "pending (no local Lean proof yet)."
    theorem_name = args.theorem
    lean_imported = False

    if not args.no_lean and lean_url:
        lean_path = root / "ErdosLab" / "Problems" / f"{problem_id}.lean"
        if lean_path.exists() and not args.force:
            try:
                lean_text = lean_path.read_text(encoding="utf-8")
            except Exception as exc:
                print(f"ERROR: failed to read existing Lean file: {lean_path}\n{exc}")
                return 1
            lean_imported = True
        else:
            try:
                lean_bytes, lean_text = fetch_url(lean_url)
            except Exception as exc:
                print(f"ERROR: failed to fetch Lean file: {lean_url}\n{exc}")
                return 1
            lean_path.write_bytes(lean_bytes)
            lean_imported = True

        all_path = root / "ErdosLab" / "All.lean"
        import_line = f"import ErdosLab.Problems.{problem_id}"
        all_lines = all_path.read_text(encoding="utf-8").splitlines()
        if import_line not in all_lines:
            all_lines.append(import_line)
            write_text(all_path, "\n".join(all_lines))

        if theorem_name is None:
            theorem_name = find_theorem_name(lean_text, number)
        if args.theorem and theorem_name is None:
            print(f"ERROR: theorem {args.theorem!r} not found in {lean_url}")
            return 1

    write_text(
        statement_dir / "frozen_v1.md",
        render_frozen_statement(
            number,
            problem_url,
            latex_url if not args.no_fetch else None,
            accessed,
            statement_text,
            latex_hash,
        ),
    )

    evidence_note = (
        f"imported Lean file {lean_url} (theorem {theorem_name})"
        if lean_imported and theorem_name
        else evidence_note
    )

    write_text(
        report_dir / "writeup.md",
        render_writeup(
            problem_url,
            forum_url,
            accessed,
            proof_link,
            statement_link,
            evidence_note,
        ),
    )
    write_text(
        literature_dir / "primary_sources.md",
        render_primary_sources(
            problem_url,
            forum_url,
            accessed,
            cite_key,
            bib_entry,
            proof_link,
            statement_link,
        ),
    )
    write_text(literature_dir / "mapping.md", render_mapping())

    blueprint_path = problem_dir / "blueprint.md"
    if not blueprint_path.exists():
        write_text(blueprint_path, render_blueprint())

    prompt_text = literature_scout.render_chatgpt_prompt(
        problem_id=problem_id,
        problem_number=number,
        title=args.title,
        problem_url=problem_url,
        forum_url=forum_url,
        statement_text=statement_text,
    )
    literature_scout.write_chatgpt_files(literature_dir, prompt_text)

    try:
        literature_scout.run_literature_scout(
            problem_dir=problem_dir,
            problem_id=problem_id,
            problem_number=number,
            title=args.title,
            statement_text=statement_text,
            offline=args.no_fetch,
            cache_dir=root / "tools" / "literature_cache",
            log_path=root / "logs" / "literature_scout.log",
        )
    except Exception as exc:  # pylint: disable=broad-except
        print(f"WARNING: literature scout failed: {exc}")

    try:
        solver_scaffold.run_scaffold(
            problem_dir=problem_dir,
            problem_id=problem_id,
            problem_number=number,
            title=args.title,
            statement_text=statement_text,
            problem_url=problem_url,
            forum_url=forum_url,
        )
    except Exception as exc:  # pylint: disable=broad-except
        print(f"WARNING: solver scaffold failed: {exc}")

    if not args.skip_checks:
        run(["bash", "tools/check.sh"], root)

    if lean_imported and theorem_name:
        status_path = problem_dir / "status.json"
        data = json.loads(status_path.read_text(encoding="utf-8"))
        data["claim"]["state"] = "solved"
        data["evidence"] = [
            {
                "type": "lean",
                "file": f"ErdosLab/Problems/{problem_id}.lean",
                "theorem": theorem_name,
            }
        ]
        write_text(status_path, json.dumps(data, indent=2, sort_keys=False))
        if not args.skip_checks:
            run([sys.executable, "tools/policy/check_repo.py"], root)

    status_path = problem_dir / "status.json"
    status_data = json.loads(status_path.read_text(encoding="utf-8"))
    claim_state = status_data.get("claim", {}).get("state", "partial")

    if not args.no_forum:
        commit_sha = run_capture(["git", "rev-parse", "--short", "HEAD"], root)
        lean_file = (
            f"ErdosLab/Problems/{problem_id}.lean" if lean_imported else None
        )
        write_text(
            report_dir / "forum_post.md",
            render_forum_post(
                number,
                problem_url,
                forum_url,
                accessed,
                latex_url if not args.no_fetch else None,
                latex_hash,
                statement_text,
                lean_file,
                lean_url,
                theorem_name,
                claim_state,
                commit_sha,
            ),
        )

    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
