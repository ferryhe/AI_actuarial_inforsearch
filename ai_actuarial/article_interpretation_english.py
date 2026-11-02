"""Bounded, evidence-preserving English translations of saved Chinese articles."""

from __future__ import annotations

import hashlib
import inspect
import json
import re
import time
import uuid
from collections import Counter
from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from ai_actuarial import article_interpretations as articles
from ai_actuarial.ai_runtime import resolve_ai_function_runtime
from ai_actuarial.article_interpretations import (
    ArticleRequestCleanupError,
    ChatArticleGenerator,
    _call_article_with_deadline,
    _current,
    _identity,
    _load_file,
    _now,
)
from ai_actuarial.chatbot.exceptions import LLMAuthenticationError, LLMTimeoutError
from ai_actuarial.postgres import PostgresConnection

MAX_CALLS = 2
MAX_PROVIDER_SECONDS = 180.0
MAX_CONTENT_SECONDS = 240.0
MAX_CALL_SECONDS = 90.0
MAX_DAILY_ITEMS = 3
MAX_DAILY_CALLS = 6
MAX_DAILY_PROVIDER_SECONDS = 900.0
MAX_INPUT_CHARS = 32_000
MAX_OUTPUT_TOKENS = 6_000
PROMPT_VERSION = "article-interpretation-english-v1"
ROLES = articles.SECTION_ROLES

PROMPT = """Translate this saved, evidence-validated Chinese article interpretation into clear English.
Use only the supplied saved Chinese title, ordered section headings and ordered claims, and their
same cited source evidence. Preserve every claim, its order, facts, figures, units, precision,
dates, model names, formulas, quoted source wording, caveats and uncertainty. Translate the text;
do not add explanations or remove claims. Do not make new claims from background knowledge.
Return only compact JSON with exactly this shape:
{"title_en":"...","sections":[{"role":"intro","heading_en":"...","paragraphs":["..."]}]}
Include each supplied section exactly once in order, with the same role and paragraph count.
Do not add metadata fields such as authors, publication dates, source names, or URLs; references, citation markers, and claim-kind labels are supplied by code. Dates and facts within the supplied claims remain claim text and must be translated faithfully.
"""


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _source_sections(draft: dict) -> list[dict]:
    claims = draft.get("claims")
    body = str(draft.get("body_markdown_zh") or "").split("\n## 原文出处与阅读", 1)[0]
    headings = re.findall(r"(?m)^## ([^\r\n]+)$", body)
    if not isinstance(claims, list) or not claims or len(headings) != len(ROLES):
        raise ValueError("saved_chinese_structure_unavailable")

    ordered_roles = []
    for claim in claims:
        role = claim.get("section_role") if isinstance(claim, dict) else None
        if role not in ROLES:
            raise ValueError("saved_chinese_claim_invalid")
        if not ordered_roles or ordered_roles[-1] != role:
            ordered_roles.append(role)
    if ordered_roles != list(ROLES):
        raise ValueError("saved_chinese_section_order_invalid")

    coverage = draft.get("coverage") or {}
    evidence = coverage.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        raise ValueError("saved_source_evidence_unavailable")
    evidence_by_id = {item.get("id"): item for item in evidence if isinstance(item, dict)}

    result = []
    claim_index = 0
    for role, heading in zip(ROLES, headings, strict=True):
        section_claims = []
        while claim_index < len(claims) and claims[claim_index]["section_role"] == role:
            claim = claims[claim_index]
            ids = claim.get("evidence_ids")
            if (
                not isinstance(claim.get("text"), str)
                or claim.get("kind") not in {"source", "inference", "example"}
                or not isinstance(ids, list)
                or not ids
                or any(identity not in evidence_by_id for identity in ids)
            ):
                raise ValueError("saved_claim_evidence_unavailable")
            section_claims.append(
                {
                    "text": claim["text"],
                    "kind": claim["kind"],
                    "evidence": [
                        {
                            "id": identity,
                            "quote": evidence_by_id[identity].get("quote", ""),
                            "section": evidence_by_id[identity].get("section", ""),
                        }
                        for identity in ids
                    ],
                }
            )
            claim_index += 1
        if not section_claims:
            raise ValueError("saved_chinese_section_empty")
        result.append({"role": role, "heading_zh": heading, "claims": section_claims})
    if claim_index != len(claims):
        raise ValueError("saved_chinese_claim_order_invalid")
    return result


def _material(draft: dict) -> dict:
    return {
        "title_zh": draft.get("title_zh", ""),
        "sections": _source_sections(draft),
    }


def _quote_values(text: str) -> list[str]:
    return [
        next(value for value in match if value)
        for match in re.findall(
            r'“([^”]+)”|"([^"\n]+)"|「([^」]+)」|『([^』]+)』|‘([^’]+)’|\$([^$]+)\$',
            text,
        )
    ]


_MONTH_NUMBERS = {
    month.casefold(): index
    for index, month in enumerate(
        "January February March April May June July August September October November December".split(),
        1,
    )
}
_MONTH_PATTERN = "|".join(_MONTH_NUMBERS)
_EXPLICIT_DATES = (
    re.compile(r"(?<!\d)(?P<year>\d{4})年(?P<month>\d{1,2})月(?:\s*(?P<day>\d{1,2})日)?"),
    re.compile(
        rf"\b(?P<month>{_MONTH_PATTERN})\s+(?:(?P<day>\d{{1,2}}),?\s+)?(?P<year>\d{{4}})\b|"
        rf"\b(?P<day_before>\d{{1,2}})\s+(?P<month_before>{_MONTH_PATTERN})\s+(?P<year_before>\d{{4}})\b",
        re.I,
    ),
    re.compile(r"(?<!\d)(?P<year>\d{4})-(?P<month>\d{2})(?:-(?P<day>\d{2}))?(?!\d)"),
)


def _date_events(text: str):
    matches = []
    for pattern in _EXPLICIT_DATES:
        for match in pattern.finditer(text):
            groups = match.groupdict()
            month_name = groups.get("month") or groups.get("month_before")
            month = (
                int(month_name)
                if month_name and month_name.isdigit()
                else _MONTH_NUMBERS[month_name.casefold()]
            )
            year = int(groups.get("year") or groups.get("year_before"))
            day_text = groups.get("day") or groups.get("day_before")
            day = int(day_text) if day_text else None
            try:
                date(year, month, day or 1)
            except ValueError:
                continue
            matches.append((match.start(), match.end(), year, month, day))
    matches.sort()
    return matches


def _quantity_events(text: str, *, english: bool = False):
    occurrences = []
    articles._quantities(text, strict=True, occurrences=occurrences)
    dates = _date_events(text)
    one_hot_spans = {
        (match.start(), match.start() + len(match.group("one")))
        for match in re.finditer(
            r"(?P<one>one)(?:[-‐‑‒–—]|\s+)hot\s+(?:encodings?|encoded|vectors?)\b",
            text,
            flags=re.IGNORECASE,
        )
    }
    ordinal_occurrences = [
        (start, end, value, exponent)
        for start, end, dimension, value, exponent in occurrences
        if dimension.startswith("ordinal:")
    ]
    events = []
    for start, end, dimension, value, exponent in occurrences:
        if dimension == "number" and (start, end) in one_hot_spans:
            continue
        if (
            english
            and dimension == "number"
            and any(
                ordinal_start == start
                and end <= ordinal_end
                and value == ordinal_value
                and exponent == ordinal_exponent
                for ordinal_start, ordinal_end, ordinal_value, ordinal_exponent in ordinal_occurrences
            )
        ):
            continue
        events.append((start, end, (dimension, value, exponent)))
    for start, end, year, month, day in dates:
        events = [event for event in events if not (start <= event[0] and event[1] <= end)]
        year_value, month_value = Decimal(year), Decimal(month)
        signature = (
            "calendar_date",
            (year_value, year_value.as_tuple().exponent),
            (month_value, month_value.as_tuple().exponent),
            None if day is None else (Decimal(day), Decimal(day).as_tuple().exponent),
        )
        events.append((start, end, signature))
    return [signature for _, _, signature in sorted(events, key=lambda item: (item[0], item[1]))]


def _check_quantities(label: str, original: str, translated: str, evidence_ids=()) -> None:
    expected = _quantity_events(original)
    actual = _quantity_events(translated, english=True)
    if Counter(actual) != Counter(expected) or actual != expected:
        raise ValueError(
            f"{label}_number_mismatch expected={list(map(str, expected))} "
            f"actual={list(map(str, actual))} evidence={list(evidence_ids)}"
        )


def _reject_model_evidence_marker(label: str, text: str) -> None:
    if re.search(r"\[e\d+\]", text, flags=re.IGNORECASE):
        raise ValueError(f"{label}_unexpected_evidence_marker")


def _outer_attempt_count(receipt: dict) -> int:
    return int(receipt.get("outer_attempts", receipt.get("provider_calls", 0)) or 0)


def _reserve_english_receipt_attempt(receipt: dict, route: dict, timeout: float) -> None:
    receipt["outer_attempts"] = _outer_attempt_count(receipt) + 1
    receipt.update(route)
    if route.get("backend") == "codex-cli":
        receipt["provider_calls"] = None
        receipt["internal_provider_requests"] = "unknown/unmetered"
    else:
        receipt["provider_calls"] = int(receipt.get("provider_calls") or 0) + 1
    receipt["provider_seconds"] += timeout


def validate_english_output(raw: str, source: dict) -> dict:
    if not isinstance(raw, str) or len(raw) > 40_000:
        raise ValueError("invalid_english_output_size")
    try:
        value = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        raise ValueError("invalid_english_json") from None
    if not isinstance(value, dict) or set(value) != {"title_en", "sections"}:
        raise ValueError("invalid_english_object")

    title = value.get("title_en")
    if not isinstance(title, str) or not title.strip() or len(title) > 240:
        raise ValueError("invalid_english_title")
    _reject_model_evidence_marker("english_title", title)
    _check_quantities("english_title", str(source.get("title_zh") or ""), title)

    expected_sections = source["sections"]
    output_sections = value.get("sections")
    if not isinstance(output_sections, list) or len(output_sections) != len(expected_sections):
        raise ValueError("english_section_count_mismatch")

    translated_sections = []
    for section_index, (expected, actual) in enumerate(
        zip(expected_sections, output_sections, strict=True), start=1
    ):
        if not isinstance(actual, dict) or set(actual) != {"role", "heading_en", "paragraphs"}:
            raise ValueError(f"english_section_{section_index}_invalid")
        if actual.get("role") != expected["role"]:
            raise ValueError(f"english_section_{section_index}_order_mismatch")
        heading = actual.get("heading_en")
        if not isinstance(heading, str) or not heading.strip() or len(heading) > 240:
            raise ValueError(f"english_heading_{section_index}_invalid")
        _reject_model_evidence_marker(f"english_heading_{section_index}", heading)
        _check_quantities(f"english_heading_{section_index}", expected["heading_zh"], heading)

        paragraphs = actual.get("paragraphs")
        if not isinstance(paragraphs, list) or len(paragraphs) != len(expected["claims"]):
            raise ValueError(f"english_section_{section_index}_paragraph_count_mismatch")
        translated_paragraphs = []
        for claim_index, (claim, text) in enumerate(
            zip(expected["claims"], paragraphs, strict=True), start=1
        ):
            label = f"english_claim_{section_index}_{claim_index}"
            if not isinstance(text, str) or not text.strip() or len(text) > 6_000:
                raise ValueError(f"{label}_invalid")
            _reject_model_evidence_marker(label, text)
            evidence_ids = [item.get("id") for item in claim["evidence"]]
            _check_quantities(label, claim["text"], text, evidence_ids)
            support = "\n".join(
                articles._prose(str(item.get("quote") or ""))
                + "\n"
                + str(item.get("section") or "")
                for item in claim["evidence"]
            )
            if any(formula not in text for formula in re.findall(r"\$[^$]+\$", claim["text"])):
                raise ValueError(f"{label}_formula_missing")
            if any(
                token in text for token in ("=", "\\", "∑", "∫", "≈", "≤", "≥")
            ) and not re.search(r"\$[^$]+\$", text):
                raise ValueError(f"{label}_formula_mismatch")
            source_quotes = Counter(_quote_values(claim["text"]))
            translated_quotes = Counter(_quote_values(text))
            if any(
                translated_quotes[quote] != count for quote, count in source_quotes.items()
            ) or any(quote not in support for quote in translated_quotes.elements()):
                raise ValueError(f"{label}_quote_mismatch")
            translated_paragraphs.append(text.strip())
        translated_sections.append(
            {
                "role": expected["role"],
                "heading_en": heading.strip(),
                "paragraphs": translated_paragraphs,
            }
        )
    return {"title_en": title.strip(), "sections": translated_sections}


def render_english_body(sections: list[dict], claims: list[dict]) -> str:
    lines = []
    claim_index = 0
    for section in sections:
        lines.append("## " + section["heading_en"])
        for text in section["paragraphs"]:
            claim = claims[claim_index]
            claim_index += 1
            if claim["kind"] == "inference":
                text = "Interpretation: " + text
            elif claim["kind"] == "example":
                text = "Illustrative example: " + text
            text += " " + " ".join(f"[{identity}]" for identity in claim["evidence_ids"])
            lines.append(text)
    if claim_index != len(claims):
        raise ValueError("english_claim_render_mismatch")
    return "\n\n".join(lines)


class EnglishTranslationService:
    """Translate only current ready Chinese rows under their separate English budget."""

    def __init__(
        self, storage, *, generator=None, now=_now, clock=time.monotonic, stop_check=lambda: False
    ):
        self.storage = storage
        self.connection = storage._conn
        if generator is not None and not inspect.iscoroutinefunction(
            getattr(generator, "generate", None)
        ):
            raise TypeError("article_generator_requires_cancellable_async_generate")
        self.generator = generator
        self.now = now
        self.clock = clock
        self.stop_check = stop_check
        self.connection.execute("SET statement_timeout = '3000ms'")
        self.connection.execute("SET lock_timeout = '3000ms'")

    def _get(self, interpretation_id):
        row = self.connection.execute(
            "SELECT payload_json FROM article_interpretations WHERE interpretation_id=?",
            (interpretation_id,),
        ).fetchone()
        return dict(row[0]) if row else None

    def _save_translation(self, draft, state):
        self.connection.execute(
            "UPDATE article_interpretations SET payload_json=jsonb_set(payload_json,'{english_translation}',?::jsonb,true),updated_at=CURRENT_TIMESTAMP WHERE interpretation_id=?",
            (_json(state), draft["interpretation_id"]),
        )
        draft["english_translation"] = state

    def _content_totals(self, content_key):
        rows = self.connection.execute(
            "SELECT payload_json FROM article_interpretations WHERE content_key=?",
            (content_key,),
        ).fetchall()
        states = [dict(row[0]).get("english_translation") or {} for row in rows]
        calls = [
            call
            for state in states
            for attempt in state.get("attempts", [])
            for call in attempt.get("calls", [])
        ]
        starts = [state["started_at"] for state in states if state.get("started_at")]
        return {
            "calls": len(calls),
            "provider_cleanup": any(
                call.get("error") == "provider_cleanup" or call.get("status") == "cleanup_failed"
                for call in calls
            ),
            "provider_seconds": sum(
                float(
                    call.get("charged_provider_seconds", call.get("reserved_provider_seconds", 0))
                )
                for call in calls
            ),
            "started_at": min(starts) if starts else None,
        }

    def _build_messages(self, material, draft):
        messages = [
            {"role": "system", "content": PROMPT},
            {"role": "user", "content": _json(material)},
        ]
        chars = sum(len(message["content"]) for message in messages)
        input_bytes = sum(len(message["content"].encode("utf-8")) + 16 for message in messages)
        context_tokens = int(
            (draft.get("coverage") or {}).get("context_tokens")
            or MAX_INPUT_CHARS + MAX_OUTPUT_TOKENS + 16
        )
        if chars > MAX_INPUT_CHARS or input_bytes + MAX_OUTPUT_TOKENS > context_tokens:
            raise ValueError("english_translation_input_too_large")
        return messages, context_tokens

    def _content_calls_exhausted_reason(self) -> str:
        runtime = getattr(getattr(self, "generator", None), "runtime", None)
        return (
            "content_outer_attempts_exhausted"
            if getattr(runtime, "backend", None) == "codex-cli"
            else "content_provider_calls_exhausted"
        )

    def _call_budget(self, draft, receipt, daily_started):
        content = self._content_totals(draft["content_key"])
        if content["calls"] >= MAX_CALLS:
            return 0.0, self._content_calls_exhausted_reason()
        if content["provider_seconds"] >= MAX_PROVIDER_SECONDS:
            return 0.0, "content_provider_seconds_exhausted"
        content_age = 0.0
        if content["started_at"]:
            content_age = max(
                0.0,
                (self.now() - datetime.fromisoformat(content["started_at"])).total_seconds(),
            )
            if content_age >= MAX_CONTENT_SECONDS:
                return 0.0, "content_wall_budget_exhausted"
        if _outer_attempt_count(receipt) >= MAX_DAILY_CALLS:
            return 0.0, "daily_outer_attempts_exhausted"
        if receipt["provider_seconds"] >= MAX_DAILY_PROVIDER_SECONDS:
            return 0.0, "daily_provider_seconds_exhausted"
        daily_age = max(0.0, self.clock() - daily_started)
        if daily_age >= MAX_DAILY_PROVIDER_SECONDS:
            return 0.0, "daily_wall_budget_exhausted"
        remaining = min(
            MAX_CALL_SECONDS,
            MAX_PROVIDER_SECONDS - content["provider_seconds"],
            MAX_DAILY_PROVIDER_SECONDS - receipt["provider_seconds"],
            MAX_CONTENT_SECONDS - content_age,
            MAX_DAILY_PROVIDER_SECONDS - daily_age,
        )
        return remaining, "" if remaining > 0 else "provider_budget_exhausted"

    def _save_receipt(self, receipt):
        self.connection.execute(
            "UPDATE article_interpretation_rounds SET receipt_json=?::jsonb WHERE round_key=?",
            (_json(receipt), receipt["round_key"]),
        )

    def _generator(self):
        if self.generator is not None:
            runtime = getattr(self.generator, "runtime", None)
            return (
                self.generator,
                (
                    articles._runtime_route(runtime)
                    if runtime is not None
                    else {"provider": "injected", "model": "injected"}
                ),
            )
        runtime = resolve_ai_function_runtime("chatbot", storage=self.storage)
        if not runtime.configured:
            raise LLMAuthenticationError("Chat credential unavailable")
        return (
            ChatArticleGenerator(
                runtime,
                MAX_OUTPUT_TOKENS,
            ),
            articles._runtime_route(runtime),
        )

    def _translate(self, draft, receipt, slot, daily_started):
        current = self._get(draft["interpretation_id"])
        if (
            not current
            or current.get("status") != "ready"
            or not _current(self.connection, current)
        ):
            slot.update(status="skipped", reason="chinese_interpretation_not_current_ready")
            return
        draft = current
        state = dict(draft.get("english_translation") or {})
        if state.get("status") == "ready":
            slot.update(status="ready", reason="english_translation_already_ready")
            return
        for old_attempt in state.get("attempts", []):
            if old_attempt.get("status") != "running":
                continue
            reserved = [
                call for call in old_attempt.get("calls", []) if call.get("status") == "reserved"
            ]
            for call in reserved:
                call["status"] = "interrupted"
                call["error"] = "interrupted"
            if reserved:
                old_attempt["status"] = "interrupted"
                state.update(status="failed", error="interrupted")
                self._save_translation(draft, state)
        totals = self._content_totals(draft["content_key"])
        if totals["provider_cleanup"] or state.get("error") == "provider_cleanup":
            state.update(status="failed", error="provider_cleanup")
            self._save_translation(draft, state)
            slot.update(status="failed", reason="provider_cleanup")
            return
        try:
            material = _material(draft)
            messages, context_tokens = self._build_messages(material, draft)
            generator, route = self._generator()
        except (ValueError, LLMAuthenticationError) as exc:
            reason = "authentication" if isinstance(exc, LLMAuthenticationError) else str(exc)[:120]
            state.update(status="failed", error=reason, prompt_version=PROMPT_VERSION)
            self._save_translation(draft, state)
            slot.update(status="failed", reason=reason)
            return

        route_fields = {
            key: route[key]
            for key in (
                "backend",
                "requested_backend",
                "effective_backend",
                "requested_model",
                "effective_model",
                "reasoning_effort",
                "requested_reasoning_effort",
                "effective_reasoning_effort",
            )
            if key in route
        }
        route_fields.update(
            {"internal_provider_requests": "unknown/unmetered"}
            if route.get("backend") == "codex-cli"
            else {}
        )
        saved_route = state.get("route")
        current_route = {
            key: route.get(key)
            for key in (
                "provider",
                "model",
                "credential_id",
                "base_url",
                "backend",
                "requested_backend",
                "effective_backend",
                "requested_model",
                "effective_model",
                "reasoning_effort",
                "requested_reasoning_effort",
                "effective_reasoning_effort",
            )
            if key in route
        }
        if state.get("attempts") and saved_route != current_route:
            state.update(status="failed", error="english_translation_route_changed")
            self._save_translation(draft, state)
            slot.update(status="failed", reason=state["error"])
            return
        fingerprint = _sha(
            _json(
                {
                    "content_key": draft["content_key"],
                    "input_fingerprint": draft.get("input_fingerprint"),
                    "material": material,
                    "prompt_version": PROMPT_VERSION,
                    "language": "en",
                }
            )
        )
        if state.get("input_fingerprint") and state["input_fingerprint"] != fingerprint:
            state.update(status="failed", error="english_translation_recipe_changed")
            self._save_translation(draft, state)
            slot.update(status="failed", reason=state["error"])
            return
        state.setdefault("attempts", [])
        state.setdefault("started_at", self.now().isoformat())
        state.update(
            status="running",
            prompt_version=PROMPT_VERSION,
            input_fingerprint=fingerprint,
            provider=route["provider"],
            model=route["model"],
            route=current_route,
            **route_fields,
        )
        attempt = (
            state["attempts"][-1]
            if state["attempts"] and state["attempts"][-1].get("status") == "running"
            else None
        )
        if attempt is None:
            attempt = {
                "attempt_id": str(uuid.uuid4()),
                "status": "running",
                "calls": [],
                "started_at": self.now().isoformat(),
            }
            state["attempts"].append(attempt)

        while self._content_totals(draft["content_key"])["calls"] < MAX_CALLS:
            current = self._get(draft["interpretation_id"])
            if (
                not current
                or current.get("status") != "ready"
                or not _current(self.connection, current)
            ):
                state.update(status="failed", error="source_version_no_longer_current")
                attempt["status"] = "failed"
                self._save_translation(draft, state)
                slot.update(status="skipped", reason="source_version_no_longer_current")
                return
            if self.stop_check():
                state["status"] = "queued"
                self._save_translation(draft, state)
                slot.update(status="queued", reason="stopped")
                return
            timeout, reason = self._call_budget(draft, receipt, daily_started)
            if timeout <= 0:
                state.update(status="failed", error=reason)
                attempt["status"] = "failed"
                self._save_translation(draft, state)
                slot.update(status="failed", reason=reason)
                return

            correction = state.get("last_validation_error")
            request_messages = messages
            if correction:
                feedback = (
                    "Return the complete corrected English JSON from the saved Chinese material. "
                    "Fix this validation issue: " + str(correction)[:180]
                )
                added_bytes = len(feedback.encode("utf-8")) + 16
                base_bytes = sum(
                    len(message["content"].encode("utf-8")) + 16 for message in messages
                )
                if (
                    sum(len(message["content"]) for message in messages) + len(feedback)
                    <= MAX_INPUT_CHARS
                    and base_bytes + added_bytes + MAX_OUTPUT_TOKENS <= context_tokens
                ):
                    request_messages = [*messages, {"role": "user", "content": feedback}]
                else:
                    state.update(status="failed", error="english_correction_feedback_does_not_fit")
                    attempt["status"] = "failed"
                    self._save_translation(draft, state)
                    slot.update(status="failed", reason=state["error"])
                    return

            deadline = time.monotonic() + timeout
            call = {
                "status": "reserved",
                "outer_attempts": 1,
                "reserved_provider_seconds": timeout,
                "started_at": self.now().isoformat(),
                "correction": bool(correction),
                **route_fields,
            }
            attempt["calls"].append(call)
            with self.storage.transaction():
                self._save_translation(draft, state)
                _reserve_english_receipt_attempt(receipt, route_fields, timeout)
                self._save_receipt(receipt)

            call_started = self.clock()
            error = None
            try:
                raw = _call_article_with_deadline(generator, request_messages, deadline)
                elapsed = max(0.0, self.clock() - call_started)
                if elapsed > timeout:
                    raise TimeoutError("english_provider_deadline")
                translated = validate_english_output(raw, material)
                body = render_english_body(translated["sections"], draft["claims"])
                if not _current(self.connection, draft):
                    raise ValueError("source_version_no_longer_current")
                state.update(
                    status="ready",
                    title_en=translated["title_en"],
                    body_markdown_en=body,
                    sections_en=translated["sections"],
                    generated_at=self.now().isoformat(),
                    error="",
                )
                state.pop("last_validation_error", None)
                call["status"] = "valid"
                attempt["status"] = "ready"
                slot.update(status="ready", reason="translation_and_evidence_valid")
            except (LLMAuthenticationError, ArticleRequestCleanupError) as exc:
                error = exc
                call["status"] = (
                    "authentication"
                    if isinstance(exc, LLMAuthenticationError)
                    else "cleanup_failed"
                )
                call["error"] = (
                    "authentication"
                    if isinstance(exc, LLMAuthenticationError)
                    else "provider_cleanup"
                )
                state.update(status="failed", error=call["error"])
                attempt["status"] = "failed"
                slot.update(status="failed", reason=call["error"])
            except articles.ArticleStreamInterrupted as exc:
                error = exc
                call["status"] = "interrupted"
                call["error"] = "interrupted"
                state.update(status="failed", error="interrupted")
                attempt["status"] = "interrupted"
                slot.update(status="failed", reason="interrupted")
            except Exception as exc:  # noqa: BLE001
                error = exc
                call["status"] = "failed"
                if isinstance(exc, ValueError) and str(exc) == "source_version_no_longer_current":
                    call["error"] = "source_version_no_longer_current"
                    state.update(status="failed", error=call["error"])
                    attempt["status"] = "failed"
                    slot.update(status="skipped", reason=call["error"])
                    return
                if isinstance(exc, ValueError):
                    call["validation_error"] = str(exc)[:180]
                    state["last_validation_error"] = str(exc)[:180]
                    call["error"] = "validation"
                else:
                    call["error"] = type(exc).__name__
                state.update(status="failed", error=call["error"])
                attempt["status"] = "failed"
                slot.update(status="failed", reason=call["error"])
            finally:
                elapsed = max(0.0, self.clock() - call_started)
                timed_out = isinstance(error, (TimeoutError, LLMTimeoutError))
                cleanup_failed = isinstance(error, ArticleRequestCleanupError)
                charge = (
                    max(timeout, elapsed)
                    if timed_out or cleanup_failed or call["status"] in {"reserved", "interrupted"}
                    else elapsed
                )
                call["elapsed_seconds"] = elapsed
                call["charged_provider_seconds"] = charge
                attempt["provider_seconds"] = float(attempt.get("provider_seconds", 0)) + charge
                receipt["provider_seconds"] += charge - timeout
                with self.storage.transaction():
                    self._save_translation(draft, state)
                    self._save_receipt(receipt)

            if state.get("status") == "ready":
                return
            if isinstance(
                error,
                (LLMAuthenticationError, ArticleRequestCleanupError, TimeoutError, LLMTimeoutError),
            ):
                return
            if not isinstance(error, ValueError):
                return

        state.update(
            status="failed",
            error=state.get("error") or self._content_calls_exhausted_reason(),
        )
        self._save_translation(draft, state)
        slot.update(status="failed", reason=state["error"])

    def run(self, *, interpretation_ids=(), file_urls=()):
        acquired = self.connection.execute(
            "SELECT pg_try_advisory_lock(hashtextextended(current_schema() || ':article_interpretation',0))"
        ).fetchone()[0]
        if not acquired:
            return {"status": "busy", "receipt_type": "english_translation", "slots": []}
        try:
            now = self.now()
            round_key = (
                "english_translation:"
                + now.astimezone(ZoneInfo("Asia/Shanghai")).date().isoformat()
            )
            saved = self.connection.execute(
                "SELECT receipt_json FROM article_interpretation_rounds WHERE round_key=?",
                (round_key,),
            ).fetchone()
            if saved:
                receipt = dict(saved[0])
                # Older rows under this prefix must still be visibly separate from Chinese runs.
                receipt["receipt_type"] = "english_translation"
                if receipt.get("status") == "provider_cleanup":
                    return receipt
            else:
                receipt = {
                    "round_key": round_key,
                    "receipt_type": "english_translation",
                    "status": "running",
                    "started_at": now.isoformat(),
                    "provider_calls": 0,
                    "outer_attempts": 0,
                    "provider_seconds": 0.0,
                    "elapsed_seconds": 0.0,
                    "slots": [],
                }
                self.connection.execute(
                    "INSERT INTO article_interpretation_rounds(round_key,receipt_json) VALUES (?,?::jsonb)",
                    (round_key, _json(receipt)),
                )

            candidates = []
            for identity in interpretation_ids:
                draft = self._get(identity)
                if draft:
                    candidates.append(draft)
            for file_url in file_urls:
                if not isinstance(file_url, str) or not file_url.strip():
                    continue
                rows = self.connection.execute(
                    "SELECT payload_json FROM article_interpretations WHERE file_url=? AND status='ready' "
                    "ORDER BY created_at DESC",
                    (file_url.strip(),),
                ).fetchall()
                candidates.extend(dict(row[0]) for row in rows)

            unique = []
            seen = set()
            for draft in candidates:
                if draft.get("status") != "ready" or not _current(self.connection, draft):
                    continue
                key = draft.get("content_key") or draft.get("interpretation_id")
                if key not in seen:
                    seen.add(key)
                    unique.append(draft)

            run_started = self.clock()
            daily_started_at = datetime.fromisoformat(receipt["started_at"])
            daily_age = max(0.0, (now - daily_started_at).total_seconds())
            daily_started = run_started - daily_age
            receipt["status"] = "running"
            self._save_receipt(receipt)
            for draft in unique:
                if self.stop_check():
                    receipt["status"] = "stopped"
                    break
                content_key = draft.get("content_key") or draft["interpretation_id"]
                slot = next(
                    (item for item in receipt["slots"] if item.get("content_key") == content_key),
                    None,
                )
                if slot is None:
                    if len(receipt["slots"]) >= MAX_DAILY_ITEMS:
                        continue
                    slot = {
                        "content_key": content_key,
                        "interpretation_id": draft["interpretation_id"],
                        "file_url": draft["file_url"],
                        "status": "queued",
                        "reason": "",
                    }
                    receipt["slots"].append(slot)
                    self._save_receipt(receipt)
                if slot.get("status") in {"ready", "skipped"}:
                    continue
                if (
                    _outer_attempt_count(receipt) >= MAX_DAILY_CALLS
                    or receipt["provider_seconds"] >= MAX_DAILY_PROVIDER_SECONDS
                ):
                    receipt["status"] = "budget_exhausted"
                    break
                self._translate(draft, receipt, slot, daily_started)
                self._save_receipt(receipt)
                if slot.get("reason") in {"authentication", "provider_cleanup", "interrupted"}:
                    receipt["status"] = slot["reason"]
                    break
            else:
                receipt["status"] = "complete"
            receipt["elapsed_seconds"] = max(
                float(receipt.get("elapsed_seconds", 0)), self.clock() - run_started
            )
            self._save_receipt(receipt)
            return receipt
        finally:
            self.connection.execute(
                "SELECT pg_advisory_unlock(hashtextextended(current_schema() || ':article_interpretation',0))"
            )


def read_english_interpretations(database, *, file_url="") -> list[dict]:
    connection = PostgresConnection(database, read_only=True)
    try:
        connection.execute("SET statement_timeout = '3000ms'")
        rows = connection.execute(
            "SELECT payload_json FROM article_interpretations WHERE (?='' OR file_url=?) "
            "AND status='ready' ORDER BY created_at DESC LIMIT 100",
            (file_url, file_url),
        ).fetchall()
        result = []
        for row in rows:
            draft = dict(row[0])
            translation = draft.get("english_translation") or {}
            if translation.get("status") != "ready" or not _current(connection, draft):
                continue
            source = articles._canonical_source(connection, draft["source_key"])
            saved_references = draft.get("references") or {}
            references = {
                key: saved_references[key]
                for key in (
                    "original_url",
                    "original_title",
                    "published_time",
                    "china_article_url",
                    "author",
                    "authors",
                )
                if key in saved_references
            }
            references["source"] = (
                {key: source[key] for key in ("name_zh", "name_en") if key in source}
                if source
                else {}
            )
            result.append(
                {
                    "interpretation_id": draft["interpretation_id"],
                    "title_en": translation["title_en"],
                    "body_markdown_en": translation["body_markdown_en"],
                    "generated_at": translation["generated_at"],
                    "file_url": draft["file_url"],
                    "raw_sha256": draft["raw_sha256"],
                    "markdown_sha256": draft["markdown_sha256"],
                    "china_article_url": draft["china_article_url"],
                    "references": references,
                }
            )
        latest = {}
        for item in result:
            latest.setdefault(item["file_url"], item)
        return list(latest.values())
    finally:
        connection.close()


def read_current_article_identity(database, file_url: str) -> dict | None:
    connection = PostgresConnection(database, read_only=True)
    try:
        connection.execute("SET statement_timeout = '3000ms'")
        row = _load_file(connection, file_url)
        if not row or not articles._visible(row):
            return None
        identity = _identity(row)
        return identity if identity["file_url"] == file_url else None
    finally:
        connection.close()
