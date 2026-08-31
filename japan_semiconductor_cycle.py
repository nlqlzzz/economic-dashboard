from __future__ import annotations

import pandas as pd


IIP_DISPLAY_ORDER = ("在庫率", "出荷", "生産", "在庫")
INVENTORY_CYCLE_PHASES = {
    (True, False): "需給改善方向",
    (True, True): "需要拡大・在庫積み増し",
    (False, True): "需要減速・在庫過剰リスク",
    (False, False): "減産・在庫調整",
}
BACKTEST_HORIZONS = {0: "同月末", 1: "1か月後", 2: "2か月後", 3: "3か月後", 6: "6か月後"}
CONDITIONAL_HORIZONS = {1: "1か月後", 3: "3か月後", 6: "6か月後"}


def summarize_semiconductor_iip(frame: pd.DataFrame) -> dict[str, object]:
    """電デバ4指数の現在値、変化率、3か月平均と複合的な局面説明を返す。"""
    rows: list[dict[str, object]] = []
    unavailable: list[str] = []
    for indicator_name in IIP_DISPLAY_ORDER:
        seasonal_column = f"{indicator_name}_季節調整済"
        original_column = f"{indicator_name}_原指数"
        if seasonal_column not in frame or original_column not in frame:
            unavailable.append(f"{indicator_name}: 必要な系列がありません")
            continue
        seasonal = _clean_series(frame[seasonal_column])
        original = _clean_series(frame[original_column])
        if seasonal.empty or original.empty:
            unavailable.append(f"{indicator_name}: 有効な観測値がありません")
            continue

        latest_date = seasonal.index[-1]
        latest_value = float(seasonal.iloc[-1])
        previous_change = (
            None
            if len(seasonal) < 2 or seasonal.iloc[-2] == 0
            else float((latest_value / seasonal.iloc[-2] - 1) * 100)
        )
        original_as_of = original.loc[:latest_date]
        year_ago_date = latest_date - pd.DateOffset(months=12)
        year_change = (
            None
            if (
                latest_date not in original_as_of.index
                or year_ago_date not in original_as_of.index
                or original_as_of.loc[year_ago_date] == 0
            )
            else float(
                (
                    original_as_of.loc[latest_date]
                    / original_as_of.loc[year_ago_date]
                    - 1
                )
                * 100
            )
        )
        rows.append(
            {
                "指標": indicator_name,
                "最新値": latest_value,
                "前月比": previous_change,
                "前年同月比": year_change,
                "3か月移動平均": (
                    None if len(seasonal) < 3 else float(seasonal.tail(3).mean())
                ),
                "対象年月": latest_date,
                "観測数": len(seasonal),
            }
        )

    summary = pd.DataFrame(rows)
    return {
        "summary": summary,
        "assessment": _cycle_assessment(summary),
        "unavailable": unavailable,
    }


def semiconductor_iip_trends(
    frame: pd.DataFrame, months: int = 36
) -> pd.DataFrame:
    """表示用に季節調整済4指数を直近指定月数へ絞る。"""
    columns = [f"{name}_季節調整済" for name in IIP_DISPLAY_ORDER]
    available = [column for column in columns if column in frame]
    if not available:
        return pd.DataFrame()
    trends = frame[available].copy().dropna(how="all").tail(months)
    return trends.rename(columns=lambda name: name.removesuffix("_季節調整済"))


def build_inventory_cycle_map(
    frame: pd.DataFrame, months: int = 24
) -> pd.DataFrame:
    """出荷・在庫の原指数前年比による在庫循環の軌跡を返す。"""
    required = ("出荷_原指数", "在庫_原指数")
    if months < 1 or any(column not in frame for column in required):
        return pd.DataFrame()

    shipment = _clean_series(frame[required[0]])
    inventory = _clean_series(frame[required[1]])
    common_dates = shipment.index.intersection(inventory.index).sort_values()
    rows: list[dict[str, object]] = []
    for target_date in common_dates:
        year_ago_date = target_date - pd.DateOffset(months=12)
        if (
            year_ago_date not in shipment.index
            or year_ago_date not in inventory.index
            or shipment.loc[year_ago_date] == 0
            or inventory.loc[year_ago_date] == 0
        ):
            continue
        shipment_yoy = float(
            (shipment.loc[target_date] / shipment.loc[year_ago_date] - 1) * 100
        )
        inventory_yoy = float(
            (inventory.loc[target_date] / inventory.loc[year_ago_date] - 1) * 100
        )
        rows.append(
            {
                "対象年月": target_date,
                "出荷前年比": shipment_yoy,
                "在庫前年比": inventory_yoy,
                "局面候補": classify_inventory_cycle(shipment_yoy, inventory_yoy),
            }
        )
    return pd.DataFrame(rows).tail(months).reset_index(drop=True)


def classify_inventory_cycle(shipment_yoy: float, inventory_yoy: float) -> str:
    """出荷・在庫前年比の符号から説明用の局面候補を返す。"""
    return INVENTORY_CYCLE_PHASES[(shipment_yoy >= 0, inventory_yoy >= 0)]


def summarize_electronic_computer_orders(series: pd.Series) -> dict[str, object]:
    """電子計算機等受注の単月値と平滑化したトレンド指標を返す。"""
    orders = _clean_series(series)
    if orders.empty:
        return {}
    latest_date = orders.index[-1]
    latest_value = float(orders.iloc[-1])
    three_month_average = orders.rolling(3, min_periods=3).mean()
    latest_three_month_average = three_month_average.iloc[-1]
    year_ago_date = latest_date - pd.DateOffset(months=12)
    three_month_year_ago_date = year_ago_date
    six_month_ago_date = latest_date - pd.DateOffset(months=6)

    return {
        "最新値": latest_value,
        "前月比": _exact_change(orders, latest_date, latest_date - pd.DateOffset(months=1)),
        "前年同月比": _exact_change(orders, latest_date, year_ago_date),
        "3か月移動平均": (
            None if pd.isna(latest_three_month_average) else float(latest_three_month_average)
        ),
        "3か月移動平均前年比": _exact_change(
            three_month_average, latest_date, three_month_year_ago_date
        ),
        "6か月モメンタム": _exact_change(
            three_month_average, latest_date, six_month_ago_date
        ),
        "対象年月": latest_date,
        "観測数": len(orders),
    }


def electronic_computer_order_trends(
    series: pd.Series, months: int = 36
) -> pd.DataFrame:
    """表示用に単月受注と3か月移動平均を直近指定月数へ絞る。"""
    orders = _clean_series(series)
    if months < 1 or orders.empty:
        return pd.DataFrame()
    return pd.DataFrame(
        {
            "単月受注": orders,
            "3か月移動平均": orders.rolling(3, min_periods=3).mean(),
        }
    ).tail(months)


def conservative_release_dates(
    target_dates: pd.DatetimeIndex, lag_months: int = 2
) -> pd.DatetimeIndex:
    """履歴公表日がない系列へ、ルックアヘッドを避ける保守的な利用可能日を付ける。"""
    if lag_months < 1:
        raise ValueError("公表ラグは1か月以上にしてください。")
    months = pd.DatetimeIndex(target_dates).to_period("M")
    return (months + lag_months).to_timestamp(how="start")


def build_semiconductor_backtest_signals(
    iip_frame: pd.DataFrame,
    machinery_orders: pd.Series | None = None,
    release_lag_months: int = 2,
) -> pd.DataFrame:
    """電デバと設備投資の検証用シグナルを、利用可能日基準で作成する。"""
    signals = pd.DataFrame()
    for output_name, source_column in {
        "電デバ出荷前年比": "出荷_原指数",
        "電デバ在庫前年比": "在庫_原指数",
    }.items():
        if source_column in iip_frame:
            series = _clean_series(iip_frame[source_column])
            signals[output_name] = series.pct_change(12, fill_method=None) * 100

    if machinery_orders is not None:
        orders = _clean_series(machinery_orders)
        average = orders.rolling(3, min_periods=3).mean()
        signals["電子計算機等受注3か月平均前年比"] = (
            average.pct_change(12, fill_method=None) * 100
        )
    if signals.empty:
        return signals

    signals = signals.sort_index().dropna(how="all")
    signals.index = conservative_release_dates(signals.index, release_lag_months)
    signals.index.name = "利用可能日"
    return signals[~signals.index.duplicated(keep="last")]


def analyze_release_aware_lead_lag(
    signal: pd.Series,
    asset_prices: pd.Series,
    horizons: tuple[int, ...] = (0, 1, 2, 3, 6),
    low_sample_threshold: int = 12,
) -> pd.DataFrame:
    """利用可能日以降の月末価格だけで、指標と株価リターンの相関を比較する。"""
    clean_signal = pd.to_numeric(signal, errors="coerce").dropna().sort_index()
    prices = _clean_daily_prices(asset_prices)
    rows: list[dict[str, object]] = []
    for horizon in horizons:
        paired: list[tuple[float, float]] = []
        for available_at, value in clean_signal.items():
            base_values = prices.loc[prices.index < available_at]
            if base_values.empty:
                continue
            target_month = pd.Timestamp(available_at) + pd.DateOffset(months=horizon)
            target_values = prices.loc[
                (prices.index >= available_at)
                & (prices.index <= target_month.to_period("M").to_timestamp("M"))
            ]
            if target_values.empty:
                continue
            base = float(base_values.iloc[-1])
            if base == 0:
                continue
            paired.append((float(value), (float(target_values.iloc[-1]) / base - 1) * 100))
        sample = pd.DataFrame(paired, columns=["signal", "return"])
        count = len(sample)
        correlation = None if count < 2 else float(sample.corr().iloc[0, 1])
        rows.append(
            {
                "期間": BACKTEST_HORIZONS.get(horizon, f"{horizon}か月後"),
                "相関": correlation,
                "サンプル数": count,
                "注意": "サンプル少" if count < low_sample_threshold else "",
            }
        )
    return pd.DataFrame(rows)


def analyze_semiconductor_condition_returns(
    signals: pd.DataFrame,
    condition: str,
    asset_prices: pd.Series,
    horizons: tuple[int, ...] = (1, 3, 6),
    low_sample_threshold: int = 12,
) -> pd.DataFrame:
    """公表後に条件が判明した過去局面の将来リターンを集計する。"""
    condition_dates = _condition_dates(signals, condition)
    prices = _clean_daily_prices(asset_prices)
    rows: list[dict[str, object]] = []
    for horizon in horizons:
        returns: list[float] = []
        for available_at in condition_dates:
            before = prices.loc[prices.index < available_at]
            target_date = available_at + pd.DateOffset(months=horizon)
            after = prices.loc[prices.index >= target_date]
            if before.empty or after.empty or before.iloc[-1] == 0:
                continue
            returns.append(float((after.iloc[0] / before.iloc[-1] - 1) * 100))
        sample = pd.Series(returns, dtype=float)
        count = len(sample)
        rows.append(
            {
                "期間": CONDITIONAL_HORIZONS.get(horizon, f"{horizon}か月後"),
                "平均": None if sample.empty else float(sample.mean()),
                "中央値": None if sample.empty else float(sample.median()),
                "上昇確率": None if sample.empty else float((sample > 0).mean() * 100),
                "サンプル数": count,
                "注意": "サンプル少" if count < low_sample_threshold else "",
            }
        )
    return pd.DataFrame(rows)


def _condition_dates(signals: pd.DataFrame, condition: str) -> pd.DatetimeIndex:
    definitions = {
        "出荷前年比プラス転換": ("電デバ出荷前年比", "positive_cross"),
        "在庫前年比マイナス転換": ("電デバ在庫前年比", "negative_cross"),
        "受注3か月平均前年比+20%以上": ("電子計算機等受注3か月平均前年比", "above_20"),
    }
    if condition not in definitions:
        raise ValueError(f"未対応の条件です: {condition}")
    column, method = definitions[condition]
    if column not in signals:
        return pd.DatetimeIndex([])
    series = pd.to_numeric(signals[column], errors="coerce")
    if method == "positive_cross":
        selected = (series > 0) & (series.shift(1) <= 0)
    elif method == "negative_cross":
        selected = (series < 0) & (series.shift(1) >= 0)
    else:
        selected = series >= 20
    return pd.DatetimeIndex(signals.index[selected.fillna(False)])


def _clean_daily_prices(series: pd.Series) -> pd.Series:
    clean = pd.to_numeric(series, errors="coerce").dropna().sort_index().copy()
    clean.index = pd.DatetimeIndex(clean.index).tz_localize(None).normalize()
    return clean[~clean.index.duplicated(keep="last")]


def _cycle_assessment(summary: pd.DataFrame) -> str:
    values = {
        row["指標"]: row
        for _, row in summary.iterrows()
        if pd.notna(row.get("前年同月比"))
    }
    shipment = values.get("出荷")
    inventory = values.get("在庫")
    if shipment is None or inventory is None:
        return "出荷と在庫の前年比がそろわず、現在地を整理できません。"

    shipment_yoy = float(shipment["前年同月比"])
    inventory_yoy = float(inventory["前年同月比"])
    phase = classify_inventory_cycle(shipment_yoy, inventory_yoy)
    if phase == "需給改善方向":
        base = "出荷が前年を上回る一方で在庫は減少しており、需給改善方向の候補です。"
    elif phase == "需要拡大・在庫積み増し":
        base = "出荷と在庫がともに増えており、需要拡大と在庫積み増しが並行する局面候補です。"
    elif phase == "需要減速・在庫過剰リスク":
        base = "出荷が前年を下回る一方で在庫は増えており、在庫過剰リスクに注意が必要です。"
    else:
        base = "出荷と在庫がともに減っており、減産・在庫調整局面の候補です。"

    inventory_ratio = values.get("在庫率")
    if inventory_ratio is None:
        return base
    ratio_yoy = float(inventory_ratio["前年同月比"])
    ratio_text = "上昇" if ratio_yoy > 0 else "低下" if ratio_yoy < 0 else "横ばい"
    return f"{base} 在庫率は前年比{ratio_text}で、単独ではなく出荷・在庫と合わせて確認します。"


def _clean_series(series: pd.Series) -> pd.Series:
    clean = pd.to_numeric(series, errors="coerce").dropna().copy()
    clean.index = (
        pd.DatetimeIndex(clean.index)
        .tz_localize(None)
        .to_period("M")
        .to_timestamp()
    )
    return clean[~clean.index.duplicated(keep="last")].sort_index()


def _exact_change(
    series: pd.Series, current_date: pd.Timestamp, comparison_date: pd.Timestamp
) -> float | None:
    if (
        current_date not in series.index
        or comparison_date not in series.index
        or pd.isna(series.loc[current_date])
        or pd.isna(series.loc[comparison_date])
        or series.loc[comparison_date] == 0
    ):
        return None
    return float((series.loc[current_date] / series.loc[comparison_date] - 1) * 100)
