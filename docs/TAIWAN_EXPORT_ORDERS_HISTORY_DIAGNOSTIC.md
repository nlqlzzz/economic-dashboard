# 台湾輸出受注 point-in-time 履歴診断

## 1. 調査目的

台湾経済部統計処の「外銷訂單」について、過去各月の実公表日と当時公表値を公式経路から取得し、厳密 Historical Validation に安全に使えるかを限定診断した。本番 loader、UI、Historical Validation は変更していない。

確認状態は次のように表記する。

- **公式確認済み**: 台湾経済部の説明、記事、添付資料で確認した事項
- **live確認済み**: 2026-09-19 に公式ページまたは公式 Open Data CSV へ実アクセスして確認した事項
- **未確認**: 今回の少数標本では確認できず、推測しない事項

## 2. 現行データフロー

`data_loader.py` の `TAIWAN_EXPORT_ORDER_URLS` は、台湾経済部の公式 CSV から `電子產品` と `資訊與通信產品` を個別取得し、`global_semiconductor_demand.py` の `parse_taiwan_export_orders_csv` へ渡す。parser は `外銷訂單金額_美元` を選び、民国年月を `reference_period` に、金額を `value` に変換する。

現行値は `unit=million USD`、`frequency=monthly`、`publication_stage=official_monthly`、`release_date=NaT`、`data_vintage=None`、`yoy_is_derived=True` である。YoY は同じ現行 CSV の12か月差から計算する。`semiconductor_validation.py` の strict mode は `release_date` 欠損行を除外するため、台湾系列は厳密検証に入らない。provisional mode だけが対象月の2か月後を仮の利用可能日とするが、strict と混在しない。

関連テストは、台湾の公表日を推測しないこと、YoY が派生値であること、CSV schema 変更を拒否すること、strict mode から台湾が除外されることを固定している。

## 3. 台湾輸出受注の公式定義

**公式確認済み**。提供機関は台湾経済部統計処、統計名は「外銷訂單統計」、頻度は月次である。[調査計畫](https://www.moea.gov.tw/Mns/dos/content/Content.aspx?menu_id=6806)と[調査概要](https://www.moea.gov.tw/Mns/dos/content/Content.aspx?menu_id=6805)によると、海外から台湾企業が受けた注文を約2,800社の輸出業者から調査し、商品別・受注地域別に集計する。電話、書面、面談等の受注を含む。

これは通関輸出実績ではない。業者が受注後に国内生産する分と海外生産へ回す分を含み、海外生産分は台湾税関を通らない場合がある。2021年1月の[公式ニュースリリース](https://www.moea.gov.tw/MNS/populace/news/wHandNews_File.ashx?file_id=84972)も同じ定義を明記し、同月の海外生産比率を52.9%としている。

対象は月全体、単位は米ドル（記事は億米ドル、Open Data は百万米ドル）、名目受注額である。記事は「統計速報」として公表される。季節調整値は総額の前月比較に掲載されるが、本診断対象の商品別金額と前年比は原数値である。後日の訂正・改定規則、電子產品／資訊與通信產品の全期間にわたる分類変更履歴は**未確認**。旧資料には、2017年4月から「精密儀器」を「光學器材」へ改称した注記があるが、対象2分類を変更した根拠にはならない。

## 4. 現行 Open Data CSV

**live確認済み（2026-09-19）**。2ファイルはいずれも `統計項目 / 貨品別 / 資料期(民國年) / 統計值(金額) / 計量單位` の5列で、各511行、1984年1月から2026年7月までを収録していた。認証・API key は不要だった。

CSV は長期の最新系列を返すが、各月の実公表日、記事ID、改定番号、当時値を識別する vintage timestamp を持たない。したがって CSV 単独では Level 2（現在値＋別経路の公表日）までであり、厳密 point-in-time 用の Level 3 にはならない。

## 5. 過去公表記事 archive

**公式確認済み・live確認済み**。経済部統計処の[外銷訂單統計速報 archive](https://www.moea.gov.tw/Mns/dos/content/ContentLink.aspx?menu_id=9423)は、少なくとも2013年1月から現在まで月別項目を掲載している。現行ニュース記事は `News.aspx?...&news_id=<id>`、添付は `wHandNews_File.ashx?file_id=<id>`、旧出版物は `wHandPublish_File.ashx?pub_id=<id>` または `wHandMenuFile.ashx?file_id=<id>` である。数値IDは単調なURL規則ではなく、一覧／記事HTMLから解決する必要がある。

代表月の確認結果は次のとおり。金額は当時資料の億米ドル。`情報通信 / 電子` の順で示す。

| 対象月 | 公式記事・資料 | 実公表日時 | 当時値 | 公式YoY | 添付 | 確認結果 |
|---|---|---:|---:|---:|---|---|
| 2025-01 | [記事](https://www.moea.gov.tw/MNS/populace/news/News.aspx?kind=1&menu_id=40&news_id=118607) / [当時PDF](https://www.moea.gov.tw/MNS/populace/news/wHandNews_File.ashx?file_id=123566) | 2025-02-20 16:00 | 120.6 / 177.1 | -13.3% / +1.5% | PDF、ODS、XLSX、個別表 | Level 3。現行CSVとは改定差あり |
| 2024-01 | [記事](https://www.moea.gov.tw/MNS/Populace/news/News.aspx?kind=1&menu_id=40&news_id=113951) | 2024-02-27 16:00 | 添付の商品別表に保存 | 公式商品別表に保存 | PDF、ODS、XLSX、個別表 | 記事日時と当時添付の存在を確認。値の転記照合は未実施 |
| 2023-06 | [記事](https://www.moea.gov.tw/MNS/populace/news/News.aspx?kind=1&menu_id=40&news_id=110612) / [当時PDF](https://www.moea.gov.tw/MNS/populace/news/wHandNews_File.ashx?file_id=119274) | 2023-07-20 16:00 | 123.0 / 146.2 | -27.4% / -22.0% | PDF、ODS、XLSX、個別表 | Level 3。現行CSVと丸め後一致 |
| 2021-01 | [当時PDF](https://www.moea.gov.tw/MNS/populace/news/wHandNews_File.ashx?file_id=84972) | 2021-02-24（日付のみ） | 150.9 / 169.3 | +55.6% / +64.3% | PDF・速報archive | Level 3。現行CSVと丸め後一致 |
| 2019-01 | [速報archive](https://www.moea.gov.tw/Mns/dos/content/ContentLink.aspx?menu_id=9423) / [公式表](https://www.moea.gov.tw/Mns/DOS/content/wHandMenuFile.ashx?file_id=20003) | 個別公表日は今回未確認 | 116.8 / 104.3 | -5.8% / -2.0% | 旧電子書・表 | 当時値は確認、公表日は未確認のため当月は strict 利用不可 |
| 2017-01 | [当時PDF](https://www.moea.gov.tw/Mns/DOS/Publish/wHandPublish_File.ashx?pub_id=1324) | 2017-02-20（日付のみ） | 105.5 / 94.6 | +6.7% / +1.4% | 旧PDF・統計表 | Level 3。現行CSVと丸め後一致 |

現行記事はページ上に時刻まで表示し、当時PDFの `DATE` と一致する。旧PDFは日付のみの場合がある。時刻がない観測は時刻を推測せず、現行の保守的ルールどおり翌営業日以降の終値から評価できる。

## 6. 実公表日の取得可否

**GO**。実公表日は、現行ニュース記事の表示日時または当時PDFの `DATE` から月別に取得できる。次回公表予定の一般規則（通常は翌月20～23日）や現在CSVの更新日を代用する必要はない。

2021年1月以降はニュース記事／添付PDFの代表標本で取得できた。旧出版物も2017年1月で取得できたが、2019年1月の個別公表日は今回の限定調査では未確認である。したがって次PRの連続自動取得範囲はまず2021年1月以降とし、それ以前は月別に公表日を検証できた観測だけを追加するのが安全である。

## 7. 当時値 / Vintage

公式記事本文またはその時点の添付PDFに商品別金額と公式前年比が残るため、Level 3（当時公表値＋実公表日）を構築できる。現在CSVを過去記事の代用にしない。

2025年1月は明確な改定例である。当時PDFは情報通信12,060百万米ドル、電子17,710百万米ドルだったが、2026-09-19時点のCSVはそれぞれ12,445、18,252百万米ドルだった。差は丸めでは説明できない。改定理由、改定日、revision history API は**未確認**であり、推測で補正しない。

記事や添付が後日上書きされないことを保証するversion ID／hashは提供されていない。実装時は取得時刻、source URL、記事ID／file ID、原文金額、公式YoYを保存し、同一URLの内容変化を検知できるhashを診断ログへ残すべきである。

## 8. 公式YoY

**公式確認済み**。当時PDFは商品別の前年同月比を掲載する。将来実装では、archive 由来の `yoy` は公式値として `yoy_is_derived=False`、現行CSVから再計算した値は `yoy_is_derived=True` のまま区別する。

記事値は0.1億米ドル、公式YoYは0.1%に丸められる。現行CSVの百万米ドル値から計算したYoYと小数点以下が一致しない場合があるため、公式YoYを派生YoYで上書きしない。

## 9. 現行CSVとの重複比較

| 対象月 | 現行CSV 情報通信 / 電子（百万USD） | 当時資料を百万USD換算 | 判定 |
|---|---:|---:|---|
| 2025-01 | 12,445 / 18,252 | 12,060 / 17,710 | `revised_value` |
| 2023-06 | 12,297 / 14,620 | 12,300 / 14,620 | `rounded_match` |
| 2021-01 | 15,093 / 16,930 | 15,090 / 16,930 | `rounded_match` |
| 2019-01 | 11,680 / 10,434 | 11,680 / 10,430 | `rounded_match`（公表日未確認） |
| 2017-01 | 10,549 / 9,463 | 10,550 / 9,460 | `rounded_match` |

同じ「外銷訂單統計」の同じ商品分類・対象月で接続可能だが、2025年の差により、現行CSVが当時値の不変な複製ではないことが実証された。

## 10. 自動取得可能性

- 一覧: 公式 `ContentLink.aspx?menu_id=9423`。月別archive項目を持つ。
- 記事: `News.aspx`。タイトル、表示日時、添付リンクをHTMLから取得可能。
- 添付: PDFに加え、近年はODS/XLSXと個別表がある。認証・API key不要。
- pagination／検索: archive一覧から辿れるが、公開API仕様とrate limitは**未確認**。
- bot対策: 少数の通常取得では障害なし。大量クロールは未実施。
- schema安定性: 近年記事と旧出版物でURL・添付形式が異なる。現行CSV parserをそのまま流用はできないが、PDF本文の商品表は規則的で、近年はXLSXもある。

実装量は**中**。2021年以降に限定すれば、一覧／記事HTML、PDFまたはXLSX、2分類、日時、公式YoYを扱う専用parserで足りる。OCRや専用ブラウザ操作は不要。2013～2020年の旧出版物まで一括対応するとURL系統と添付形式の分岐が増えるため、別段階にする。

## 11. 既存schemaへの適合性

既存 `SEMICONDUCTOR_DATA_COLUMNS` に自然に格納でき、schema変更は不要。

- `region=Taiwan`
- 既存の2つの `series_id` を維持
- `reference_period` は記事タイトル／資料対象月
- `release_date` は公式記事日時またはPDF `DATE`（時刻なしは日付のみ）
- `value` は当時記事値を百万米ドルへ換算
- `unit=million USD`、`currency=USD`、`frequency=monthly`
- `publication_stage=official_monthly_release`
- `data_vintage=as_published_monthly_release` 等、現行CSV最新値と区別
- `yoy` は記事の公式値、`yoy_is_derived=False`

同じ系列IDへ統合してよいが、同じ対象月では archive の当時値と current CSV の最新値を黙ってmergeしない。point-in-time validation用選択では archive vintage を優先し、現在表示は現行CSVを維持する。

## 12. Historical Validation適合性

| 用途 | 判定 | 理由 |
|---|---|---|
| A. 現在表示 | GO（現状維持） | 現行CSVが最新長期値を提供する |
| B. 長期チャート | GO（現状維持） | 1984年1月以降を表示可能。ただしvintageではない |
| C. 参考Historical Analysis | GO | 現行CSVでも可能。改定後値であることを明示する |
| D. 厳密Historical Validation | **GO（2021年1月以降を初期範囲）** | 月別の実公表日、当時値、公式YoYを公式記事から復元できる |

確認できた単月としては2017年1月までLevel 3が成立し、archive一覧は2013年1月まで遡る。ただし今回の限定診断で連続自動取得を確認した範囲は2021年1月以降であり、厳密検証の最古月を2013年1月と断定しない。

## 13. 解消する問題

- 台湾系列の `release_date=NaT` による strict validation 除外を、公式日付で解消できる。
- 現行CSVの改定後値と当時公表値を分離できる。
- 公式YoYとアプリ計算YoYを分離できる。
- 韓国の現行2023年6月開始より前へ、台湾単独条件の厳密検証標本を増やせる。

## 14. 残る問題

- 2020年以前の全月について、旧URL系統の公表日・添付形式を連続検証していない。
- 改定理由、改定日、revision history APIは未確認。
- 添付の不変性を保証する公式version/hashはない。
- 商品分類の全期間変更履歴は未確認。
- 台湾単独の履歴が伸びても、台湾＋韓国の複合条件は韓国の開始月より前へ伸びない。

## 15. 継続費用・保守負荷

利用料、API key、契約費は不要。月1回の新記事取得、parser fixture更新、URL／添付schema変更の監視が必要で、継続費用は低、保守負荷は小～中。過去一括backfillは2021年以降約70か月規模だが、実装時は低速・キャッシュ付きで一度だけ行い、repoへ大量の原文を直書きしない。

## 16. GO / CONDITIONAL GO / HOLD / NO-GO

**GO（初期範囲を2021年1月以降に限定）**。

公式archiveに実公表日、当時の商品別金額、公式YoYが対で残り、現行CSVとの差も識別できる。認証、OCR、ブラウザ自動操作は不要で、専用loaderの実装・保守負荷も過大ではない。2020年以前は同時に広げず、月別の公表日と当時値が両方確認できた観測だけを後続追加する。

## 17. 次PRの推奨範囲

1. 2021年1月以降だけを対象に、公式archive一覧→記事→添付を取得する独立loader/parserを追加する。
2. 代表fixtureで記事日時、PDF/XLSXの商品別当時値、公式YoY、schema変更を検証する。
3. `release_date` 不明時は行をstrictへ入れず、予定日を推測しない。
4. current CSV と archive vintage を別ソースとして保持し、同月の無条件上書きを禁止する。
5. archive hashまたは抽出値の差分を検知し、再現性を残す。
6. loader単体のlive確認後にだけ Historical Validation へ接続する。UI変更、Cycle Score、AIスコアは別PRとする。

## 18. 再開条件または打ち切り条件

2020年以前への拡張は、旧archiveの連続月について公表日・当時値・公式YoYを自動抽出でき、分類接続を説明できる場合だけ再開する。旧資料の欠落、日付不明、OCR必須、または保守負荷が標本増加に見合わない場合は2021年1月を固定始点とし、同じ経路の調査を反復しない。
