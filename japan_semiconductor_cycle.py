from __future__ import annotations

import pandas as pd


IIP_DISPLAY_ORDER = ("在庫率", "出荷", "生産", "在庫")
INVENTORY_CYCLE_PHASES = {
    (True, False): "需給改善方向",
    (True, True): "需要拡大・在庫積み増し",
    (False, True): "需要減速・在庫過剰リスク",
    (False, False): "減産・在庫調整",
}


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
