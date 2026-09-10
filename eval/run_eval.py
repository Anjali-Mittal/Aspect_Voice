"""
Aspect-extraction accuracy eval.

Runs the SAME prompt template and JSON-parsing path as
app/pipeline/aspect_extraction.py (imported directly, not copy-pasted, so
this can't silently drift from production) against a small hand-labeled
set, and reports feature/sentiment/severity accuracy.

WHY THIS EXISTS: aspect_extraction currently has zero ground-truth
measurement — sentiment/severity/feature are pure LLM judgment with no
check against known-correct answers anywhere in the pipeline. This is the
first version of that check.

IMPORTANT — READ BEFORE TRUSTING THE NUMBERS THIS PRINTS:
eval_set.csv (36 rows) was drafted by Claude as a starting scaffold, NOT
verified by a human against real customer feedback. Before citing eval
results anywhere client-facing:
  1. A person should read every row in eval_set.csv and confirm the
     expected_feature / expected_sentiment / expected_severity_band
     columns are actually correct.
  2. Expand past 36 rows — real reviews are messier than hand-written
     examples (typos, code-switching, sarcasm). Pull 30-50 more from
     actual scraped clean_feedback and label those by hand.
  3. Re-run after any prompt change in aspect_extraction.py to catch
     regressions.

Usage:
    python eval/run_eval.py
Writes eval/eval_results.json with full per-row detail for manual review.
"""
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.llm.client import call_llm_json
from app.pipeline.aspect_extraction import PROMPT_TEMPLATE, FEATURE_MATCH_THRESHOLD
from rapidfuzz import process, fuzz

EVAL_DIR = Path(__file__).resolve().parent
BATCH_SIZE = 10


def severity_band(sev: float) -> str:
    if sev is None:
        return "none"
    if sev <= 0.33:
        return "low"
    if sev <= 0.66:
        return "medium"
    return "high"


def load_fixture():
    fixture = json.loads((EVAL_DIR / "ontology_fixture.json").read_text())
    return fixture["product_name"], fixture["features"]


def load_eval_rows():
    with open(EVAL_DIR / "eval_set.csv", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def run_extraction(texts: list[str], product_name: str, features: list[dict]) -> dict[int, list[dict]]:
    """Returns {text_index: [mentions]} using the production prompt/parse path."""
    feature_list = "\n".join(f"- {f['name']}: {f['description']}" for f in features)
    known_names = [f["name"] for f in features]

    out: dict[int, list[dict]] = defaultdict(list)
    for i in range(0, len(texts), BATCH_SIZE):
        batch = texts[i:i + BATCH_SIZE]
        snippets = "\n".join(f"{j}. {t[:500]}" for j, t in enumerate(batch))
        prompt = PROMPT_TEMPLATE.format(
            product_name=product_name, feature_list=feature_list, n=len(batch), snippets=snippets
        )
        result = call_llm_json(prompt)
        for r in result.get("results", []):
            idx = r.get("i")
            if idx is None or idx >= len(batch):
                continue
            global_idx = i + idx
            for m in r.get("mentions", []):
                if not isinstance(m, dict) or "feature" not in m:
                    continue
                match = process.extractOne(m["feature"], known_names, scorer=fuzz.WRatio) if known_names else None
                canonical = match[0] if match and match[1] >= FEATURE_MATCH_THRESHOLD else None
                out[global_idx].append({
                    "raw_feature": m["feature"],
                    "canonical_feature": canonical,  # None = rejected, same rule as production
                    "sentiment": m.get("sentiment", "neutral"),
                    "severity": float(m.get("severity", 0)),
                })
    return out


def grade(rows: list[dict], extracted: dict[int, list[dict]], text_to_indices: dict[str, list[int]]) -> dict:
    per_row = []
    feature_hits, feature_total = 0, 0
    sentiment_hits, sentiment_total = 0, 0
    severity_hits, severity_total = 0, 0
    abstain_hits, abstain_total = 0, 0

    for row in rows:
        text_idx = text_to_indices[row["text"]][0] if len(text_to_indices[row["text"]]) == 1 else None
        # multiple eval rows can share one text (multi-feature snippets) — search all indices for that text
        indices = text_to_indices[row["text"]]
        mentions = [m for idx in indices for m in extracted.get(idx, [])]

        expected_feature = row["expected_feature"].strip()
        result_row = {"id": row["id"], "text": row["text"], "expected": dict(row), "extracted_mentions": mentions}

        if expected_feature == "":
            abstain_total += 1
            passed = len(mentions) == 0
            abstain_hits += passed
            result_row["abstain_correct"] = passed
        else:
            feature_total += 1
            found = next((m for m in mentions if m["canonical_feature"] == expected_feature), None)
            result_row["feature_found"] = found is not None
            if found:
                feature_hits += 1
                sentiment_total += 1
                sent_ok = found["sentiment"] == row["expected_sentiment"]
                sentiment_hits += sent_ok
                result_row["sentiment_correct"] = sent_ok
                if row["expected_sentiment"] == "negative":
                    severity_total += 1
                    band_ok = severity_band(found["severity"]) == row["expected_severity_band"]
                    severity_hits += band_ok
                    result_row["severity_band_correct"] = band_ok

        per_row.append(result_row)

    def pct(hits, total):
        return round(100 * hits / total, 1) if total else None

    summary = {
        "feature_recall_pct": pct(feature_hits, feature_total),
        "feature_recall_n": feature_total,
        "sentiment_accuracy_pct": pct(sentiment_hits, sentiment_total),
        "sentiment_accuracy_n": sentiment_total,
        "severity_band_accuracy_pct": pct(severity_hits, severity_total),
        "severity_band_accuracy_n": severity_total,
        "correct_abstain_pct": pct(abstain_hits, abstain_total),
        "correct_abstain_n": abstain_total,
    }
    return {"summary": summary, "per_row": per_row}


def main():
    product_name, features = load_fixture()
    rows = load_eval_rows()

    text_to_indices = defaultdict(list)
    unique_texts = []
    for row in rows:
        if row["text"] not in text_to_indices:
            text_to_indices[row["text"]].append(len(unique_texts))
            unique_texts.append(row["text"])
        else:
            text_to_indices[row["text"]].append(text_to_indices[row["text"]][0])

    print(f"Running extraction on {len(unique_texts)} unique texts ({len(rows)} eval rows)...")
    extracted = run_extraction(unique_texts, product_name, features)

    results = grade(rows, extracted, text_to_indices)

    print("\n=== EVAL SUMMARY ===")
    for k, v in results["summary"].items():
        print(f"  {k}: {v}")

    out_path = EVAL_DIR / "eval_results.json"
    out_path.write_text(json.dumps(results, indent=2))
    print(f"\nFull per-row detail written to {out_path}")
    print("\nReminder: eval_set.csv labels are an unverified Claude-drafted scaffold.")
    print("Read eval/run_eval.py module docstring before citing these numbers anywhere client-facing.")


if __name__ == "__main__":
    main()
