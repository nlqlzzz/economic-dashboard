# Japan Core 20 Fundamentals / Earnings データ品質診断

調査日: 2026-09-08
対象: Japan Core 20（20銘柄）
結論: **四半期Earnings Trend / Earnings Momentumを含むFundamentals & Earnings v1はNo-Go**

## Executive Summary

既存環境で利用している `yfinance`（Yahoo Finance由来）について、Core20全銘柄の `quarterly_income_stmt`、`income_stmt`、`get_info()` を実地確認した。

- 年次の売上高、営業利益、純利益、EPSは概ね取得できる。
- 一方、四半期の売上高・営業利益・純利益が取得できたのはトヨタ自動車のみ（各1/20）。直近8四半期の履歴は0/20である。
- 四半期EPSは20/20で何らかの値が返るが、4期以上はソフトバンクグループのみで、売上高・利益の四半期系列と整合していない。単独でMomentumやQoQを構成する根拠にはしない。
- `get_info()` のMarket Cap、PER、PBRは20/20で値を返したが、Yahoo Finance由来の現在スナップショットであり、公表日・データVintage・履歴は取得できない。
- EDINETは公式かつXBRLを提供するが、Version 2 APIは登録・APIキーを要する。現行環境にはキーがなく、キーなしの安定自動取得経路は確認できなかった。

このため、今回のStock Detailへ四半期Trend、Earnings Momentum、FundamentalsとResidualを結ぶInterpretationを追加すると、少数銘柄のデータだけを一般化することになる。実装しない。

## 調査したデータソース

| ソース | 方式 | 評価 | 結論 |
| --- | --- | --- | --- |
| Yahoo Finance / `yfinance` | Pythonライブラリの財務Statements・info | 現在Valuationと年次履歴には実用的。ただし日本株の四半期P/L履歴は欠損・不揃い | 四半期Earnings v1には不採用 |
| 金融庁 EDINET API Version 2 | 公式API、XBRL | 定義・提出日・XBRLの点で本命候補 | APIキー取得、XBRL正規化、銀行・保険等の業種差対応を別途設計後に再調査 |

EDINET API Version 2の利用には登録とAPIキー発行が必要であることを金融庁が案内している。APIキーを前提としない今回の実装範囲には入れない。
出所: [金融庁 EDINET APIの利用にかかるご案内](https://disclosure2.edinet-fsa.go.jp/week0010.aspx)

## Core20取得カバレッジ

2026-09-08に各Tickerへ個別アクセスして確認した結果。`4期以上` は、Trendの最低限の比較に使える件数である。

| Metric | Coverage | 4期以上 | 履歴・更新性 | Reliability | v1採用 |
| --- | ---: | ---: | --- | --- | --- |
| 四半期 Revenue | 1/20 | 1/20 | 取得列数も銘柄ごとに不揃い、8期なし | Low | No |
| 四半期 Operating Income | 1/20 | 1/20 | 同上 | Low | No |
| 四半期 Net Income | 1/20 | 1/20 | 同上 | Low | No |
| 四半期 EPS | 20/20 | 1/20 | 多くは1〜3期のみ。P/L系列と整合しない | Low | No |
| 年次 Revenue | 20/20 | 20/20 | 原則4年、決算月は会社ごとに異なる | Medium | 将来の年次表示候補 |
| 年次 Operating Income | 18/20 | 18/20 | 銀行・保険で非表示 | Medium | 将来の業種別表示候補 |
| 年次 Net Income | 18/20 | 18/20 | 一部業種・銘柄で非表示 | Medium | 将来の業種別表示候補 |
| 年次 EPS | 20/20 | 20/20 | 原則4年 | Medium | 将来の年次表示候補 |
| Market Cap | 20/20 | N/A | 現在スナップショット、取得日時のみ | Medium | 将来候補 |
| Current PER | 20/20 | N/A | 現在スナップショット、履歴なし | Medium | 将来候補 |
| Current PBR | 20/20 | N/A | 現在スナップショット、履歴なし | Medium | 将来候補 |
| ROE | 18/20 | N/A | 現在スナップショット | Medium | 将来候補 |
| Operating Margin | 20/20 | N/A | 銀行・保険には一般事業会社と同じ意味で非適用 | Low〜Medium | 一律表示しない |
| Fiscal year end | 20/20相当 | N/A | 年次Statement末日から判定可能 | Medium | 年次表示では利用可 |
| Guidance | 0/20を安定的に取得 | N/A | 構造化かつ出所・公表日付きの経路なし | Low | No |

## 日本企業の四半期定義と累計値

今回取得したYahoo Finance四半期データでは、四半期単独値か累計値かを全Core20で一貫して識別できなかった。

- 1Q、半期累計、3Q累計、通期を混同してQoQを計算しない。
- `2Q単独 = 2Q累計 - 1Q累計` の導出は、公式XBRL等で累計定義と同一会計基準を確認できる場合だけ許容する。
- 導出値には `is_derived = true`、元の累計/単独定義、対象期間を保持する必要がある。
- したがって今回、QoQ・四半期YoY・四半期Earnings Momentumは採用しない。

## 指標別の採否

### 採用しないもの

- 四半期Revenue / Operating Income / Net Income / EPS Trend
- 四半期YoY、QoQ、8四半期チャート
- Earnings Momentum
- Guidance
- Historical PER / PBR

理由は、Core20の80〜90%以上で定義・履歴・対象期間がそろわない、または当時値を再構築できないため。

### 年次データとして将来検討できるもの

- Revenue、Operating Income、Net Income、EPSの4年程度の年次履歴
- 最新の年次Revenue YoY、Operating Income YoY、EPS YoY
- Current Market Cap、PER、PBR、ROE

ただし年次の最新決算期は2025年12月期または2026年3月期など企業ごとに異なり、直近株価の説明に使うには鮮度が低い。年次表示を別の限定的な `Annual Fundamentals` として導入するかは、EDINET等の四半期ソース設計後に再評価する。

## 業種差

- 銀行（MUFG）と保険（東京海上）ではOperating Incomeが取得されず、Operating Marginを一般事業会社と同じように比較してはならない。
- 金融業向けKPI（経常利益、事業利益、保険料収入、自己資本等）を追加する今回の範囲にはしない。
- よって、業種にかかわらず同じ利益率を使うMomentum判定は行わない。

## 実装前に解決すべき課題

1. EDINET APIキーの取得可否と、利用条件・Secret管理の方針を決める。
2. XBRLから銘柄横断で使えるRevenue、Operating Income、Net Income、EPSを正規化し、会計基準・連結/個別・単独/累計を保持する。
3. 提出日（市場が利用可能になった日）とreference periodを明確に分ける。
4. 銀行・保険を一般事業会社のOperating Margin比較から除外するルールを確立する。
5. Core20全体で少なくとも4〜8四半期の整合的なカバレッジを測定し、80〜90%を満たした指標だけをEarnings v1へ採用する。

## Go / No-Go

**No-Go: 今回は診断のみで停止する。**

UI、Stock Detail分析ロジック、`app.py`、既存テストは変更しない。Fundamentals / Earnings v1は、上記の公式・構造化データ経路を確立してから再開する。
