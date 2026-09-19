# 次に進める改善

最終更新: 2026-09-19

このファイルには未完了の項目だけを記載します。完了済みの項目は[`docs/COMPLETED_ROADMAP.md`](docs/COMPLETED_ROADMAP.md)へ移します。

## Investment Roadmap

目的: 既存データを投資判断の材料へつなげ、過去の傾向・市場間関係・テーマを直感的に確認できるようにする。

1. Phase 4: 個人の投資行動につなげる（低優先）
   - 保有資産を登録し、資産ごとの市場要因への感応度を確認できるようにする。
   - Bull / Base / Bearシナリオとポートフォリオの主要リスクを整理する。

共通原則:

- 過去分析はサンプル数と低標本警告を表示し、将来予測・投資助言として見せない。
- 新規データを増やす前に、既存の指標、相関、急変検知、マクロ、イベントを再利用する。
- 数字だけでなく、投資判断に何が追加されるかを短く説明する。

## Japan Semiconductor Cycle Roadmap

目的: 日本の半導体について、市場価格、実体経済、在庫循環、設備投資、過去の株価反応を一つの分析導線へつなげる。

1. Japan Semiconductor Cycle Score（保留）
   - 暫定検証ではリード・ラグ相関が弱く、条件付き将来リターンも低標本のため、現時点では実装しない。
   - 履歴公表日と当時公表値を取得でき、複数資産・複数指標で安定した有用性を確認できた場合に限り、各要素の寄与を開示する説明可能な0〜100スコアを再検討する。

共通原則:

- 最新ファイルによる現在地と、当時公表値によるバックテストを区別する。
- 季節調整済指数は前月比較・トレンド、原指数は前年比に使用する。
- 対象月と公表日を区別し、過去検証では公表日前の株価へ情報を混入させない。
- 在庫・在庫率を単独で強弱判定せず、生産・出荷と組み合わせる。
- データから見た局面候補として表示し、将来予測や投資助言として扱わない。

## Semiconductor Roadmap

目的: 市場価格、台湾の先行需要、韓国の実際の輸出、日本の生産・在庫・設備投資をつなぎ、半導体株の動きとグローバル実需を同じ導線で確認できるようにする。

韓国半導体輸出の長期履歴拡張は終了した。[`docs/KOREA_SEMICONDUCTOR_HISTORY_DIAGNOSTIC.md`](docs/KOREA_SEMICONDUCTOR_HISTORY_DIAGNOSTIC.md)でKOSIS / ITSTATを、[`docs/KOREA_ICT_ARCHIVE_DIAGNOSTIC.md`](docs/KOREA_ICT_ARCHIVE_DIAGNOSTIC.md)で旧MSIT公式記事archiveを診断したが、2021年以降の実公表日と当時値を連続して自動復元できないため、厳密Historical Validation延長は**NO-GO**とする。現行の2023年6月開始を維持し、同じ経路の調査は反復しない。

1. 台湾データ品質改善
   - 完了。[`docs/TAIWAN_EXPORT_ORDERS_HISTORY_DIAGNOSTIC.md`](docs/TAIWAN_EXPORT_ORDERS_HISTORY_DIAGNOSTIC.md)のGO判定に基づき、[`docs/TAIWAN_EXPORT_ORDERS_ARCHIVE_LOADER.md`](docs/TAIWAN_EXPORT_ORDERS_ARCHIVE_LOADER.md)の独立archive loaderと正規化snapshotを実装した。current CSVとarchive vintageを分離し、公表日・当時値・公式前年比の欠損をcurrent CSVで補完しない。公式一覧は2021年1月～2026年7月の67か月、欠損候補0。代表3か月（2021-01、2023-06、2025-01）はlive parse済み。初期月と全期間を再確認し、連続して安全なstrict開始月は2022-08とした。
2. 海外Historical Validation拡張
   - 実施。strictは台湾archive snapshotと韓国の実公表日付き月次履歴、provisionalは台湾current CSVと現行韓国データへ入力分離した。台湾snapshotは2022-08～2026-01の42か月・84行・欠損0。韓国は現行の2023-06開始を維持し、台湾＋韓国複合条件はそれ以前へ遡及しない。台湾相関標本は主要4資産で42、キオクシアで15へ増えたが、相関は期間・資産で一貫せず、複合条件は8件（キオクシア4件）で低標本警告が残る。結果は公表後の関係として表示し、Cycle Scoreや売買シグナルへ昇格させない。
3. 米国Big TechのAI関連設備投資（CapEx）分析（中期）
   - Japan Core 20 / Macro Sensitivityと今後の個別株分析に一定の目途がついた後、Microsoft、Alphabet / Google、Amazon、Metaを中心に着手する。必要に応じてOracle、Apple、その他主要Cloud / Hyperscalerも検討する。
   - 四半期CapEx、前年比、前四半期比、トレンド、Guidance、AI / Data Center関連の投資額・計画、各社合計CapEx、合計前年比、CapEx momentumを候補とする。
   - 会計上のCapEx全体とAI専用CapExを混同せず、企業間の定義差と、AI関連額を公式に分離できる範囲を明示する。
   - Big Tech CapEx / AI Investment → Taiwan Orders → Korea Exports → Japan Production / Shipments / Inventory → Corporate Earnings → Semiconductor Market / SOX → Price vs Fundamentals → Historical Validationという上流から下流の分析導線を検討する。
   - CapEx、Guidance、momentumが台湾受注、韓国輸出、日本の生産・出荷、SOX、日本主要半導体株に先行したかを公表日基準で検証し、Proxy・相関・先行指標を混同しない。
   - 着手時に公式データ、SEC filings / Investor Relations資料、CapEx定義の企業間差、AI関連CapExの抽出可能性、Guidance、公表日管理、Historical Validation手法を改めて調査する。
   - 次候補。ただし台湾strict拡張後も資産・条件別の低標本警告と期間依存性を確認し、Cycle Scoreは引き続き保留する。
4. Global Semiconductor Cycle Score（保留）
   - 複数地域・複数資産で安定した有用性を確認できた場合に限り、各要素の寄与を開示する説明可能なスコアを再検討する。

共通原則:

- 将来はAI Investment → Orders → Exports → Production / Inventory → Corporate Earnings → Market Priceの資金・サプライチェーンを可視化し、現在はMarket → Global Demand → Japan Cycle → Price vs Fundamentals → Historical Validationの順で管理する。
- 台湾輸出受注は注文、韓国半導体輸出は金額、日本の統計は生産・出荷・在庫・設備投資として役割を区別する。
- 対象期間、公表日、取得日時、速報・暫定・確定を混同しない。
- 公式値と当アプリ計算値を区別し、公表日や営業日調整値を推測で補完しない。
- 厳密検証は実際の公表日がある観測だけを使い、推定利用可能日や改定後データによる暫定検証と混在させない。

## Japan Equity Roadmap

目的: 個人投資家向けの日本株分析を、**業績 → 評価水準 → 価格の反応 → リスク**の導線で段階的に整備する。Market Exposure、Macro Sensitivity、Residual、相関は補助情報として位置付ける。Streamlitを継続し、個人利用規模に不要なバックエンド移行は行わない。

A. 決算比較、B. 価格品質・時点・期間整合、C. 日本株主画面への統合は完了済みとして[`docs/COMPLETED_ROADMAP.md`](docs/COMPLETED_ROADMAP.md)へ移した。

1. **Decision Log / Forward Validation（現在の最優先）**
   - Core20の判断区分、根拠、想定期間、判断時点Snapshotを追記保存し、20・60・120営業日後に同一終点の個別株・TOPIXリターンを評価するMVPを運用する。
   - Supabase設定後に実判断・仮想判断を蓄積し、未満了・価格品質・共通終点欠損の扱いが実データでも明確か確認する。
   - 理由別勝率や統合スコアへ進む前に、Snapshot schemaと前向き評価の継続性を検証する。
2. **評価水準に必要なデータと比較条件の整備**
   - [`docs/VALUATION_READINESS.md`](docs/VALUATION_READINESS.md)でpoint-in-time選択と安全停止条件を実装した。Yahoo調整後価格とJ-Quants EPSを当アプリで組み合わせるCurrent Forward PERは停止し、`AdjFactor=1`を`basis_verified`へ緩和しない。
   - 2026-09-18の最終live診断（**ユーザー提供結果**）は、Core20 20、Financial Summary取得失敗0、有効Current Forecast EPS 14/20、Adjustment bars成功17/20、API error 0、`input_unavailable` 3、safe Current Forward PER 0/20、Forecast Revision comparable 0/20、Historical Forward PER 0/20、split/per-share basis unverified 20/20。J-Quants価格終端2026-06-26、Yahoo価格終端2026-09-16、lag 82日だった。
   - [`docs/JQUANTS_VALUATION_API_FIT.md`](docs/JQUANTS_VALUATION_API_FIT.md)で、同一提供元が算出する公式Valuation APIへ方針を切り替えて限定調査した。進行期会社予想純利益、当日終値、翌営業日反映は公式確認できた一方、株式数・企業行動・決算期変更の詳細計算仕様は非開示で、対象Fiscal Yearと元開示日もレスポンスにないため、自動PERは**HOLD**とする。
   - 再開条件は、FwdEPS/FwdPERの株式数・自己株式・分割/併合・遡及修正の扱いを説明可能な範囲まで確認すること、対象年度の表示方針を決めること、Light以上の継続費用（月額1,650円・税込）を許容して代表銘柄を限定確認すること、公式Client v2.7.0への更新を検証すること。
   - 自動PERを保留した次の実装として、同一対象年度・同一定義の会社予想売上/営業利益/純利益の更新履歴を業績画面とDecision Log Snapshotへ接続した。これはValuationとは表示しない。basis未確認のEPSペアから差額、修正率、方向判定、ランキング、シグナル、連続グラフを作らない。
   - Historical PER、同業ランキング、割安/割高判定は対象外。2026-09-16 live raw Summaryで確認した`BPS=82`、`Eq=174`、`ShOutFY=174`、`AvgSh=174`も、normalizer/basis再診断前はPBR表示に使わない。
   - 株価上昇率やTOPIX比を割安・割高の代用にせず、比較可能な同業・自社履歴がない倍率は単独で評価しない。

Corporate Events Lite、TDnet Full、Event Study、General Newsは、A〜Cの主導線を安定化した後に別途優先順位を判断する。TDnetで不足する詳細Fundamentalsが必要な場合だけ、EDINET APIのXBRLを候補として調査する。
3. Arbitrary Japanese Stock Analysis（将来）
   - 任意Ticker入力と、Core20 Anchorを参照した市場・Macro・相対行動の比較を追加する。

共通原則:

- Core 20内集計をTOPIX業種指数の代替として扱わない。
- Market Exposure、事前定義済みPrimary Driver、データ観測後のEx post相関を区別し、相関を因果関係や先行性として表示しない。
- TOPIX連動ETFをProxyとして使用する場合は指数そのものではないことを明示する。

## Technical Roadmap

現在、着手待ちの項目はありません。新しい技術課題は、目的・優先順位・完了条件を決めてからここへ追加します。

## 実装時の注意

- 通常表示を優先し、補足情報は詳細表示へ置く。
- モバイルでも見やすいグラフ高さ・凡例位置を維持する。
- 相関は過去の傾向であり、将来予測・投資判断ではないことを画面に明記する。
- 代替ETFは元指数と同一ではないため、代替使用時の警告・実ティッカー・単位を維持する。
- 経済イベントの日程は収録期限と公式データ元を画面に明記する。
