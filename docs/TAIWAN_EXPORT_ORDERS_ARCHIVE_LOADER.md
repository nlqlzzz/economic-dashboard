# 台湾輸出受注 archive loader

## 役割分担

- Current snapshot: 既存 `load_taiwan_semiconductor_orders()`。Open Data CSVの最新改定値を現在表示・長期チャートへ使う。`release_date` は不明、YoYはアプリ計算値。
- As-published archive: 新規 `load_taiwan_semiconductor_orders_archive()`。公式「外銷訂單統計速報」の当時値・公式YoY・実公表日をpoint-in-time用途向けに返す。

両者は同じ `series_id` と対象月を持ち得るが、自動merge、最新値優先、欠損補完を行わない。アプリ本体とHistorical Validationにはまだ接続していない。

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

## 残る制約とPR86

- 2021-02～2021-08もnews historyのローリング範囲外になり得るため、PR86の全期間接続前に月別の公式公表日を確認済みmanifestへ追加するか、利用開始月を連続取得可能な範囲へ制限する必要がある。
- 2020年以前、旧URL形式、OCRは対象外。
- 公式URLにversion保証はないため、SHA-256の変化を診断する。

代表3か月のlive完了条件は満たしたためPR86へ進める。ただしstrict Historical Validationへ投入する連続月は、上記legacy公表日の残課題を解消してから確定する。
