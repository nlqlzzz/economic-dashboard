from __future__ import annotations

import pandas as pd

from validation_timing import condition_onsets, evaluate_release_return, exclusion_summary


RETURN_HORIZONS = {1: "1か月後", 3: "3か月後", 6: "6か月後"}


def calculate_market_momentum(prices: pd.Series) -> dict[str, object]:
    clean = _clean_prices(prices)
    if clean.empty:
        return {"state": "Unavailable", "direction": 0, "returns": {}}
    latest_date = clean.index[-1]
    returns: dict[int, float | None] = {}
    for months in (1, 3, 6):
        prior = clean.loc[clean.index <= latest_date - pd.DateOffset(months=months)]
        returns[months] = None if prior.empty or prior.iloc[-1] == 0 else float((clean.iloc[-1] / prior.iloc[-1] - 1) * 100)
    primary = returns[3]
    if primary is None:
        primary = returns[1]
    if primary is None:
        state, direction = "Unavailable", 0
    elif primary > 0:
        state, direction = "Rising", 1
    elif primary < 0:
        state, direction = "Falling", -1
    else:
        state, direction = "Flat", 0
    return {"state": state, "direction": direction, "returns": returns, "as_of": latest_date}


def classify_price_vs_fundamentals(
    market: dict[str, object], global_pulse: dict[str, object]
) -> dict[str, object]:
    market_direction = int(market.get("direction", 0))
    pulse_state = str(global_pulse.get("state", "Unavailable"))
    if market.get("state") == "Unavailable":
        return _comparison_result("Unavailable", "市場価格データがありません。", market, global_pulse)
    if pulse_state == "Unavailable":
        return _comparison_result("Unavailable", "実需データのcoverageが不足しています。", market, global_pulse)
    fundamentals_direction = 1 if pulse_state in {"Strong", "Improving"} else -1 if pulse_state == "Weakening" else 0
    if market_direction > 0 and fundamentals_direction > 0:
        label, message = "Aligned Positive", "株価と半導体実需がともに改善しています。"
    elif market_direction > 0 and fundamentals_direction < 0:
        label, message = "Expectation-led / Divergence", "株価上昇に対して、実需モメンタムが追随していません。期待先行の可能性があります。"
    elif market_direction < 0 and fundamentals_direction > 0:
        label, message = "Fundamentals stronger than market", "実需が堅調な一方、市場価格は弱含んでいます。"
    elif market_direction < 0 and fundamentals_direction < 0:
        label, message = "Aligned Negative", "株価と実需がともに弱含んでいます。"
    else:
        label, message = "Mixed", "市場価格または実需の方向が明確でなく、シグナルが混在しています。"
    return _comparison_result(label, message, market, global_pulse)


def build_overseas_validation_signals(
    frame: pd.DataFrame,
    strict: bool = True,
    approximate_lag_months: int = 2,
) -> pd.DataFrame:
    """海外月次系列を、公表日または明示した暫定利用可能日で横持ちにする。"""
    if frame.empty:
        return pd.DataFrame()
    selected = frame[
        ~frame["is_derived"].fillna(False)
        & ~frame["is_partial_period"].fillna(False)
    ].copy()
    selected["yoy"] = pd.to_numeric(selected["yoy"], errors="coerce")
    selected = selected.dropna(subset=["yoy", "reference_period"])
    if strict:
        selected = selected.dropna(subset=["release_date"])
        selected["available_at"] = pd.to_datetime(selected["release_date"])
        method = "official_release_date"
    else:
        selected["available_at"] = pd.to_datetime(selected["release_date"])
        missing = selected["available_at"].isna()
        selected.loc[missing, "available_at"] = (
            pd.to_datetime(selected.loc[missing, "reference_period"]).dt.to_period("M")
            + approximate_lag_months
        ).dt.to_timestamp()
        method = "official_or_approximate"
    if selected.empty:
        return pd.DataFrame()
    pivot = selected.pivot_table(index="available_at", columns="series_id", values="yoy", aggfunc="last").sort_index()
    pivot.attrs["validation_mode"] = "release_date_confirmed" if strict else "provisional"
    pivot.attrs["publication_time_status"] = "unknown"
    pivot.attrs["revision_history_status"] = "not_verified"
    pivot.attrs["availability_method"] = method
    return pivot


def add_global_condition_signals(
    signals: pd.DataFrame,
    japan_signals: pd.DataFrame | None = None,
) -> pd.DataFrame:
    result = signals.copy().sort_index()
    taiwan_columns = [column for column in result if str(column).startswith("taiwan_")]
    korea_columns = [column for column in result if str(column).startswith("korea_")]
    if taiwan_columns:
        taiwan = result[taiwan_columns].mean(axis=1, skipna=True).where(result[taiwan_columns].notna().any(axis=1))
        result["Taiwan Improving"] = asof_improving(taiwan)
        result["Taiwan YoY Positive"] = taiwan.ffill().gt(0).where(taiwan.ffill().notna()).astype("boolean")
        result["Taiwan Last Release"] = _last_valid_release(taiwan)
        result["Taiwan Stale"] = _stale_release(result.index, result["Taiwan Last Release"])
    if korea_columns:
        korea = result[korea_columns].mean(axis=1, skipna=True).where(result[korea_columns].notna().any(axis=1))
        result["Korea Improving"] = asof_improving(korea)
        result["Korea YoY Positive"] = korea.ffill().gt(0).where(korea.ffill().notna()).astype("boolean")
        result["Korea YoY Above 20"] = korea.ffill().gt(20).where(korea.ffill().notna()).astype("boolean")
        result["Korea Last Release"] = _last_valid_release(korea)
        result["Korea Stale"] = _stale_release(result.index, result["Korea Last Release"])
    if "Taiwan Improving" in result and "Korea Improving" in result:
        result["Taiwan AND Korea Improving"] = result["Taiwan Improving"] & result["Korea Improving"]
        stale = result["Taiwan Stale"] | result["Korea Stale"]
        result["Taiwan AND Korea Improving"] = result["Taiwan AND Korea Improving"].mask(stale, pd.NA)
    if japan_signals is not None and not japan_signals.empty:
        japan = japan_signals.copy().sort_index().reindex(result.index, method="ffill")
        japan_improving = japan.mean(axis=1) > 0
        result["Japan Improving"] = japan_improving.astype("boolean")
        if "Taiwan AND Korea Improving" in result:
            result["Taiwan AND Korea AND Japan Improving"] = result["Taiwan AND Korea Improving"] & result["Japan Improving"]
    return result


def analyze_release_aware_returns(
    condition: pd.Series,
    asset_prices: pd.Series,
    horizons: tuple[int, ...] = (1, 3, 6),
    *,
    mode: str = "post_release",
    as_of: object | None = None,
) -> pd.DataFrame:
    """公表後評価または公表前後の価格反応を、満了サンプルだけで集計する。"""
    selected_dates = condition_onsets(condition)
    rows: list[dict[str, object]] = []
    for horizon in horizons:
        returns: list[float] = []
        statuses: list[str] = []
        excluded_prices = 0
        for available_at in selected_dates:
            observation = evaluate_release_return(asset_prices, available_at, horizon, mode=mode, as_of=as_of)
            statuses.append(observation.status)
            excluded_prices = max(excluded_prices, observation.excluded_observations)
            if observation.value is not None: returns.append(observation.value)
        sample = pd.Series(returns, dtype=float)
        count = len(sample)
        rows.append(
            {
                "期間": RETURN_HORIZONS.get(horizon, f"{horizon}か月後"),
                "平均": None if sample.empty else float(sample.mean()),
                "中央値": None if sample.empty else float(sample.median()),
                "上昇確率": None if sample.empty else float((sample > 0).mean() * 100),
                "25%点": None if sample.empty else float(sample.quantile(0.25)),
                "75%点": None if sample.empty else float(sample.quantile(0.75)),
                "最悪値": None if sample.empty else float(sample.min()),
                "最良値": None if sample.empty else float(sample.max()),
                "サンプル数": count,
                "除外": exclusion_summary(statuses),
                "価格品質": f"一時的不連続 {excluded_prices}観測除外" if excluded_prices else "確認済み",
                "評価方法": "公表後評価" if mode == "post_release" else "公表前後の価格反応",
                "注意": sample_warning(count),
            }
        )
    return pd.DataFrame(rows)


def analyze_release_aware_correlation(
    signal: pd.Series,
    asset_prices: pd.Series,
    horizons: tuple[int, ...] = (1, 3, 6),
    *,
    mode: str = "post_release",
    as_of: object | None = None,
) -> pd.DataFrame:
    """実際の利用可能日以降の市場リターンとの相関を集計する。"""
    clean_signal = pd.to_numeric(signal, errors="coerce").dropna().sort_index()
    rows: list[dict[str, object]] = []
    for horizon in horizons:
        pairs: list[tuple[float, float]] = []
        statuses: list[str] = []
        excluded_prices = 0
        for available_at, value in clean_signal.items():
            observation = evaluate_release_return(asset_prices, available_at, horizon, mode=mode, as_of=as_of)
            statuses.append(observation.status)
            excluded_prices = max(excluded_prices, observation.excluded_observations)
            if observation.value is not None: pairs.append((float(value), observation.value))
        sample = pd.DataFrame(pairs, columns=["signal", "return"])
        count = len(sample)
        rows.append(
            {
                "期間": RETURN_HORIZONS.get(horizon, f"{horizon}か月後"),
                "相関": None if count < 2 else float(sample.corr().iloc[0, 1]),
                "サンプル数": count,
                "除外": exclusion_summary(statuses),
                "価格品質": f"一時的不連続 {excluded_prices}観測除外" if excluded_prices else "確認済み",
                "評価方法": "公表後評価" if mode == "post_release" else "公表前後の価格反応",
                "注意": sample_warning(count),
            }
        )
    return pd.DataFrame(rows)


def sample_warning(count: int) -> str:
    if count < 5:
        return "標本数が非常に少ないため解釈に注意"
    if count < 10:
        return "標本数が少なく参考値"
    return ""


def _comparison_result(label: str, message: str, market: dict[str, object], pulse: dict[str, object]) -> dict[str, object]:
    return {"state": label, "message": message, "market": market, "fundamentals": pulse}


def _clean_prices(series: pd.Series) -> pd.Series:
    clean = pd.to_numeric(series, errors="coerce").dropna().sort_index().copy()
    clean.index = pd.DatetimeIndex(clean.index).tz_localize(None).normalize()
    return clean[~clean.index.duplicated(keep="last")]


def asof_improving(series: pd.Series) -> pd.Series:
    """Compare only consecutive valid releases, then carry that known state forward."""
    valid = pd.to_numeric(series, errors="coerce").dropna()
    at_release = valid.diff().gt(0).astype("boolean")
    if not at_release.empty:
        at_release.iloc[0] = pd.NA
    return at_release.reindex(series.index).ffill().astype("boolean")


def _last_valid_release(series: pd.Series) -> pd.Series:
    releases = pd.Series(pd.NaT, index=series.index, dtype="datetime64[ns]")
    releases.loc[series.notna()] = pd.DatetimeIndex(series.index[series.notna()])
    return releases.ffill()


def _stale_release(index: pd.Index, last_release: pd.Series, maximum_age_days: int = 62) -> pd.Series:
    current = pd.Series(pd.DatetimeIndex(index), index=index)
    age = current - pd.to_datetime(last_release)
    return age.gt(pd.Timedelta(days=maximum_age_days)).where(last_release.notna(), pd.NA).astype("boolean")
