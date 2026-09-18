# J-Quants公式バリュエーション指標API 限定適合性調査

調査日: 2026-09-18

対象: J-Quants API V2 `GET /v2/equities/valuation`

結論: **HOLD（定義確認と費用は概ね適合するが、企業行動・株式数basisの詳細が説明可能な水準に達していない）**

本書では根拠の状態を次の3つに分ける。

- **公式確認済み**: J-Quants公式API仕様、公式計算原則、公式Python Clientまたは公式料金表で確認した事項
- **live確認済み**: APIレスポンスを実際に取得して確認した事項
- **未確認**: 公式資料に詳細がなく、今回の環境でも実データを確認できなかった事項

## 1. 調査目的

自前の「Yahoo調整後価格 ÷ J-Quants会社予想EPS」は、価格とEPSのper-share basisを直接確認できず停止している。本調査は、J-Quantsが同一サービス内で算出する`FwdPER`が、この問題を追加の企業行動DBなしで解消し、Core20の投資判断用評価情報として説明可能かを限定的に確認するものである。本番UI、課金、プラン変更、既存`valuation.py`の安全条件変更は行わない。

## 2. 公式API概要

**公式確認済み**:

- エンドポイントは`GET /v2/equities/valuation`。日付または銘柄コードで取得する。
- 日次の株価と決算開示を用い、J-Quantsが評価指標を算出する。
- 返却項目は`Date`、`Code`、`EPS`、`FwdEPS`、`BPS`、`ROE`、`FwdROE`、`PER`、`FwdPER`、`PBR`、`MktCap`。
- ETF、ETN、優先株等では行が返っても指標がNullになり得る。初期収録期間、新規上場直後、決算期変更の移行期間も入力不足によりNullになり得る。
- 収録開始は2008-07-08。ただし2008～2010年頃は株式数・財務情報の不足によりNullが多い。

公式資料:

- [Valuation Indicators API](https://jpx-jquants.com/en/spec/eq-valuation)
- [How Indicators Are Calculated](https://jpx-jquants.com/en/spec/eq-valuation/calc)
- [APIs and Data Storage Period by Subscription](https://jpx-jquants.com/en/spec/data-spec)

## 3. 指標定義

| 指標 | 公式の基本定義 | Null・注意条件 |
|---|---|---|
| EPS | TTM純利益 ÷ 株式数 | 赤字なら負値。株式数の詳細仕様は非開示 |
| FwdEPS | 進行期の会社予想純利益 ÷ 株式数 | 予想なし・予想取下げでNull。赤字予想なら負値 |
| BPS | 直近四半期末の株主資本 ÷ 株式数 | 株主資本が負なら負値 |
| ROE | TTM純利益 ÷ TTM始点・終点の平均株主資本 | 分母がゼロ以下ならNull |
| FwdROE | 進行期の会社予想純利益 ÷ 直近四半期末株主資本 | 予想なし・取下げ、分母ゼロ以下でNull |
| PER | 当日終値（不成立日は基準値）÷ EPS | EPSがゼロ以下ならNull |
| FwdPER | 当日終値（不成立日は基準値）÷ FwdEPS | 予想なし・取下げ、FwdEPSがゼロ以下ならNull |
| PBR | 当日終値（不成立日は基準値）÷ BPS | BPSがゼロ以下ならNull |
| MktCap | 株価 × 自己株式控除後株式数 ÷ 1,000,000 | 百万円単位。企業行動を反映すると明記 |

重要なのは、`FwdEPS`がFinancial Summaryの開示EPSをそのまま転記した値ではなく、**J-Quantsが進行期の会社予想純利益と株式数から再計算する値**である点である。会社予想・コンセンサス・TTMを混同しないため、将来表示する場合の名称は「**予想PER（J-Quants定義）**」または「**J-Quants FwdPER**」が適切である。

## 4. FwdPERと当アプリ目的の対応関係

**公式確認済み**:

- 分子は対象日の終値。不成立日はその日の基準値。
- 分母はJ-Quants算出のFwdEPSで、その利益は「進行期の会社予想純利益」。
- 決算情報は開示時刻にかかわらず翌営業日から指標へ反映される。このため、開示当日終値へのlook-ahead混入を避ける当アプリの保守的方針と整合する。
- 赤字予想またはゼロFwdEPSではFwdPERはNullであり、負のPERを表示しない方針と整合する。

**未確認**:

- レスポンスには予想対象Fiscal Year、対象期末、元の開示日・開示IDがない。利用者へ「どの年度の予想か」を値単体から表示できない。
- 決算期変更時は移行期間にNullとなり得ることまでは確認できるが、どの時点で新しい「進行期」へ切り替えるかの詳細仕様は非開示。
- 訂正開示の反映規則は、データ訂正が既存値の上書きで履歴・差分なしであること以外、FwdPER固有の説明がない。

したがって、J-Quants FwdPERは自前計算より定義の一貫性が高いが、当アプリが従来想定した「対象年度と開示日を併記するCurrent Forward PER」と完全には同一ではない。

## 5. 株価・財務・企業行動basis

**公式確認済み**:

- J-Quantsが株価・会社予想純利益・株式数を同じ計算系で組み合わせるため、Yahoo価格とJ-Quants EPSを混ぜる自前計算のクロスプロバイダbasis問題は避けられる。
- 公式計算原則は「株式数の扱い、決算期変更の調整を含む詳細計算仕様は非開示」と明記している。
- MktCapについてのみ、自己株式控除後株式数と企業行動（株式分割・併合）の反映が明記されている。
- Financial Summaryの開示は時刻を問わず翌営業日から指標へ反映される。

**未確認**:

- FwdEPS/PERに用いる株式数が期中平均、期末、予想前提株式数のどれか。
- 自己株式をFwdEPSでも控除するか。
- 将来予定された分割を会社予想純利益・株式数へいつ反映するか。
- 分割・併合後に過去のFwdEPS/FwdPERを遡及修正するか。
- 訂正開示前の値を復元できるか（公式には訂正は上書きされ、旧版・差分は提供されない）。

MktCapの注記をFwdPERへ自動的に読み替えることはできない。公式値であること自体は、自動的な`basis_verified`の証明にはしない。

## 6. 更新頻度・データ鮮度

**公式確認済み**:

- Valuation Indicatorsは営業日ごと、概ね16:30更新。
- 当日決算は開示時刻にかかわらず翌営業日から指標へ反映。
- 更新完了通知、version、ETagはない。更新時刻は保証されず前後し得る。
- 訂正は既存値の上書きで、旧版と差分は保持されない。
- Financial SummaryはPremium APIでは準リアルタイム、その他プランのAPI/CSVは日次（概ね18:00速報、24:30確定）だが、Valuation Indicators自体は翌営業日反映ルールである。

公式資料: [Update Timing of Provided Data](https://jpx-jquants.com/en/spec/data-update)

## 7. プラン・継続費用

2026-09-18時点の個人向け公式プランを整理する。

| プラン | 月額（税込） | Valuation API | 履歴 | 遅延 | 今回の用途 |
|---|---:|---|---|---|---|
| Free | 0円 | 利用可 | 2年 | 12週間遅延 | 定義・過去値の確認のみ。直近投資判断には不適 |
| Light | 1,650円 | 利用可 | 5年 | 遅延表記なし | **直近FwdPER取得の最小候補** |
| Standard | 3,300円 | 利用可 | 10年 | 遅延表記なし | Valuationだけなら過剰。長期履歴が必要な場合 |
| Premium | 16,500円 | 利用可 | 提供全期間（最大20年） | 遅延表記なし | Valuationだけなら過剰 |

Valuation Indicatorsは全プランで利用可能だが、Freeは12週間遅延である。したがって当日の投資判断に使う直近値の最低継続費用は、現行の公式表では**Lightの月額1,650円（税込）**となる。今回は課金・プラン変更を行っていない。

公式資料: [J-Quants料金・プラン](https://jpx-jquants.com/)、[データ提供期間](https://jpx-jquants.com/en/spec/data-spec)

## 8. Python Client適合性

**ローカル確認済み**:

- `requirements.txt`は`jquants-api-client>=2.6.0`、現在解決済みバージョンは2.6.0。
- 2.6.0の`ClientV2`には`get_eq_valuation`がない。

**公式確認済み**:

- 公式Client v2.7.0（2026-09-14）が`get_eq_valuation`と`get_eq_valuation_range`を追加した。
- 追加dependencyは不要だが、利用するなら最小バージョンを`>=2.7.0`へ上げる必要がある。
- `_range`は暦日ごとの並列リクエストであり、Freeの5 calls/minute等ではレート制限に注意が必要。

今回は文書調査のみのためupgradeしない。既存コードへの影響は限定的と見込むが、次PRで依存更新、既存J-Quants loader回帰テスト、rate-limit制御を一緒に検証する。

公式資料: [J-Quants公式Python Client](https://github.com/J-Quants/jquants-api-client-python)、[v2.7.0 release](https://github.com/J-Quants/jquants-api-client-python/releases/tag/v2.7.0)

## 9. 代表銘柄の限定確認

**Environment Blocked**: このCodex環境では`JQUANTS_API_KEY`を参照できず、7203、7011、8306、8766、9984のlive API確認は実施していない。取得可否、実際のNull、銀行・保険・投資会社の値を推測していない。ユーザーへ同じ診断の再実行は要求せず、今回の判断は公式仕様だけで行う。

なお、以下は**2026-09-18のユーザー提供結果**であり、Valuation APIのlive確認ではない。

| 既存自前診断 | 結果 |
|---|---:|
| Core20 | 20 |
| Financial Summary取得失敗 | 0 |
| 有効Current Forecast EPS | 14/20 |
| Adjustment bars成功 | 17/20 |
| API error / input_unavailable | 0 / 3 |
| safe Current Forward PER | 0/20 |
| Forecast Revision comparable | 0/20 |
| Historical Forward PER | 0/20 |
| split/per-share basis unverified | 20/20 |
| J-Quants / Yahoo価格終端 | 2026-06-26 / 2026-09-16（lag 82日） |

## 10. 解消する問題

- 価格とFwdEPSを同じJ-Quants計算系で生成するため、Yahoo調整後価格とJ-Quants開示EPSのbasisをアプリ側で接合する問題を避けられる。
- 進行期の会社予想純利益、当日終値、翌営業日反映、赤字・予想取下げ時のNullが公式定義される。
- EPS/BPSを当アプリで再計算せず、PER/PBR/ROEを同一APIから取得できる。
- Freeでも遅延した過去値により実データ形状を確認できる。

## 11. 残る問題

- 株式数・決算期変更・企業行動の詳細計算仕様は非開示で、FwdPERのper-share basisを利用者へ完全には説明できない。
- FwdPERレコードだけでは対象Fiscal Year、対象期末、元の開示日を表示できない。
- 訂正前の値が保存されず、厳密なpoint-in-time再現には不十分。
- Freeは12週間遅延で、現在の判断材料には使えない。
- 代表銘柄のNull率と特殊業種の実挙動は未確認。
- 銀行・保険・投資会社で値が存在しても、同一基準の割安・割高判定には直結しない。

## 12. 継続費用

直近値を日常利用する最低候補はLightの**月額1,650円（税込）**。追加の企業行動DBは不要となる可能性があるが、公式の非開示部分を補うためだけに独自DBを新設するなら今回の目的（低工数・保守可能）から外れる。Standard/Premiumへ上げる合理性はValuation単体では確認できない。

## 13. 実装量

条件が整った場合の限定実装は小～中規模と見込む。

1. `jquants-api-client>=2.7.0`へ更新し、単発取得を既存cache/rate-limit方針へ統合する。
2. 公式フィールドを欠損のまま保持し、独自再計算をしない。
3. 「予想PER（J-Quants定義）」、価格基準日、12週遅延/プラン状態、対象年度非表示という制約を表示する。
4. 銀行・保険・投資会社は解釈注意を付け、割安・割高判定を行わない。
5. 代表銘柄fixtureと、API未設定・Null・遅延のテストを追加する。

Historical PER、同業ランキング、割安/割高判定はこの実装量に含めない。

## 14. GO / HOLD判断と理由

| 候補 | 判断 | 理由 |
|---|---|---|
| J-Quants FwdPERの限定表示 | **HOLD** | 価格・予想純利益・株式数が同一提供元である利点は大きいが、企業行動と株式数basisの詳細が非開示。対象年度・元開示日もレスポンスから説明できず、代表銘柄live確認も未実施 |
| 自前Yahoo価格 × J-Quants EPS | **NO-GO継続** | split/per-share basis未確認。`AdjFactor=1`を`basis_verified`へ緩和しない |
| Historical PER | **NO-GO** | 訂正が上書きされ、対象年度・開示IDもなく、厳密point-in-time履歴を再現できない |
| PBR限定表示 | **HOLD** | 公式PBRは取得可能だが、今回はFwdPER適合性に限定。BPSの株式数basis詳細も非開示 |
| 同業・業種別割安判定 | **NO-GO** | 業種別モデルと比較条件が未設計 |

費用はLight月額1,650円で保守可能な範囲だが、費用だけを理由にGOとはしない。現時点の総合判断は**HOLD**である。

## 15. 再開条件

次の条件が揃った場合に限り、「予想PER（J-Quants定義）」の限定実装を再検討する。

1. 公式サポート等でFwdEPS/FwdPERの株式数、自己株式、分割・併合、遡及修正の扱いを説明可能な範囲まで確認できる。
2. 対象Fiscal Year/期末をFinancial Summaryと安全に対応付けられるか、表示上「対象年度はAPIから特定不可」と明示する方針を利用者が受容できる。
3. Light以上の継続費用を許容し、代表5銘柄でNull・特殊業種・日付反映を限定確認する。
4. v2.7.0への依存更新とレート制御を既存機能を壊さず検証する。

再開しない場合の次候補は、同一対象年度・同一定義の**会社予想売上、営業利益、純利益の更新履歴とDecision Logの接続**である。これはValuationとは表示しない。EPSは原開示値の履歴表示に限定し、basis未確認ペアから差額、修正率、上方/下方判定、ランキング、シグナル、比較可能と誤認される連続グラフを作らない。
