from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import pandas as pd


BIGTECH_CAPEX_DATA_PATH = Path(__file__).resolve().parent / "data" / "bigtech_capex_research.json"
ALLOWED_COMPANIES = ("Microsoft", "Alphabet", "Meta")
ALLOWED_PUBLISHED_PRECISIONS = {"date", "datetime"}
ALLOWED_GUIDANCE_KINDS = {"range", "approx", "qualitative", "unavailable"}
ALLOWED_COMPARISON_STATUSES = {"exact", "caveat", "definition_changed", "not_comparable"}
ALLOWED_CHANGE_LABELS = {
    "initial", "raised", "lowered", "lower_bound_raised", "upper_bound_raised",
    "range_narrowed", "unchanged", "definition_changed", "not_comparable",
}
ALLOWED_ECONOMIC_PLAN_CHANGES = {"raised", "lowered", "unchanged", "unknown"}
ALLOWED_SOURCE_TYPES = {"IR", "SEC", "official_transcript"}
CHANGE_LABELS_JA = {
    "initial": "初回",
    "raised": "増額",
    "lowered": "減額",
    "lower_bound_raised": "下限引き上げ",
    "upper_bound_raised": "上限引き上げ",
    "range_narrowed": "レンジ縮小",
    "unchanged": "据え置き",
    "definition_changed": "定義変更",
    "not_comparable": "比較不可",
}
COMPARISON_STATUS_LABELS_JA = {
    "exact": "比較可能",
    "caveat": "比較注意",
    "definition_changed": "定義変更",
    "not_comparable": "比較不可",
}
ECONOMIC_PLAN_LABELS_JA = {
    "raised": "増額",
    "lowered": "減額",
    "unchanged": "据え置き",
    "unknown": "不明",
}

BIGTECH_RESEARCH_CONTEXT = {
    "Microsoft": {
        "next_check": "reported CapEx定義とeconomic planの関係、finance / operating lease分類を再確認。",
        "demand_check": "台湾・韓国の実需がcapacity expansionと整合するか確認。",
    },
    "Alphabet": {
        "next_check": "CY2026 guidanceとAI compute / server / DC / network capacityの追加継続を確認。",
        "demand_check": "capacity delivery加速後にTaiwan Orders / Korea Exportsが追随するか確認。",
    },
    "Meta": {
        "next_check": "CY2026 rangeとfinance lease principal込み定義の維持、AI / DC投資継続を確認。",
        "demand_check": "台湾・韓国の実需が追随するか確認。",
    },
}


class BigTechCapexDataError(ValueError):
    """Raised when the manual point-in-time research dataset is unsafe to display."""


def load_bigtech_capex_research(path: str | Path | None = None) -> dict[str, Any]:
    data_path = Path(path) if path is not None else BIGTECH_CAPEX_DATA_PATH
    try:
        payload = json.loads(data_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise BigTechCapexDataError(f"Big Tech CapEx datasetを読み込めません: {error}") from error
    return validate_bigtech_capex_research(payload)


def validate_bigtech_capex_research(payload: object) -> dict[str, Any]:
    if not isinstance(payload, dict) or not isinstance(payload.get("records"), list):
        raise BigTechCapexDataError("datasetはrecords配列を持つJSON objectである必要があります。")
    updated_at = pd.to_datetime(payload.get("dataset_updated_at"), errors="coerce")
    if pd.isna(updated_at):
        raise BigTechCapexDataError("dataset_updated_atが不正です。")

    records: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    required = {
        "company", "disclosure_label", "published_at", "published_precision",
        "target_year", "actual_capex_bn", "guidance_kind", "guidance_low_bn",
        "guidance_high_bn", "guidance_approx_bn", "comparison_status",
        "change_label", "economic_plan_change", "capex_definition",
        "lease_treatment", "official_use_summary", "source_url", "source_type",
    }
    for index, raw in enumerate(payload["records"]):
        if not isinstance(raw, dict) or not required.issubset(raw):
            missing = sorted(required.difference(raw if isinstance(raw, dict) else {}))
            raise BigTechCapexDataError(f"record {index}の必須fieldが不足しています: {missing}")
        record = dict(raw)
        company = record["company"]
        if company not in ALLOWED_COMPANIES:
            raise BigTechCapexDataError(f"対象外companyです: {company}")
        key = (company, str(record["disclosure_label"]))
        if key in seen:
            raise BigTechCapexDataError(f"duplicate disclosureです: {key}")
        seen.add(key)
        if not str(record["target_year"]).strip():
            raise BigTechCapexDataError(f"{key}: target_yearが空です。")
        published_at = pd.to_datetime(record["published_at"], errors="coerce", utc=True)
        if pd.isna(published_at):
            raise BigTechCapexDataError(f"{key}: published_atが不正です。")
        if record["published_precision"] not in ALLOWED_PUBLISHED_PRECISIONS:
            raise BigTechCapexDataError(f"{key}: published_precisionが不正です。")
        if record["guidance_kind"] not in ALLOWED_GUIDANCE_KINDS:
            raise BigTechCapexDataError(f"{key}: guidance_kindが不正です。")
        if record["comparison_status"] not in ALLOWED_COMPARISON_STATUSES:
            raise BigTechCapexDataError(f"{key}: comparison_statusが不正です。")
        if record["change_label"] not in ALLOWED_CHANGE_LABELS:
            raise BigTechCapexDataError(f"{key}: change_labelが不正です。")
        if record["economic_plan_change"] not in ALLOWED_ECONOMIC_PLAN_CHANGES:
            raise BigTechCapexDataError(f"{key}: economic_plan_changeが不正です。")
        if record["source_type"] not in ALLOWED_SOURCE_TYPES:
            raise BigTechCapexDataError(f"{key}: source_typeが不正です。")
        if record["comparison_status"] == "definition_changed" and record["change_label"] != "definition_changed":
            raise BigTechCapexDataError(f"{key}: definition_changedはchange_labelでも優先する必要があります。")
        if record["comparison_status"] == "not_comparable" and record["change_label"] != "not_comparable":
            raise BigTechCapexDataError(f"{key}: not_comparableのchange_labelが不整合です。")
        _validate_guidance(record, key)
        parsed_url = urlparse(str(record["source_url"]))
        if parsed_url.scheme != "https" or not parsed_url.netloc:
            raise BigTechCapexDataError(f"{key}: source_urlは公式HTTPS URLが必要です。")
        record["published_at"] = published_at
        records.append(record)

    if set(record["company"] for record in records) != set(ALLOWED_COMPANIES):
        raise BigTechCapexDataError("datasetには対象3社すべてが必要です。")
    records.sort(key=lambda item: (ALLOWED_COMPANIES.index(item["company"]), item["published_at"]))
    return {
        "dataset_updated_at": updated_at.normalize(),
        "update_method": payload.get("update_method"),
        "records": records,
    }


def _validate_guidance(record: dict[str, Any], key: tuple[str, str]) -> None:
    kind = record["guidance_kind"]
    low, high, approx = (record["guidance_low_bn"], record["guidance_high_bn"], record["guidance_approx_bn"])
    if kind == "range":
        if low is None or high is None or float(low) > float(high):
            raise BigTechCapexDataError(f"{key}: range guidanceはlow <= highが必要です。")
        if approx is not None:
            raise BigTechCapexDataError(f"{key}: range guidanceにapprox値は設定できません。")
    elif kind == "approx":
        if approx is None:
            raise BigTechCapexDataError(f"{key}: approx guidanceにはguidance_approx_bnが必要です。")
        if low is not None or high is not None:
            raise BigTechCapexDataError(f"{key}: approx guidanceにrange値は設定できません。")
    elif any(value is not None for value in (low, high, approx)):
        raise BigTechCapexDataError(f"{key}: {kind} guidanceに数値は設定できません。")


def effective_change_label(current: dict[str, Any], previous: dict[str, Any] | None) -> str:
    if previous is None or previous["target_year"] != current["target_year"]:
        return "initial"
    if current["comparison_status"] == "definition_changed":
        return "definition_changed"
    if current["comparison_status"] == "not_comparable":
        return "not_comparable"
    return str(current["change_label"])


def format_guidance(record: dict[str, Any] | None) -> str:
    if record is None:
        return "—"
    if record["guidance_kind"] == "range":
        return f"{float(record['guidance_low_bn']):g}–{float(record['guidance_high_bn']):g} bn USD"
    if record["guidance_kind"] == "approx":
        return f"約{float(record['guidance_approx_bn']):g} bn USD"
    if record["guidance_kind"] == "qualitative":
        return "定性説明のみ"
    return "利用不可"


def build_bigtech_capex_summaries(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for company in ALLOWED_COMPANIES:
        history = sorted(
            (record for record in records if record["company"] == company),
            key=lambda item: item["published_at"],
        )
        if not history:
            continue
        current = history[-1]
        previous = next(
            (record for record in reversed(history[:-1]) if record["target_year"] == current["target_year"]),
            None,
        )
        change = effective_change_label(current, previous)
        summaries.append({
            "company": company,
            "target_year": current["target_year"],
            "previous_guidance": format_guidance(previous),
            "current_guidance": format_guidance(current),
            "change_label": change,
            "change_label_ja": CHANGE_LABELS_JA[change],
            "comparison_status": current["comparison_status"],
            "comparison_status_ja": COMPARISON_STATUS_LABELS_JA[current["comparison_status"]],
            "economic_plan_change": current["economic_plan_change"],
            "economic_plan_change_ja": ECONOMIC_PLAN_LABELS_JA[current["economic_plan_change"]],
            "published_at": current["published_at"],
            "official_use_summary": current["official_use_summary"],
            "comparison_note": current.get("comparison_note", ""),
            "history": history,
            "context": BIGTECH_RESEARCH_CONTEXT[company],
        })
    return summaries
