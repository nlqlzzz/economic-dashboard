# Japan Core 20 Corporate Events Phase 1 診断

調査日: 2026-09-12  
対象: Japan Core 20  
結論: **No-Go（追加の有料契約なしでは実装しない）**

## Corporate Events Lite（2026-09-12追記）

結論: **No-Go（現行実行環境で `JQUANTS_API_KEY` を確認できず、Core20実データ診断を実施できない）**。

TDnet本格版のNo-Go判断は維持する。一方、公式 `jquants-api-client` のV2 `ClientV2` には以下の決算関連メソッドが存在する。

- `get_fin_summary`: Financial Summary。実績の `DiscDate`、対象期、通期会社予想を取得する候補。
- `get_fin_earnings_date`: 銘柄・日付・予定日で決算発表日を取得する候補。
- `get_eq_earnings_cal`: 決算発表予定カレンダーを取得する候補。
- `get_fin_dividend`: 配当情報の候補。ただし今回未検証のためLiteには含めない。

既存のFinancial Summary正規化では、`DiscDate`、Fiscal Year / Quarter、実績とForecastを安全に分離できる。実データで同一企業・同一Fiscal Year・同一metric・同一通貨／単位の複数Forecast開示が確認できた場合だけ、`forecast_update` として前回値・最新値を並べられる。値の増減はmetric単位の `Upward / Downward / Unchanged` とし、正式な「業績予想修正」とは呼ばない。

ただし、この実行環境ではキー未設定のため、Summary履歴、Forecast更新、決算予定日をCore20 20社で取得してcoverageを測定できなかった。キーなしでEndpointを繰り返し呼ぶこと、公開TDnetの代替取得、推測によるイベント表示は行わない。

### 契約・キーが利用可能な環境でのGo条件

1. `get_fin_summary` でCore20の決算発表・Forecast履歴を実測し、部分失敗を分離する。
2. `get_fin_earnings_date` または `get_eq_earnings_cal` の20社coverage、予定日範囲、rate limitを実測する。
3. 決算発表・Forecast Update・次回決算予定を共通schemaへ正規化し、直近3〜5件だけをStock Detailへ表示する。
4. UIには「J-Quantsで取得可能な決算関連イベントのみ。M&A・自己株式取得・大型受注等は含まれない」と明記する。

この条件を満たした場合のLite schemaは、既存schemaの `event_type` を `earnings_release` / `forecast_update` / `earnings_schedule` に限定し、`event_id` はticker・type・開示日・対象期から安定生成する。`document_url`、TDnet item code、revision / deletionは `None` とする。

## 結論

Corporate Events v1の第一候補は、JPX総研のJ-Quants APIに追加された「適時開示書類（TDnet）アドオン」である。日中配信、API / CSV、一律5年履歴を提供するが、Lightプラン以上に加えて月額11,000円（税込）のアドオンが必要である。

現在のリポジトリはJ-Quants API V2 Financial Summary用の `JQUANTS_API_KEY` だけを保持し、TDnetアドオンの契約有無を保存・推定しない。現行キーにこの権限があるとは確認できないため、認証エラーを前提にした実装や公開TDnet画面のスクレイピングは行わない。

## 調査した公式経路

| 経路 | 取得範囲 | 現実性 | 判定 |
| --- | --- | --- | --- |
| J-Quants API TDnetアドオン | 当日の日中配信、過去5年、API / CSV | 個人利用・Light以上・月額11,000円（税込） | 将来の第一候補 |
| JPX TDnet API | 全上場会社の適時開示、過去5年、Index / Document API | 法人向け有料サービス。基本料月額7万円（税抜）＋従量 | 個人アプリには不採用 |
| J-Quants Pro / TDnet on Snowflake | TDnet、文書、5年履歴等 | 別契約・Snowflake等を前提 | 今回は不採用 |
| 公開TDnet閲覧画面 | 閲覧用 | 自動取得の正式経路ではない | スクレイピング禁止 |

出所: [JPX: J-Quants TDnetアドオン開始](https://www.jpx.co.jp/corporate/news/news-releases/6020/20260518-01.html)、[JPX: TDnet API](https://www.jpx.co.jp/markets/paid-info-listing/tdnet/02.html)、[TDnet API仕様](https://www.jpx.co.jp/english/markets/paid-info-listing/tdnet/p1j4l40000000q03-att/tdnetapi_specificationsE.pdf)。価格・利用条件は契約前に公式サイトで再確認する。

## 公式TDnet API仕様から確認できた項目

- Indexには5桁コード、銘柄略称、開示日・時刻、開示番号、履歴番号、表題、公開項目コード、PDF / XBRL有無、revision / deleteがある。
- 公開項目コードは複数保持でき、文書分類（決算、M&A等）を表す。v1はタイトルキーワードよりこれを優先する。
- Document APIは開示番号とPDF / XBRL種別で取得する。大きな文書は一回限りのURLで返る。
- 保存期間は過去5年、Index APIは1回最大10,000件、日付範囲は最大1か月。開示直後に必ず取得可能とは保証されない。
- 文書は訂正・削除され得る。削除済み文書データは取得できず、インデックスの処理属性と履歴番号を保存する必要がある。
- J-Quants TDnetアドオンの公開資料では、詳細なrate limit、公開項目コード表、文書URLのフィールド仕様は契約者向け仕様を確認する必要がある。

## v1 Event taxonomy

公式の公開項目コードを `source_item_codes` として保存し、アプリ表示用に次の分類を設ける。公式コードが未取得・未対応の場合のみタイトルによる限定的な `その他重要開示` とする。

- 決算発表
- 業績予想修正 / 配当予想修正
- 自己株式取得 / 自己株式消却
- 株式分割・株式併合 / 増資・新株発行
- M&A・TOB / 事業譲渡・取得
- 大型受注・契約 / 提携 / 新製品・新サービス
- 経営方針・中期経営計画 / 人事・経営体制変更
- その他重要開示

## 共通 Event schema

`ticker`, `code`, `company_name`, `event_id`, `event_type`, `event_subtype`, `title`, `disclosed_at`, `source_name`, `source_url`, `document_url`, `source_item_codes`, `is_revision`, `is_deleted`, `importance`, `summary`, `fetched_at`

- `event_id` は開示番号、`is_revision` / `is_deleted` はTDnetの処理属性、改訂履歴は履歴番号で保持する。
- `importance` と `summary` はv1では生成しない。表示順位は開示時刻と公式分類を使い、因果関係を推定しない。
- `document_url` は正式APIが返す場合だけ保存する。一時URLの永続表示・公開TDnetからの推測はしない。

## 将来の実装条件

アドオン契約が確認できた場合だけ、取得層（認証・月単位取得・ページング・部分失敗・正規化）を追加する。Stock Detailでは直近3〜5件を日付・種別・短い表題で表示し、残りはexpanderへ置く。`Stock-specific / Unexplained` には「直近に開示がある」ことだけを説明候補として表示し、株価変動の原因とは断定しない。

Fundamentalsは数値、Corporate Eventsは開示時刻・種別という役割で分離する。一般ニュース、感情分析、イベントスタディはPhase 2以降に再判断する。

## 制約と次の判断

- 現行キーの契約プラン・アドオン有無、rate limit、個別APIフィールドはリポジトリから確認できない。
- 有料アドオンを契約しない限り、Corporate Eventsの本番取得・Stock Detail表示は実装しない。
- 契約後は公式仕様と実レコードでCore20 coverage、訂正・削除、コード変換、API障害時の部分表示を診断してから Conditional Go / Go を再判定する。
