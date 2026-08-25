from __future__ import annotations

import math

import pandas as pd


SIMILAR_FEATURE_DEFINITIONS = {
    "SOX日次騰落率": ("SOX指数", "return"),
    "NASDAQ日次騰落率": ("NASDAQ総合指数", "return"),
    "VIX変化率": ("VIX指数", "return"),
    "米10年金利変化": ("UST 10Y", "change"),
    "USD/JPY変化率": ("USD/JPY", "return"),
}

SIMILAR_ASSET_DEFINITIONS = {
    "S&P 500": ("S&P 500指数", "return"),
    "NASDAQ": ("NASDAQ総合指数", "return"),
    "SOX": ("SOX指数", "return"),
    "USD/JPY": ("USD/JPY", "return"),
    "米10年金利": ("UST 10Y", "change_bp"),
}

FORWARD_HORIZONS = {1: "1営業日後", 5: "5営業日後", 20: "20営業日後"}


def build_point_in_time_features(
    numeric_features: pd.DataFrame,
    macro_history: pd.DataFrame | None = None,
    minimum_history: int = 252,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """各日までのデータだけで標準化し、距離計算用の特徴量を返す。"""
    numeric = numeric_features.sort_index().replace([float("inf"), float("-inf")], pd.NA)
    numeric = numeric.dropna()
    if numeric.empty:
        return pd.DataFrame(), pd.DataFrame()

    expanding = numeric.expanding(min_periods=minimum_history)
    means = expanding.mean()
    standard_deviations = expanding.std(ddof=0).replace(0, pd.NA)
    standardized = ((numeric - means) / standard_deviations).dropna()
    if standardized.empty:
        return pd.DataFrame(), pd.DataFrame()

    raw = numeric.reindex(standardized.index).copy()
    if macro_history is not None and not macro_history.empty:
        # 月末判定は翌月から利用可能とみなし、公表時点の完全再現ができないことに保守的に対処する。
        macro = macro_history.sort_index().copy()
        macro.index = pd.DatetimeIndex(macro.index) + pd.offsets.MonthEnd(1)
        combined_index = macro.index.union(standardized.index).sort_values()
        macro_daily = macro.reindex(combined_index).ffill().reindex(standardized.index)
        macro_daily = macro_daily.add_prefix("マクロ:")
        standardized = pd.concat([standardized, macro_daily], axis=1).dropna()
        raw = pd.concat([raw, macro_daily], axis=1).reindex(standardized.index)
    return standardized, raw


def find_similar_periods(
    point_in_time_features: pd.DataFrame,
    target_series: pd.Series,
    target_method: str,
    neighbor_count: int = 5,
    exclusion_sessions: int = 20,
    horizons: tuple[int, ...] = (1, 5, 20),
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """最新日と似た重複しない過去日、その後の実績、特徴量寄与を返す。"""
    if point_in_time_features.empty:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    if neighbor_count < 1 or exclusion_sessions < 0:
        raise ValueError("検索件数は1以上、近接除外期間は0以上にしてください。")

    features = point_in_time_features.sort_index().dropna()
    numerical_columns = [column for column in features if not column.startswith("マクロ:")]
    macro_columns = [column for column in features if column.startswith("マクロ:")]
    if not numerical_columns:
        raise ValueError("距離計算に使える数値特徴量がありません。")

    current = features.iloc[-1]
    numeric_contributions = features[numerical_columns].sub(current[numerical_columns]).pow(2)
    if macro_columns:
        macro_contributions = features[macro_columns].ne(current[macro_columns]).astype(float)
        contributions = pd.concat([numeric_contributions, macro_contributions], axis=1)
    else:
        contributions = numeric_contributions
    distances = contributions.sum(axis=1).pow(0.5) / math.sqrt(len(contributions.columns))

    outcomes = _forward_outcomes(target_series, target_method, horizons)
    outcome_on_feature_dates = outcomes.reindex(
        features.index, method="ffill", tolerance=pd.Timedelta(days=4)
    )
    maximum_horizon = max(horizons)
    reference_position = len(features) - 1
    eligible_dates = features.index[: max(0, reference_position - exclusion_sessions)]
    eligible_dates = eligible_dates.intersection(
        outcome_on_feature_dates.dropna(subset=[maximum_horizon]).index
    )
    ranked_dates = distances.reindex(eligible_dates).sort_values().index

    selected: list[pd.Timestamp] = []
    index_positions = {pd.Timestamp(day): position for position, day in enumerate(features.index)}
    for candidate in ranked_dates:
        candidate = pd.Timestamp(candidate)
        if all(
            abs(index_positions[candidate] - index_positions[chosen]) > exclusion_sessions
            for chosen in selected
        ):
            selected.append(candidate)
        if len(selected) == neighbor_count:
            break

    rows: list[dict[str, object]] = []
    contribution_rows: list[dict[str, object]] = []
    for candidate in selected:
        distance = float(distances.loc[candidate])
        row: dict[str, object] = {
            "類似局面の日付": candidate,
            "類似度": 100 / (1 + distance),
            "距離": distance,
        }
        for horizon in horizons:
            row[FORWARD_HORIZONS.get(horizon, f"{horizon}営業日後")] = float(
                outcome_on_feature_dates.loc[candidate, horizon]
            )
        rows.append(row)

        candidate_contributions = contributions.loc[candidate]
        contribution_total = float(candidate_contributions.sum())
        for feature_name, value in candidate_contributions.items():
            contribution_rows.append(
                {
                    "類似局面の日付": candidate,
                    "特徴量": feature_name,
                    "距離への寄与率": (
                        0.0
                        if contribution_total == 0
                        else float(value / contribution_total * 100)
                    ),
                }
            )

    matches = pd.DataFrame(rows)
    contribution_frame = pd.DataFrame(contribution_rows)
    summary_rows: list[dict[str, object]] = []
    for horizon in horizons:
        label = FORWARD_HORIZONS.get(horizon, f"{horizon}営業日後")
        sample = matches[label].dropna() if not matches.empty else pd.Series(dtype=float)
        summary_rows.append(
            {
                "期間": label,
                "平均": None if sample.empty else float(sample.mean()),
                "中央値": None if sample.empty else float(sample.median()),
                "上昇確率": None if sample.empty else float((sample > 0).mean() * 100),
                "サンプル数": len(sample),
                "単位": "bp" if target_method == "change_bp" else "%",
            }
        )
    return matches, pd.DataFrame(summary_rows), contribution_frame


def _forward_outcomes(
    series: pd.Series, method: str, horizons: tuple[int, ...]
) -> pd.DataFrame:
    clean = series.dropna().sort_index().copy()
    clean.index = pd.DatetimeIndex(clean.index).tz_localize(None).normalize()
    outcomes: dict[int, pd.Series] = {}
    for horizon in horizons:
        future = clean.shift(-horizon)
        if method == "return":
            outcomes[horizon] = (future / clean - 1) * 100
        elif method == "change_bp":
            outcomes[horizon] = (future - clean) * 100
        else:
            raise ValueError(f"未対応の将来変化計算です: {method}")
    return pd.DataFrame(outcomes)
