# Japan Core 20: J-Quants API V2 Financial Summary 診断

調査日: 2026-09-09

対象: Japan Core 20（20銘柄）
状態: **実データ診断は保留（この実行環境に `JQUANTS_API_KEY` がないため）**

## Executive Summary

J-Quants API V2は、Yahoo Finance由来の不揃いな四半期P/Lを置き換え得る第一候補である。公式Python ClientのFinancial Summary APIには、売上高、営業利益、純利益、EPS、開示日、対象期間、決算種別、通期会社予想のフィールドがある。

ただし、今回の実行環境には有効な `JQUANTS_API_KEY` が設定されていない。そのため、Core20の取得成功率、8四半期カバレッジ、実際の累計/単独定義、会計基準差、Forecastカバレッジを実測していない。**Fundamentals / Earnings v1のGo / Conditional Go / No-GoはPendingであり、本番UIは変更していない。**

代わりに、公式Clientによる低頻度の取得層、共通正規化スキーマ、累計値を誤認しない単独四半期導出、同一Fiscal Quarter間だけのYoY、fixtureテスト、再実行用スクリプトを追加した。キー設定後に実データ診断を行い、その結果だけで実装可否を判断する。

## J-Quants API V2仕様と採用候補

| 項目 | 確認結果 |
| --- | --- |
| 認証 | J-Quantsダッシュボードで発行するAPI KeyをV2 Clientへ渡す方式。V1のID/パスワード・refresh token方式は使わない。 |
| Secret | ローカルは `JQUANTS_API_KEY`、Streamlitは同名Secretを優先。値はコード・ログ・テスト・文書へ出さない。 |
| Client | 公式 `jquants-api-client` の `jquantsapi.ClientV2`。 |
| 主Endpoint | `get_fin_summary(code=...)`。銘柄単位で履歴を取得し、公式Clientのpaginationを利用する。 |
| 補助Endpoint | `get_fin_summary_range`、`get_fin_earnings_date`。Financial DetailsはSummaryに不足が確認された場合だけ検討する。 |
| Range取得 | 公式Clientのrange helperは日付単位の呼出しを行うため、Core20診断の主経路には使わない。 |
| プラン | 現行公式プラン表ではFreeでFinancial Summaryと直近2年（12週遅延）、Lightで5年、Standardで10年、Premiumで全期間等が案内されている。契約・変更の可能性があるため、実行前にユーザーのアカウント画面で再確認する。 |

公式参照: [JPX J-Quants API](https://www.jpx.co.jp/markets/other-data-services/j-quants-api/)、[公式Python Client](https://github.com/J-Quants/jquants-api-client-python)、[J-Quants公式プラン](https://jpx-jquants.com/)。

## 実データ診断の実行方法

APIキーを安全に設定した後、リポジトリ直下で次を実行する。

```powershell
$env:JQUANTS_API_KEY = "<J-Quants dashboardで発行したキー>"
python scripts/diagnose_jquants_fundamentals.py
```

キーをリポジトリ、`.env`、テストfixture、ログ、PR本文へ保存・貼付しない。Streamlit本番では `st.secrets["JQUANTS_API_KEY"]` を利用できる。診断はキーの値を表示しない。

標準ではFree相当の低頻度（1回/12秒）で銘柄ごとに取得する。APIキーの契約プランと最新のrate limitを確認し、必要時だけ `JQUANTS_REQUESTS_PER_MINUTE` 相当の呼出し設定を調整する。現時点のスクリプトはその値を自動変更しない。

## 共通Fundamentals Schema

取得層は、将来のTDnet・EDINETと同じ分析層に渡せる次の長形式を返す。

`ticker`, `code`, `jquants_code`, `company_name`, `disclosure_date`, `reference_period`, `fiscal_year`, `fiscal_quarter`, `document_type`, `accounting_standard`, `consolidated_flag`, `metric`, `value`, `unit`, `currency`, `is_cumulative`, `is_derived`, `source_name`, `source_url`, `fetched_at`

- Yahoo Financeの `7203.T` とJ-Quantsの5桁コード `72030` は明示的に変換する。
- `disclosure_date` はAPIの `DiscDate` だけを使用し、推定しない。
- `reference_period` は `CurPerEn`、取得時刻は `fetched_at` として別に保持する。
- 金額の単位を取得結果なしに推測して表示しない。正規化時は `unit` を未確定として保持し、実レコードと公式定義で確認後にUIの金額表示を有効化する。
- 現在期の `Sales` / `OP` / `NP` / `EPS` と、通期Forecastの `FSales` / `FOP` / `FNP` / `FEPS` を別metricとして保持する。

## 1Q / 2Q / 3Q / FYと累計値

J-Quants実レコードの `CurPerType`、`CurPerSt`、`CurPerEn`、`CurFYSt`、`CurFYEn` を保存する。現時点で実レコードを確認していないため、すべての会社・会計基準について同じ累計定義だとは仮定しない。

単独四半期を導出できるのは、以下が全て満たされる場合だけである。

1. 期別・対象期間・会計基準・連結/単体が同一の比較可能な生データである。
2. Q2 / Q3 / FYが期首からの累計であることを期間日付から確認できる。
3. 前累計値が存在し、単位・通貨が同じである。
4. 決算期変更、会計基準変更、改定等で比較不能と判定されない。

この場合のみ、Q2=H1−Q1、Q3=9M−H1、Q4=FY−9Mとし、`is_derived=true` を必ず付与する。定義不明なら導出もQoQも行わない。YoYはCalendar Quarterではなく同一Fiscal Quarter・連続Fiscal Yearだけで計算する。

## 実データで判定する項目

| Metric | Core20 Coverage | 8 Quarter Coverage | Definition Quality | v1 Suitability |
| --- | ---: | ---: | --- | --- |
| Revenue | Pending | Pending | Pending record review | Pending |
| Operating Profit | Pending | Pending | Pending record review | Pending |
| Net Income | Pending | Pending | Pending record review | Pending |
| EPS | Pending | Pending | Pending record review | Pending |
| Forecast Revenue | Pending | N/A | Pending record review | Pending |
| Forecast Operating Profit | Pending | N/A | Pending record review | Pending |
| Forecast Net Income | Pending | N/A | Pending record review | Pending |
| Forecast EPS | Pending | N/A | Pending record review | Pending |

実行後はトヨタ、INPEX、MUFG、フジクラ、リクルートHD、JR東日本、中外製薬を重点確認し、銀行・保険を一般事業会社の営業利益率へ無理に当てはめない。

## Go / No-Go基準

- **Go:** Core20の80〜90%以上でRevenue、Operating Profit、Net Income、EPSの各指標に安全な8四半期程度の履歴がある。
- **Conditional Go:** 業種非適用を除けば主要Trendが可能で、Unavailableや業種差をUIで正確に分離できる。
- **No-Go:** 定義・累計/単独・履歴の不整合によりEarnings Trendを誤認させる可能性が高い。

今回の結論は **Pending**。キーなしで得られる仕様情報だけを根拠にUIを実装しない。

## TDnet / EDINETの位置付け

J-Quantsの実測がNo-Goまたは重要指標不足の場合にだけ次を調査する。

- **TDnet:** 決算短信、業績予想修正、適時開示の一次資料。今回、自前HTML/PDFスクレイパーは実装しない。
- **EDINET API V2:** 有価証券報告書・半期報告書・XBRLの詳細分析候補。連続する1Q/2Q/3Q/FYの代替になり得るか、制度・提出書類・APIキー・XBRL正規化コストを実測して判断する。

現段階では、整形済みFinancial Summaryを優先する順序を **J-Quants → TDnet → EDINET → Yahoo Finance補助** とする。

## 推奨Architectureと制約

- `jquants_loader.py` は認証、コード変換、低頻度取得、部分失敗、正規化、単独四半期導出、YoY、coverageを担当する。UIはAPIを直接呼ばない。
- 本番UI、`app.py`、Stock Detail、既存Macro / Anchor / Residual分析は変更していない。
- 一銘柄のAPI失敗は当該codeだけをfailureとして返し、他の結果を破棄しない。
- API key未設定、API障害、rate limit、期別不明、累計定義不明、会計基準差は個別にUnavailableとして扱う設計である。
- APIキー設定後の実データ診断、プラン確認、実レコードの単位確認、8四半期カバレッジ測定が完了するまで、Earnings Momentum・Forecast表示・進捗率・Fundamentals UIは実装しない。
