from __future__ import annotations

import json
from collections.abc import Iterable


def load_watchlists(raw_value: object, valid_indicators: Iterable[str]) -> dict[str, list[str]]:
    """ブラウザ保存値を検証し、利用可能なウォッチリストだけを返す。"""
    if isinstance(raw_value, str):
        try:
            raw_value = json.loads(raw_value)
        except (TypeError, ValueError):
            return {}
    if not isinstance(raw_value, dict):
        return {}

    valid_names = set(valid_indicators)
    watchlists: dict[str, list[str]] = {}
    for raw_name, raw_indicators in raw_value.items():
        if not isinstance(raw_name, str) or not isinstance(raw_indicators, list):
            continue
        name = raw_name.strip()[:40]
        if not name:
            continue
        indicators = list(
            dict.fromkeys(
                indicator
                for indicator in raw_indicators
                if isinstance(indicator, str) and indicator in valid_names
            )
        )
        if indicators:
            watchlists[name] = indicators
    return watchlists


def dump_watchlists(watchlists: dict[str, list[str]]) -> str:
    """日本語を保ったJSONとしてブラウザ保存用の文字列へ変換する。"""
    return json.dumps(watchlists, ensure_ascii=False, separators=(",", ":"))
