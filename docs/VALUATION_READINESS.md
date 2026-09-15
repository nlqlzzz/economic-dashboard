# Valuation Data Readiness Diagnostic

診断日: 2026-09-16

対象: Japan Core20

live実測状態: **Environment Blocked / JQUANTS_API_KEY unavailable**

## 結論

今回は本番画面へPER/PBRを追加していない。固定fixtureではpoint-in-time選択、予想修正比較、価格品質、通貨・単位、正のEPS、per-share basisを分離して判定できた。一方、このCodex環境では環境変数およびリポジトリ固有のignored Streamlit SecretsからAPIキーを参照できず、Core20のlive coverageは実測していない。過去の20/20 Fundamentals取得実績を、今回のvaluation coverageへ流用していない。

| 項目 | 判定 | 理由 |
| --- | --- | --- |
| A. Current Forward PER | **CONDITIONAL** | 数学・時点・品質条件は実装可能。Yahoo `auto_adjust=True`価格とJ-Quants FEPSのper-share basisを現行データだけで確認できないため、本番値はまだ出さない。 |
| B. Forecast EPS Revision | **CONDITIONAL** | 同一Fiscal Year・会計定義内の比較ロジックは実装可能。Core20各社の複数開示coverageはlive未確認。正式な「業績予想修正」とは呼ばず、会社予想更新として扱う。 |
| C. Historical Self-PER | **NO-GO** | 次取引日有効化は可能だが、長期の価格・EPS双方の分割basisをつなぐ根拠が未整備。 |
| D. PBR | **NO-GO（現行正規化）** | 公式Clientのraw Summary列にはBPS等があるが、現行normalizerは保持していない。株式数・分割basisを確認してから別診断が必要。 |
| E. Sector-specific valuation | **NO-GO** | 銀行・保険等を含む評価モデルは未設計。PER単独の割安・割高判定は行わない。 |

## 利用可能なデータと確認結果

- J-Quants公式Python Client 2.6.0の`get_fin_summary`を利用候補とする。既存の`fetch_financial_summaries`と`normalize_financial_summaries`を再利用する。
- 正規化済み`forecast_eps`はFiscal Year、Disclosure Date、Accounting Standard、Consolidated Flag、Currency、Unitを保持する。
- インストール済み公式Clientの`FIN_SUMMARY_COLUMNS_V2`には`FEPS`、`BPS`、`NCBPS`、`Eq`、`NCEq`、`ShOutFY`、`AvgSh`が定義されている。ただし値のlive coverageは未確認であり、存在を取得済みと読み替えない。
- 同Clientの日足列には`AdjFactor`、調整前OHLC、`AdjC`等がある。JPXもJ-Quants株価が分割等を考慮した調整済み・調整前価格を含むと説明している。しかし現在のアプリ価格はYahoo Finance `auto_adjust=True`であり、Summary FEPSと同じ1株basisかを示す共通識別子は現行正規化schemaにない。
- 根拠のない分割係数推定は行わない。`AdjFactor=1`から分かるのは、観測区間にeffectiveな調整イベントが検出されなかったことだけであり、`no_effective_action_detected`と記録する。会社予想が将来の分割を先に反映した可能性は排除できないため、Current PERはFEPSと価格basisを直接確認できる`basis_verified`の場合だけ計算可能とする。

公式資料: [JPX J-Quants API](https://www.jpx.co.jp/markets/other-data-services/j-quants-api/)、[J-Quants公式Python Client](https://github.com/J-Quants/jquants-api-client-python)

## Current Forward PERの適合条件

`valuation.assess_current_forward_per`は、以下をすべて満たす場合だけ`current price / forecast EPS`を返す。

1. 価格系列が既存`inspect_price_series`で利用可能。
2. 最新価格とその基準日が存在する。
3. Forecast Disclosure Dateが価格基準日以前。
4. Forecast Fiscal Year、対象期末、Disclosure Date、Accounting Standard、Consolidated Flagが明示され、対象期が失効していない。
5. CurrencyがJPY、Unitが既知の円/株候補。
6. Forecast EPSが正。0以下は負のPERを作らず`N/M候補`。
7. 価格とEPSのper-share basisが確認済み。

欠損を0に置換せず、複数条件に抵触した場合は理由を列挙する。

## Forecast EPS Revision

`build_forecast_eps_revisions`はTicker、Fiscal Year、Reference Period、Accounting Standard、Consolidated Flag、Currency、Unitが同じcohort内だけをDisclosure Date順に比較する。

- 前回値が正の場合だけ前回比%を計算する。
- 赤字予想・ゼロ跨ぎは金額差と`turned_positive` / `turned_non_positive`を優先する。
- Fiscal Yearが変わる行は新しい系列の初回観測であり、上方・下方修正にしない。
- 2開示間に`AdjFactor`の変化があれば`basis_changed`とし、通常のup/downや修正率には数えない。変化が検出されなくても直接basisを確認できなければ`basis_unverified`とし、live coverageの比較可能ペアに数えない。
- Financial SummaryだけではTDnet上の正式な修正開示か判別できないため、「会社予想更新」候補である。

## Historical Forward PER

`forecast_available_on`は価格日より**前**に開示され、Reference Periodが価格日以降で、Fiscal Year、Reference Period、Accounting Standard、Consolidated Flag、Currency、Unitが有効な最後のforecastだけを返す。開示時刻が確定していないため、開示当日終値には適用しない。対象期終了後は、次年度予想がなくても古いforecastを使い続けない。

現状はper-share basisが直接`basis_verified`と確認できない限り履歴を生成しない。`no_effective_action_detected`だけでは生成せず、future disclosureを過去価格へ遡及適用せず、分割係数も推測しない。

## Core20 live診断表

`—`は欠損値ではなく**今回未実測**を表す。各行の`NO-GO（未実測）`は環境上の実行ゲートであり、銘柄データ品質の最終評価ではない。

| Ticker | 会社名 | Sector | Price date | Price | Forecast EPS | Forecast FY | Forecast disclosure | Current PER? / 理由 | Revision obs | Historical PER | Split basis | Sector caution | Verdict |
| --- | --- | --- | --- | ---: | ---: | --- | --- | --- | ---: | --- | --- | --- | --- |
| 7203.T | トヨタ自動車 | 自動車・輸送機 | — | — | — | — | — | 未実測 | — | 未実測 | 未確認 | PER単独判定不可 | NO-GO（未実測） |
| 8306.T | 三菱UFJフィナンシャル・グループ | 銀行 | — | — | — | — | — | 未実測 | — | 未実測 | 未確認 | 信用コスト・資本規制を別途確認 | NO-GO（未実測） |
| 8058.T | 三菱商事 | 商社 | — | — | — | — | — | 未実測 | — | 未実測 | 未確認 | 保有資産・投資損益を別途確認 | NO-GO（未実測） |
| 1605.T | INPEX | エネルギー | — | — | — | — | — | 未実測 | — | 未実測 | 未確認 | PER単独判定不可 | NO-GO（未実測） |
| 7011.T | 三菱重工業 | 資本財 | — | — | — | — | — | 未実測 | — | 未実測 | 未確認 | PER単独判定不可 | NO-GO（未実測） |
| 4063.T | 信越化学工業 | 化学 | — | — | — | — | — | 未実測 | — | 未実測 | 未確認 | PER単独判定不可 | NO-GO（未実測） |
| 8802.T | 三菱地所 | 不動産 | — | — | — | — | — | 未実測 | — | 未実測 | 未確認 | 資産価値・金利を別途確認 | NO-GO（未実測） |
| 8766.T | 東京海上ホールディングス | 保険 | — | — | — | — | — | 未実測 | — | 未実測 | 未確認 | 運用損益・自然災害・資本政策を別途確認 | NO-GO（未実測） |
| 9983.T | ファーストリテイリング | 小売 | — | — | — | — | — | 未実測 | — | 未実測 | 未確認 | PER単独判定不可 | NO-GO（未実測） |
| 6501.T | 日立製作所 | 電機・IT | — | — | — | — | — | 未実測 | — | 未実測 | 未確認 | PER単独判定不可 | NO-GO（未実測） |
| 5401.T | 日本製鉄 | 鉄鋼 | — | — | — | — | — | 未実測 | — | 未実測 | 未確認 | 市況循環を別途確認 | NO-GO（未実測） |
| 5803.T | フジクラ | 電線・AIインフラ | — | — | — | — | — | 未実測 | — | 未実測 | 未確認 | PER単独判定不可 | NO-GO（未実測） |
| 6301.T | 小松製作所 | 機械 | — | — | — | — | — | 未実測 | — | 未実測 | 未確認 | PER単独判定不可 | NO-GO（未実測） |
| 4519.T | 中外製薬 | 医薬品 | — | — | — | — | — | 未実測 | — | 未実測 | 未確認 | 開発パイプラインを別途確認 | NO-GO（未実測） |
| 2914.T | JT | 生活必需品 | — | — | — | — | — | 未実測 | — | 未実測 | 未確認 | PER単独判定不可 | NO-GO（未実測） |
| 9503.T | 関西電力 | 電力 | — | — | — | — | — | 未実測 | — | 未実測 | 未確認 | 規制・燃料費を別途確認 | NO-GO（未実測） |
| 9020.T | JR東日本 | 鉄道 | — | — | — | — | — | 未実測 | — | 未実測 | 未確認 | PER単独判定不可 | NO-GO（未実測） |
| 9432.T | NTT | 通信 | — | — | — | — | — | 未実測 | — | 未実測 | 未確認 | PER単独判定不可 | NO-GO（未実測） |
| 9984.T | ソフトバンクグループ | 投資・テクノロジー | — | — | — | — | — | 未実測 | — | 未実測 | 未確認 | 保有資産・投資損益を別途確認 | NO-GO（未実測） |
| 6098.T | リクルートホールディングス | 人材・サービス | — | — | — | — | — | 未実測 | — | 未実測 | 未確認 | PER単独判定不可 | NO-GO（未実測） |

### Coverage集計

| 指標 | 結果 |
| --- | ---: |
| Current Forward PERを安全に計算可能 | live未確認（—/20） |
| Forecast EPS revision比較可能 | live未確認（—/20） |
| Historical Forward PERを十分構築可能 | live未確認（—/20） |
| Split / per-share basis問題 | live未確認（—/20、現行schemaでは全社未確認扱い） |
| PBR | live未確認。現行正規化schemaはNo-Go |

## 再実行方法

APIキーを環境変数またはignored `.streamlit/secrets.toml`へ安全に設定し、次を実行する。キー値は出力されない。

```powershell
python scripts/diagnose_valuation.py --output artifacts/valuation_readiness.json
```

デフォルトはCore20を低頻度（5 requests/minute）で取得する。JSONはCore20各社の判定理由、revision観測、raw BPS・株式数関連フィールドの非null件数を分離して出力する。取得結果を文書へ反映する際は、実測日時・契約プラン・failure数を併記する。

## 次PRの推奨範囲

1. **第1段階:** キー利用可能環境でCore20 live診断を実行し、同一Fiscal YearのForecast EPS Revision coverageを確定する。十分なら「会社予想更新履歴」だけを実装候補とする。
2. **第2段階:** J-Quants調整係数・調整前後価格とFEPS/BPS/株式数のbasisを公式仕様・実データで突合する。確認できた銘柄・期間に限定してCurrent Forward PERを実装する。Historical PERとPBRはこの確認後に再判定する。

Decision Logのschema、Snapshot、前向き評価は今回変更していない。
