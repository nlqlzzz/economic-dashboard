# 台湾輸出受注 archive loader

## 役割分担

- Current snapshot: 既存 `load_taiwan_semiconductor_orders()`。Open Data CSVの最新改定値を現在表示・長期チャートへ使う。`release_date` は不明、YoYはアプリ計算値。
- As-published archive: 新規 `load_taiwan_semiconductor_orders_archive()`。公式「外銷訂單統計速報」の当時値・公式YoY・実公表日をpoint-in-time用途向けに返す。

両者は同じ `series_id` と対象月を持ち得るが、自動merge、最新値優先、欠損補完を行わない。アプリ本体とHistorical Validationにはまだ接続していない。

## loader / parser仕様

`taiwan_export_orders_archive.py` が次を担当する。

1. 公式archive HTMLに実在するリンクだけを発見する。数値IDを生成しない。
2. 記事の対象月、表示日時、公式添付URLを抽出する。
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

一覧取得と各記事・添付は既存のtimeout、最大2回retry、User-Agentを再利用する。取得は逐次で各月間に短い待機を置き、Streamlit cacheは24時間。月ごとの失敗は `failed_months` に対象月、記事URL、例外種別、詳細を残す。

DataFrame attrsには、expected/discovered/loaded month数、discovery欠損月、添付SHA-256、取得日時、試行回数を保持する。hash列は共通schemaへ追加しない。原文ファイルもrepositoryへ保存しない。

## fixture確認

- 2025-01: 情報通信 12,060、電子 17,710 million USD、公式YoY -13.3% / +1.5%、2025-02-20 16:00
- 2023-06: 12,300 / 14,620 million USD、-27.4% / -22.0%、2023-07-20 16:00
- 2021-01: 15,090 / 16,930 million USD、+55.6% / +64.3%、2021-02-24（日付のみ）

2025年1月はcurrent CSVの12,445 / 18,252へ置き換わらないことを固定した。release date不明、商品欠損、2020年以前、schema不一致も停止する。

## 限定live確認とcoverage

2026-09-19、公式archive一覧を直接確認し、2021年1月から2026年7月まで67か月が連続掲載され、一覧上の欠損月候補は0件だった。

同日のloader経路による代表3 PDF（2025-01、2023-06、2021-01）取得は、公式サイトがHTTP 429 HTMLを返したため **Environment Blocked**。PDFではない応答を値として扱わず停止した。公式ページ内容自体はPR84で確認済みだが、PR85の実装によるlive parse成功とは区別する。

## 残る制約とPR86

- 実環境からのHTTP 429が解消した状態で、代表3か月のloader live parseを再確認する必要がある。
- 実archive HTMLのdiscovery parserも同じ理由でlive実行未確認。
- 2020年以前、旧URL形式、OCRは対象外。
- 公式URLにversion保証はないため、SHA-256の変化を診断する。

fixtureとcoverage設計は完成したが、PR86のstrict Historical Validation接続は、代表3か月のloader live成功と2021年以降のdiscovery件数再確認後に進める。
