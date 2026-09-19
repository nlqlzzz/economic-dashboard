# 韓国半導体輸出の長期履歴診断

調査日: 2026-09-19

対象表: KOSIS / ITSTAT `DT_092_115_2009_S023`

判定: **NO-GO（厳密 Historical Validation の延長）**

## 1. 調査目的

現行の韓国半導体輸出系列より長い point-in-time 検証履歴を、公式統計から安全に作れるかを限定診断した。本診断は本番 loader、UI、Historical Validation、既存 schema を変更しない。

確認状態は次のように区別する。

- **公式確認済み**: KOSIS / ITSTAT、科学技術情報通信部または産業通商部の公式画面・仕様で確認した事項
- **live確認済み**: 2026-09-19 に実際の公式表または現行 loader で確認した事項
- **未確認**: 公式資料から確定できず、推測しない事項

## 2. 現行韓国データフロー

`global_semiconductor_demand.py` は韓国関税庁の旬次速報、産業通商部の月次輸出入動向、産業通商部の ICT 輸出入動向を parse する。月次一般貿易と ICT の半導体輸出は、いずれも `korea_semiconductor_exports_monthly` として生成される。ICT の記事記載額（億ドル）は100倍して `million USD` に正規化し、公式記事の前年比と記事登録日を保持する。

`data_loader.py` は産業通商部の記事一覧から履歴を発見し、ICT 記事がある場合は ICT 系列を優先する。`yoy` または `release_date` が欠ける行を履歴から除外し、現在値と結合後、同一 `series_id`・`reference_period` は公表日の新しい行を残す。探索開始設定は2021年1月だが、**live確認済み**の取得結果は29か月、2023年6月〜2026年8月だった（発見95件、取得対象34件、警告5件）。これは fixture ではなく公式サイトへの1回の live 取得結果である。

`semiconductor_validation.py` の厳密検証は、派生値と部分期間を除外し、`release_date` が欠ける観測を除外して `available_at = release_date` とする。暫定検証だけが対象月からの推定利用可能日を使い、厳密検証とは混在させない。`semiconductor_view.py` と `app.py` も両者を分離表示する。関連 fixture / test は、未知の公表日と旬次値が厳密検証へ入らないこと、および parse・merge の既存挙動を固定している。

`SEMICONDUCTOR_DATA_COLUMNS` の役割は次のとおり。

| 列 | 役割 |
|---|---|
| `region` / `series_id` / `series_name` | 地域と系列の識別 |
| `reference_period` | 数値が表す対象期間 |
| `release_date` | 市場参加者が利用できた実公表日 |
| `value` / `unit` / `currency` | 水準、単位、通貨 |
| `yoy` / `yoy_is_derived` | 前年比と公式値・計算値の区別 |
| `frequency` | 月次・旬次等の頻度 |
| `source_name` / `source_url` | 出典と追跡先 |
| `publication_stage` | 速報、月次速報、現在 DB snapshot 等の公表段階 |
| `is_partial_period` / `period_start` / `period_end` | 部分期間と対象範囲 |
| `fetched_at` | 取得時点（公表日ではない） |
| `is_derived` | 水準値自体が計算値か |
| `data_vintage` | どの時点・版のデータか |

なお schema には上記以外に `working_days` もある。

## 3. `DT_092_115_2009_S023` の定義

| 項目 | 確認結果 | 状態 |
|---|---|---|
| 統計表名称 | `IT산업별/월별 수출 현황`（IT産業別・月別輸出現況） | 公式・live確認済み |
| 提供機関 | 科学技術情報通信部 | 公式・live確認済み |
| 対象統計 | `ICT수출입통계`（ICT輸出入統計） | 公式・live確認済み |
| 頻度 | 月次 | 公式・live確認済み |
| 収録期間 | 1996年1月〜2026年7月（調査時表示） | live確認済み |
| 半導体分類 | `情報通信放送機器 > 電子部品 > 半導体`。下位分類も存在 | 公式・live確認済み |
| 輸出分類 | 輸出現況表の金額 | 公式・live確認済み |
| 単位・通貨 | ドル、USD | 公式・live確認済み |
| 値の性質 | 月末までの通関速報値を基礎とし、翌年3月以降は年間確定値を提供 | 公式・live確認済み |
| ベース | ICT輸出統計の通関ベース | 公式・live確認済み |
| 季節調整 | 季節調整系列との表示はなく、名目ドル金額 | 公式画面上確認済み |
| 改定 | 速報から年間確定値への更新がある | 公式確認済み |
| 分類変更履歴 | 現行階層は確認できたが、時系列の分類版・接続表は確認できず | 未確認 |

[ITSTAT対象表](https://www.itstat.go.kr/statHtml/statHtml.do?orgId=006&tblId=DT_092_115_2009_S023) は、現行の産業通商部「ICT輸出入動向」と同じ ICT 輸出統計ファミリーに属し、半導体集計の定義は整合的である。一方、DB は後日更新・確定されるため、各記事に掲載された当時値と同じ **vintage** とはみなせない。一般の総貿易統計を名称だけで接続したものでもない。

## 4. API / download仕様

標準 API は `https://kosis.kr/openapi/Param/statisticsParameterData.do?method=getList`。`apiKey`、`orgId=006`、`tblId=DT_092_115_2009_S023`、分類軸 `objL1`〜、項目 `itmId`、周期 `prdSe=M` を指定し、`startPrdDe` / `endPrdDe` または `newEstPrdCnt` で期間を絞る。対象表の半導体に対応する正確な分類コードは、API key なしでは API response で確認できなかったため**未確認**である。

- 形式: 標準 API は JSON、SDMX。大容量 API は SDMX、XLS
- 上限: 1回40,000セル。仕様に pagination は記載されず、分類・期間分割が必要
- 認証: KOSIS 会員登録と利用申請後に発行される API key が必須。自動承認、1会員1キー、有効期間2年
- 費用: 公式案内上は無料。ただし登録とキー更新の運用が必要
- rate limit: 公式サービス案内は毎分200回、2026年の変更告知は毎分1,000回と記載が一致しない。本用途では保守的に毎分200回以下、かつ代表期間のみとする
- download: ITSTAT 表画面の公式 download 導線は live 確認済み。選択可能な個別形式は本診断では未確認。KOSIS 大容量 API の XLS は公式仕様で確認済み、CSV は未確認
- 最長期間: 表示上1996年1月から。API key なしのため全期間 API 取得は未実施

公式仕様: [統計資料 API](https://kosis.kr/openapi/devGuide/devGuide_0201List.do)、[統計説明資料 API](https://kosis.kr/openapi/devGuide/devGuide_060101List.do)、[大容量統計資料 API](https://kosis.kr/openapi/devGuide/devGuide_030101List.do)、[利用申請](https://kosis.kr/openapi/community/community_0401List.do)、[サービス案内](https://kosis.kr/openapi/introduce/introduce_01List.do)、[2026年 API 変更告知](https://kosis.kr/openapi/community/community_01Detail.do?p_id=49)。

## 5. 取得可能期間

**live確認済み**では1996年1月〜2026年7月を選択できる。したがって値の coverage は現行の2023年6月開始より大幅に長い。ただし、最古月からの API 応答と分類一貫性は key 未所持のため未確認であり、厳密検証で利用可能な最古月は確認できない。

## 6. 値・単位・分類

表の半導体 aggregate は USD の生値である。現行 schema の `million USD` に変換する場合は100万で除すればよいが、変換を明示する必要がある。表自体に公式前年比列は確認できなかった。画面の増減率機能や値から前年比を計算する場合、`yoy_is_derived=True` とし、記事掲載の公式前年比と区別する。

名目値・通関ベース・ICT分類であることは確認できた。品目分類の過去改訂と長期接続性は未確認であり、1996年以降を機械的に同一定義と扱わない。

## 7. 公表日の取得可否

**取得できない。** 厳密検証に必要なのは対象月 `reference_period`、実公表日 `release_date`、DB更新日時、改定日時のうち実公表日である。

- 表には対象月と表全体のデータ更新日（調査時 `2026-09-07`）があるが、各対象月の実公表日列はない
- 標準 API の `PRD_DE` は対象期間、`LST_CHN_DE` は最終変更日であり、当初公表日ではない
- metadata API は表のデータ更新日等を返すが、月ごとの過去公表日を返さない
- [KOSIS最近更新資料](https://kosis.kr/serviceInfo/newContrainDataList.do) は最新対象期間と DB 更新日、[国家統計公表日程](https://sso.kosis.kr/serviceInfo/statisPublicationList.do) は予定を示すが、全過去月の実公表日履歴ではない
- [ITSTATのお知らせ](https://www.itstat.go.kr/itstat/kor/board/BoardList.html?board_class=BOARD02) に公表予定案内はあるが、一般ルールや予定日を過去月の実公表日として採用できない

産業通商部の個別記事は登録日を確認できるため現行履歴には使えるが、KOSIS / ITSTAT 表だけから古い月の利用可能日を復元することはできない。推定日は作らない。

## 8. Vintage / 改定

公式注記から、月次値は速報、翌年3月以降は年間確定値となる。API / 表は現在の DB snapshot と最終変更日を提供するが、改定前の各 vintage、当初公表値、改定イベント列は確認できない。公式利用案内も情報が追加・変更・更新され得るとしている。

point-in-time 再現性は次の段階2にとどまる。

1. 各月の実公表日が分かる: **表/APIでは不可**
2. 現在の改定後値が分かる: **可**
3. 当時公表値まで再現できる: **不可**

`LST_CHN_DE` や `fetched_at` を `release_date` に転用しない。

## 9. 既存ICT系列との重複比較

公式表で代表月を直接選択し、産業通商部 ICT 記事と照合した。

| 対象月 | ITSTAT 半導体輸出（USD） | ICT記事（億USD） | ICT記事公式YoY | 結果 |
|---|---:|---:|---:|---|
| 2023-11 | 9,562,874,088 | 95.6 | +10.7% | `definition_compatible_but_value_differs` |
| 2023-12 | 11,066,415,208 | 110.7 | +19.3% | `definition_compatible_but_value_differs` |
| 2024-11 | 12,458,119,886 | 124.6 | +30.3% | `definition_compatible_but_value_differs` |

ITSTAT の精密値を億ドルへ丸めると記事値に一致するため、分類・単位は整合的である。ただし exact vintage の一致を証明するものではなく、差を勝手に補正しない。記事出典は[2023年12月 ICT輸出入動向](https://www.motir.go.kr/kor/article/ATCL3f49a5a8c/168482/view)（2024-01-16登録）と[2024年11月 ICT輸出入動向](https://www.motir.go.kr/kor/article/ATCL3f49a5a8c/169932/view)（2024-12-16登録）。

## 10. 既存schemaへの適合性

列構造には格納可能だが、既存系列へ無理に merge してはならない。参考用途で採用する場合の候補は次のとおり。

- `region = Korea`
- `series_id = korea_semiconductor_exports_monthly_kosis`
- `frequency = monthly`, `is_partial_period = False`
- `value` は換算根拠を明示した `million USD`、`currency = USD`
- `release_date = NaT`
- `publication_stage = current_database_snapshot`
- `data_vintage` は取得日時を含む current snapshot と明示
- `yoy` を計算する場合は `yoy_is_derived = True`

同じ統計ファミリーでも記事当時値と現在 DB 値は vintage が異なり得るため、`korea_semiconductor_exports_monthly` の同一対象月を上書きしない。schema 変更は不要であり、本診断では integration しない。

## 11. Historical Validationへの適合性

| 用途 | 判定 | 条件 |
|---|---|---|
| A. 現在表示・長期チャート | CONDITIONAL GO | 別系列、current snapshot、分類変更未確認、厳密検証対象外を明示 |
| B. 参考用の過去分析 | CONDITIONAL GO | 改定後値であることを明示し、推定公表日を使わない |
| C. 厳密 Historical Validation | **NO-GO** | 月別実公表日と当時 vintage を復元できず、未来情報混入を防げない |

C の GO 条件のうち、月次半導体輸出の定義と reference period は確認できた。しかし実公表日の月別履歴、当時値、改定履歴、長期分類接続が不足する。

## 12. 解消する問題

- 候補表が一般貿易表ではなく、科学技術情報通信部の通関ベース ICT 輸出統計であることを特定した
- 半導体 aggregate、USD、月次、1996年1月開始を確認した
- 現行 ICT 記事系列との代表月の定義・丸め整合を確認した
- KOSIS key の要否、API上限、期間指定、metadata と値 API の役割を整理した
- KOSIS の更新日を実公表日として利用できないことを確定した

## 13. 残る問題

- 過去各月の実公表日と当初値を対応付ける公式 archive が見つからない
- revision / vintage history を取得できない
- 長期の分類変更履歴と接続表を確認できない
- API key なしのため半導体分類コードと全期間 API 応答は未確認。ただし、この確認だけでは厳密検証の構造的欠落は解消しない

## 14. 継続費用・運用負荷

API利用料は無料だが、会員登録、2年ごとの key 管理、分類コード変更・表更新の監視、取得量制御、current snapshot の保存が必要となる。A/B用途の loader は小〜中規模で実装できるが、厳密検証には別途、公式記事 archive と vintage の収集・検証が必要で、KOSIS loader だけでは完成しない。secret は repository に保存しない。

## 15. GO / CONDITIONAL GO / HOLD / NO-GO

最終判定は **NO-GO**。対象表は長期値を提供するが、各 reference month の実公表日と当時公表値を再現できない。これは API key の取得だけで解ける小さな未確認事項ではなく、公式 API schema と表の性質に由来する。したがって改定後値を過去時点へ置き、Historical Validation を延長してはならない。

## 16. 次PRの推奨範囲

厳密検証延長を目的とする次PRでは KOSIS 本番 loader を追加しない。先に、2023年6月より前の科学技術情報通信部／産業通商部 ICT 月次報道資料について、公式記事登録日と記事掲載当時値が対で残る archive があるかを別候補として確認する。

A/B用途に明確な需要が生じた場合だけ、別PRで `korea_semiconductor_exports_monthly_kosis` を追加し、`release_date=NaT`、current snapshot、派生前年比、厳密検証除外を固定する。そのPRでも既存 ICT 系列を置換しない。

## 17. 再開条件または打ち切り条件

厳密検証向けに再開する条件は、公式機関から次のいずれかが確認できること。

- 各対象月の実公表日と当初公表値を対応付けた archive
- 取得可能な revision / vintage 履歴
- 改定がない期間についての明示的な公式説明と、月別実公表日履歴

これらが確認できない限り、`DT_092_115_2009_S023` を厳密 Historical Validation に使う経路は打ち切る。同じ表に対する API key 取得や反復 probe だけでは再開しない。
