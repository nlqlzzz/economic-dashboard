# Big Tech AI / Data Center投資計画

## 目的

半導体テーマで、Big TechのAI / Data Center関連投資計画が前回の公式決算開示からどう変化したかを確認する小規模リサーチ機能である。売買シグナル、予測モデル、AI専用CapEx推定ではない。

対象はPR87でADOPTとしたMicrosoft、Alphabet、Metaだけである。Amazonを含む非採用企業は本番表示へ追加しない。

## データとschema

手動更新datasetは[`data/bigtech_capex_research.json`](../data/bigtech_capex_research.json)に置く。1 disclosureを1 recordとし、公開時点、target year、actual、guidance、比較状態、変化label、economic plan、CapEx定義、lease treatment、公式用途、公式sourceを保持する。初期datasetは8開示である。

`bigtech_capex.py`はJSON読込、schema検証、日付parse、並び替え、表示用summary生成を担当する。対象3社、必須field、guidance型と数値、status enum、重複、HTTPS source URLを検証し、不整合はfail closedとする。

## 公式情報と当アプリ分析の分離

datasetの`official_use_summary`は会社が説明した用途だけを保持する。日本株との関連仮説と次の確認事項は`BIGTECH_RESEARCH_CONTEXT`へ分離する。総CapExをAI専用額とみなさず、会社横断合計やランキングを作らない。

仮説経路は、AI / Data Center投資からserver / accelerator / memory / networking需要、Taiwan Orders、Korea Exports、日本の半導体生産・装置へ至る確認経路である。特定企業のCapEx変化と個別株価格の直接因果は示さない。

## 比較ルール

- 同一company・同一target yearだけを前回比較する。target yearが変わった最初の開示は`initial`とし、前年guidanceと比較しない。
- `comparison_status=definition_changed`は数値差より優先し、`raised`または`lowered`へ変換しない。
- MicrosoftのCY2026 約190→約175は、future datacenter leasesの一部がfinance leaseからoperating leaseへ移ることによるreported CapEx定義への影響である。表示は「定義変更」「経済的投資計画: 据え置き」とする。
- `comparison_status=caveat`は数値を表示しつつ「比較注意」を付ける。Alphabet 2026 Q1はIntersect取得関連投資を含む。
- Actualの四半期変化からguidance changeを推測しない。

## 手動更新方法

1. 会社IR、公式transcript、SECの一次資料で公開日時、target year、guidance、定義、lease、用途を確認する。
2. 同じtarget year・comparison basisかを確認して新しいrecordをJSON末尾へ追加する。
3. `dataset_updated_at`を更新する。公開時刻を確認できない場合は`published_precision=date`とし、時刻を推測しない。
4. 新年度の最初は`change_label=initial`とする。定義変更は数値方向にかかわらず`definition_changed`とする。
5. `python -m unittest test_bigtech_capex -v`と全テストを実行する。

ライブ取得、自動スクレイピング、自動更新は行わない。Git履歴を更新履歴として利用する。

## UIとfailure handling

半導体テーマのMarketと世界需要詳細の間に、会社別の縦カードを表示する。主表示はtarget year、前回・今回guidance、変化、最新開示日、公式用途、当アプリの確認事項に限定する。定義、lease、actual、開示履歴、公式sourceはexpanderへ置く。

JSONが欠損・不正でもBig Tech sectionだけ警告して終了し、台湾、韓国、日本、Historical Validationの表示を継続する。

## Decision Logと非対象機能

Decision Log、Supabase、Snapshot、Forward Validationへは接続しない。必要な場合は利用者が既存コメントやreview conditionへ手動記録する。

Historical Validation、株価リターン、相関、CapEx momentum、AI Investment Score、Cycle Score、AI専用CapEx推定、会社横断合計、ランキングも対象外である。
