# 台湾輸出受注 archive loader

## 役割分担

- Current snapshot: 既存 `load_taiwan_semiconductor_orders()`。Open Data CSVの最新改定値を現在表示・長期チャートへ使う。`release_date` は不明、YoYはアプリ計算値。
- As-published archive: 新規 `load_taiwan_semiconductor_orders_archive()`。公式「外銷訂單統計速報」の当時値・公式YoY・実公表日をpoint-in-time用途向けに返す。

両者は同じ `series_id` と対象月を持ち得るが、自動merge、最新値優先、欠損補完を行わない。通常表示と暫定検証はcurrent snapshot、厳密Historical Validationだけはrepository内のas-published snapshotを読む。

## loader / parser仕様

`taiwan_export_orders_archive.py` が次を担当する。

1. 公式速報archive HTMLに実在する月次リンクだけを発見する。数値IDを生成しない。
2. 公式news archiveを対象月の完全な記事名で検索し、検索結果に明示された記事URLから表示日時と公式添付URLを抽出する。
3. 2021年以降で文章構造が安定した「新聞稿」PDFを優先し、通常のテキスト抽出で2商品を読む。OCRは行わない。
4. XLSX/ODSは記事上で検出できるが、全表workbookのsheet配置が年により異なるためfallbackとする。構造不一致は失敗として扱う。
5. 億米ドルを百万米ドルへ100倍し、記事の精度を超える値を作らない。

既定開始月は `2021-01`。2020年以前を指定すると停止する。終了月は任意で、通常起動からは呼ばれない。

## 正規化

既存 `SEMICONDUCTOR_DATA_COLUMNS` を変更せず、2系列だけを返す。

- `publication_stage=official_monthly_release`
- `data_vintage=as_published_monthly_release`
- `is_derived=False`
- `yoy_is_derived=False`
- `value`: 当時公表値（million USD）
- `yoy`: 当時資料の公式前年比
- `release_date`: 記事表示日時またはPDF DATE。日付しかなければ00:00として日付精度を保持し、時刻を推測しない

公表日、商品別金額、公式YoYのいずれかが欠ければ、その月を採用しない。current CSVへのfallbackはない。

## failure handling / cache / rate control

台湾archive専用clientはlisting、検索form、検索POST、記事、添付を含む**全HTTP request間で最低3秒**空ける。HTTP 429だけを最大4試行（初回＋再試行3回）とし、`Retry-After` があれば尊重し、なければ5秒、15秒、30秒のbounded backoffを使う。403等は無条件retryしない。timeoutは30秒、User-Agentを明示し、Streamlit cacheは24時間。月ごとの失敗は `failed_months` に対象月、記事URL、例外種別、詳細を残す。

2021-01は公式news historyのローリング範囲外になったため、PR84で公式確認済みの公表日 `2021-02-24` だけをlegacy manifestとして保持する。値・YoY・添付URL・hashは現在表示CSVではなく、速報archive一覧に現存する当時PDFから取得する。一般的な「翌月20日前後」からは推定しない。

DataFrame attrsには、expected/discovered/loaded month数、discovery欠損月、添付SHA-256、取得日時、試行回数を保持する。hash列は共通schemaへ追加しない。原文ファイルもrepositoryへ保存しない。

## fixture確認

- 2025-01: 情報通信 12,060、電子 17,710 million USD、公式YoY -13.3% / +1.5%、2025-02-20 16:00
- 2023-06: 12,300 / 14,620 million USD、-27.4% / -22.0%、2023-07-20 16:00
- 2021-01: 15,090 / 16,930 million USD、+55.6% / +64.3%、2021-02-24（日付のみ）

2025年1月はcurrent CSVの12,445 / 18,252へ置き換わらないことを固定した。release date不明、商品欠損、2020年以前、schema不一致も停止する。

## 限定live確認とcoverage

2026-09-19、公式archive一覧を直接確認し、2021年1月から2026年7月まで67か月が連続掲載され、一覧上の欠損月候補は0件だった。

同日、GitHub Actionsの手動live診断相当環境で、代表3か月を実loaderにより取得・parseした。全3か月成功、失敗月0。診断対象範囲2021-01～2025-01は expected 49 / discovered 49 / missing 0だった（67か月という全一覧coverageとは範囲が異なる）。通常CIからはnetwork依存を除き、手動workflowだけを残す。

| 対象月 | 情報通信 / 電子 (million USD) | 公式YoY | release_date | 添付SHA-256 |
|---|---:|---:|---|---|
| 2021-01 | 15,090 / 16,930 | +55.6% / +64.3% | 2021-02-24（日付のみ） | `99bc4c8de0ed20ba99a903b25fa561628dffdaa118daa3cc85026d400903330b` |
| 2023-06 | 12,300 / 14,620 | -27.4% / -22.0% | 2023-07-20 16:00 | `965946ebdb50d205e3f8c5f1bbb06d352a99d5c170322fdea23210ae2cebd33c` |
| 2025-01 | 12,060 / 17,710 | -13.3% / +1.5% | 2025-02-20 16:00 | `66544dbf3ce064ce5ab46efc47e2a487946c1b483e27c957b3d7441ab0e07f27` |

2025-01はcurrent CSVの12,445 / 18,252へ置換されず、当時値の差を維持した。

## Safe startと残る制約

- 2021-01～2021-08をPR86で一度だけ再確認した。2021-01は確認済みlegacy manifestで取得できるが、2021-02～07はarchive上に公式PDFが残る一方、公式news記事と資料内の正式公表日を確認できない。
- 2021-08は公式記事（2021-09-24 16:00）と添付が残るが、新聞稿PDFの多段組みテキスト抽出順が崩れ、2系列を安全に機械抽出できない。current CSVや一般公表ルールでは補完しない。
- 単発の2021-01と断続的にparseできる月を穴越しに使わず、全月が連続して安全なstrict開始月を **2022-08** とした。2021-09～2022-07には多段組みPDFを安全に抽出できない月が残る。除外月はmanifestへ推定日を追加していない。
- 2020年以前、旧URL形式、OCRは対象外。公式URLにversion保証はないため、SHA-256の変化を診断する。
- 公式一覧が2026-02～07として示す直接添付は、添付本文の対象月が2025年同月で一致しなかったため除外した。引数の対象月で本文を上書きしない検証と、公表日が対象月末より後である検証を追加した。最新の安全な対象月は2026-01（公表日2026-03-04 16:00）。

## Snapshotと更新運用

通常アプリは `data/taiwan_export_orders_archive.csv` を `load_taiwan_semiconductor_orders_archive_snapshot()` でnetworkなしに読む。`data/taiwan_export_orders_archive_manifest.json` は生成日時、安全開始月、最新月、月数、欠損月、元archive URL、月別attachment SHA-256を保持する。共通schemaや原文PDFは増やさない。

snapshotは最古月から最新月までの全暦月が連続していることを必須とする。更新後に1か月でも欠損があれば保存せず、`missing_months` はsnapshotから実計算する。欠損をcurrent CSVで補完しない。

手動更新は `scripts/update_taiwan_orders_archive.py --end YYYY-MM` を使う。既定では未取得月だけを逐次取得し、既存月は上書きしない。既存月を `--refresh` した結果、release date、value、公式YoY、source URL、attachment hashのいずれかが変われば差分を表示して停止し、`--accept-changes` の明示なしにはpoint-in-time snapshotを変更しない。通常CIはlive networkへ接続しない。

## Historical Validation接続

- strict: 台湾archive snapshot + 韓国の実公表日付き公式月次履歴
- provisional: 台湾current Open Data CSV + 韓国の現行データ
- strict台湾行は `official_monthly_release`、`as_published_monthly_release`、`yoy_is_derived=False`、実公表日、2系列が揃う月だけを採用する。不完全月をcurrent CSVで埋めない。
- 台湾と韓国は別々の公表イベントとして保持する。韓国履歴が始まる2023-06より前は韓国をunknownとし、台湾＋韓国複合条件を成立させない。62日staleルール、翌利用可能終値、未満了・価格品質の既存ルールを維持する。
- current表示、36か月推移、Global Semiconductor Pulse、Price vs Fundamentalsは従来どおりcurrent CSVを使う。2025-01のarchive/current差は正常であり、自動一致させない。

## Snapshot coverageとlive validation

commit済みsnapshotは2022-08～2026-01の42か月、2系列×42か月の84行、欠損0。最古公表日は2022-09-20 16:00、最新公表日は2026-03-04 16:00。2025-01は情報通信12,060 / 電子17,710 million USD、公式YoY -13.3% / +1.5%を維持し、current CSVへ置換していない。

2026-09-19にsnapshot、韓国公式月次履歴、Yahoo Financeの現行5資産でlive診断した。台湾2系列の相関サンプル数はSOX・東京エレクトロン・アドバンテスト・ディスコで各期間42、上場期間の短いキオクシアで15。`Taiwan Improving` の条件成立後リターンは前4資産で各期間12、キオクシアで5。台湾＋韓国複合条件は前4資産で8、キオクシアで4に留まり、低標本警告が残る。

相関は期間・資産で一貫しない。SOXは電子で +0.00 / +0.29 / +0.41、情報通信で +0.05 / +0.34 / +0.46（1 / 3 / 6か月）だが、東京エレクトロンとアドバンテストは概ね弱く、ディスコは3 / 6か月で負、キオクシアは短い履歴しかない。条件付きリターンは正の標本が多いものの、重複期間、少数標本、近年の強い上昇相場を含むため、先行指標・予測モデル・売買シグナルとは結論づけない。Cycle Scoreは保留を維持する。
