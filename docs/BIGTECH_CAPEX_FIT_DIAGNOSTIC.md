# Big Tech AI関連CapEx 限定採否診断

調査・再選定日: 2026-09-19
判定: **限定GO（Microsoft / Alphabet / MetaをADOPT、AmazonはDO NOT ADOPT）**

## 1. 調査目的と範囲

検証する問いは「同一企業・同一対象年度のCapEx guidance変更と投資用途の説明が、台湾受注・韓国輸出に加えて、日本半導体株の判断理由または次の確認事項を変えるか」である。取得可能性やCapEx増加だけでは採用しない。株価リターン、勝率、相関、先行性、売買予測力は、今回の2～3事例では評価しない。

Decision Log / Forward Validationの運用を最優先とし、具体的支障がない限り機能追加しない。半導体の大型拡張、Cycle Score、条件・重み最適化、韓国長期履歴再探索は停止を維持する。本番loader、UI、DB、Decision Log schema、Historical Validation、自動更新は変更しない。

対象はMicrosoft、Alphabet、Amazon、Metaの4社だけである。2026-09-19時点の最新公式決算開示から逆算し、同一target yearのguidanceを比較できる連続2～3開示を選んだ。過去の方が比較しやすいという理由で2025 Q1～Q3へ戻していない。

## 2. 対象開示の再選定

| Company | 最新側から選定した開示 | Target year | 選定理由 |
|---|---|---:|---|
| Microsoft | FY26 Q3 / FY26 Q4 | CY2026 | Q3で約190、Q4で約175を開示。ただしQ4でlease分類変更を明示したため、経済的投資計画と会計上のCapExを分離して比較できる最新2回 |
| Alphabet | 2025 Q4 / FY2025、2026 Q1、2026 Q2 | CY2026 | 175–185→180–190→195–205を同じcalendar yearについて連続比較できる最新3回 |
| Amazon | 2025 Q4 / FY2025、2026 Q1、2026 Q2 | CY2026 | Q4で約200を数値開示。続くQ1/Q2公式release / SEC添付には同じ年次数値guidanceの再提示がなく、comparison unavailable |
| Meta | 2025 Q4 / FY2025、2026 Q1、2026 Q2 | CY2026 | 115–135→125–145→130–145を同一定義で連続比較できる最新3回 |

Microsoftは数値を単純比較できないため2回で終了した。Amazonは1回しか同一年次数値を確認できないためcomparison unavailableとし、別archiveやベンダーを探索していない。

## 3. 公式データ源と公開時点

### Microsoft

- [FY2026 Q3 earnings call（2026-04-29）](https://www.microsoft.com/en-us/investor/events/fy-2026/earnings-fy-2026-q3)
- [FY2026 Q4 earnings call（2026-07-29）](https://www.microsoft.com/en-us/investor/events/fy-2026/earnings-fy-2026-q4)

公式HTML transcriptで開示日、発言、actual、guidance、lease分類変更を追跡できる。ページ上でcall開始時刻を確認できないため、利用可能日は確認済み、正確な時刻は未確認とする。一般的なafter-market時刻は補完しない。

### Alphabet

- [2025 Q4 earnings call（2026-02-04 13:30 PT）](https://abc.xyz/investor/events/event-details/2026/2025-Q4-Earnings-Call-2026-Dr_C033hS6/default.aspx)
- [2026 Q1 release（2026-04-29）](https://www.sec.gov/Archives/edgar/data/1652044/000165204426000043/googexhibit991q12026.htm) / [公式transcript](https://s206.q4cdn.com/479360582/files/doc_events/2026/Apr/29/Alphabet-2026_Q1_Earnings_Transcript.pdf)
- [2026 Q2 release（2026-07-22）](https://www.sec.gov/Archives/edgar/data/1652044/000165204426000066/googexhibit991q22026.htm) / [SEC accepted 2026-07-22 16:01:36 ET](https://www.sec.gov/Archives/edgar/data/1652044/000165204426000066/0001652044-26-000066-index.htm) / [公式call](https://abc.xyz/investor/events/event-details/2026/2026-Q2-Earnings-Call-2026-GgTAq7Is0z/default.aspx)

公式callページ／transcriptがguidance本文とcall日時を残し、releaseは8-K添付として残る。Q2の数値guidanceはrelease本文ではなく公式callで初めて確認可能となるため、releaseのSEC acceptanceをguidanceの利用可能時刻に代用しない。

### Amazon

- [2025 Q4 / FY2025 results（2026-02-05）](https://ir.aboutamazon.com/news-release/news-release-details/2026/Amazon-com-Announces-Fourth-Quarter-Results/)
- [2026 Q1 results（2026-04-29）](https://ir.aboutamazon.com/news-release/news-release-details/2026/Amazon-com-Announces-First-Quarter-Results/)
- [2026 Q2 results（2026-07-30）](https://ir.aboutamazon.com/news-release/news-release-details/2026/Amazon-com-Announces-Second-Quarter-Results/)

日付と公式releaseは追跡できる。Q4ではCY2026約200を公式説明したが、Q1/Q2の永続的なrelease / SEC添付には同じ年次数値guidanceを再提示していない。両四半期のreleaseはAI投資がfree cash flowへ与えた影響を説明するものの、それを約200の維持確認とは扱わない。期間限定webcastや二次資料で補完しない。

### Meta

- [2025 Q4 / FY2025 results（2026-01-28）](https://investor.atmeta.com/investor-news/press-release-details/2026/Meta-Reports-Fourth-Quarter-and-Full-Year-2025-Results/)
- [2026 Q1 results（2026-04-29）](https://investor.atmeta.com/investor-news/press-release-details/2026/Meta-Reports-First-Quarter-2026-Results/)
- [2026 Q2 8-K Exhibit 99.1（2026-07-29）](https://www.sec.gov/Archives/edgar/data/1326801/000162828026050596/meta-06302026xexhibit991.htm) / [公式call（2026-07-29 13:30 Pacific）](https://investor.atmeta.com/investor-events/event-details/2026/Q2-2026-Earnings-Call/default.aspx)

guidanceを含むreleaseが会社IRおよび8-K添付として残る。release日を確認でき、SEC acceptanceが取得できる開示では秒単位のpoint-in-timeも追跡できる。IR表示より早い時刻を推測しない。

## 4. 主要比較表

金額はUSD billion。ActualとGuidanceは混ぜない。

| Company / Disclosure | Published at | Actual CapEx | CY2026 guidance | Definition / lease | 公式AI / Data Center説明 | Change | 比較可能性 / PIT |
|---|---|---:|---:|---|---|---|---|
| Microsoft FY26 Q3 | 2026-04-29、時刻未確認 | 31.9 | 約190（component pricing約25を含む） | total CapEx。finance leases 4.7、cash PP&E 30.9を別記 | 約2/3が短寿命GPU/CPU、Azure、AI platform/apps/services、DC capacity | 数値初回 | comparable with caveat / Partial |
| Microsoft FY26 Q4 | 2026-07-29、時刻未確認 | 41.0 | 約175 | total CapExはfinance leasesを含みoperating leasesを含まない。future DC leasesの一部をfinanceからoperatingへ変更 | 約2/3が短寿命CPU/GPU。AI需要とcapacity拡張 | **economic plan unchanged; definition/classification changed** | definition changed / Partial |
| Alphabet 2025 Q4 | 2026-02-04 13:30 PT | Q4 27.9 / FY 91.4 | 175–185 | reported CapEx。lease commitmentsは別開示 | 約60% servers、40% DC/network。DeepMind、Services、Cloud需要 | 数値初回 | exactly comparable / Yes |
| Alphabet 2026 Q1 | 2026-04-29、call時刻確認可 | 35.7 | 180–190 | 同上。Intersect取得関連投資を範囲へ追加 | AI computeの内外需要、technical infrastructure | **raised 175–185→180–190** | comparable with caveat / Yes |
| Alphabet 2026 Q2 | 2026-07-22、call 13:30 PT | 44.9 | 195–205 | 同じreported CapEx | AI infrastructure / global compute、需要対応capacityの納入加速 | **raised 180–190→195–205** | exactly comparable / Yes |
| Amazon 2025 Q4 | 2026-02-05 | FY cash CapEx actualあり | 約200 | Amazon全体。AI専用ではなくchips、robotics、LEO等も含む | AI、AWS、chips、robotics、LEO | 数値初回 | comparison unavailable / Partial |
| Amazon 2026 Q1 | 2026-04-29 | cash-flow actualあり | 永続releaseに再提示なし | purchases of PP&E、lease等は別開示 | AI投資によるFCF影響 | unavailable | not comparable / Partial |
| Amazon 2026 Q2 | 2026-07-30 | cash-flow actualあり | 永続releaseに再提示なし | 同上 | AI投資、AWS需要、capacity | unavailable | not comparable / Partial |
| Meta 2025 Q4 | 2026-01-28 | FY actualあり | 115–135 | purchases of PP&E **including principal payments on finance leases** | Meta Superintelligence Labs、core business、AI/DC capacity | 数値初回 | exactly comparable / Yes |
| Meta 2026 Q1 | 2026-04-29 | 19.84 | 125–145 | 同一定義 | component pricing上昇、将来capacity向け追加DC costs | **raised 115–135→125–145** | exactly comparable / Yes |
| Meta 2026 Q2 | 2026-07-29、call 13:30 Pacific | Q2 actualあり | 130–145 | 同一定義 | AI efforts、infrastructure capacity | **raised floor / narrowed 125–145→130–145** | exactly comparable / Yes |

## 5. 定義、lease、actual vs guidance

- **Microsoft:** total CapExはfinance leasesを含み、cash paid for PP&Eを別掲する。Q4ではdatacenter leaseの見積耐用年数更新により、将来契約の一部がfinance leaseからoperating leaseへ移る。operating leaseはCapExに含まれない。会社はこの影響を除くCY2026投資期待はunchangedと明言したため、190→175を`guidance lowered`としない。判定は`definition changed`である。
- **Alphabet:** reported CapExはland/buildings、servers/network equipment等のproperty and equipment投資で、lease commitmentsは別開示である。Q1の+5はIntersect取得を含むため`comparable with caveat`、Q2は同じreported CapExのrange引上げとして扱う。
- **Amazon:** cash flowのpurchases of PP&E、finance leases、financing obligations等が分かれる。Q4の約200をQ1/Q2 actualやFCF説明と比較しない。
- **Meta:** 3回とも`capital expenditures, including principal payments on finance leases`という同じ定義である。

会社間で定義が異なるため4社合計、横断ランキング、AI比率を作らない。総CapExをAI専用金額ともみなさない。

## 6. 公式用途説明と日本株への関連仮説

企業の公式説明は、MicrosoftがGPU/CPUとDC capacity、Alphabetがservers/DC/networkとAI compute、AmazonがAIに加えchips/robotics/LEO、MetaがAI/DC capacityとcore businessである。AI専用金額は4社とも作らない。

当アプリ側の仮説は、server / accelerator / memory / networking / data-center capacityの計画変更または定義変更が、後続するTaiwan Orders、Korea Exports、日本の生産・装置・在庫を確認する上流の観測点になる、という範囲に限定する。東京エレクトロン（wafer fab equipment）、アドバンテスト（test）、ディスコ（cutting / grinding / packaging周辺）、キオクシア（memory / storage）への需要経路を確認できるが、特定Big TechのCapEx変更と個別株価格の直接因果は認定しない。

## 7. 既存情報への追加価値とDecision Log候補

| Company | 追加情報 | 判断理由・次の確認事項を変えるか |
|---|---|---|
| Microsoft | 190→175を見かけ上の減額と誤認せず、lease分類と経済的投資計画を分けられる | 「economic investment unchangedか」「finance/operating leaseの分類差か」を次回確認できる |
| Alphabet | 同一CYのrangeが2回増額され、AI computeとcapacity納入加速を公式説明 | 「CY2026 range維持」「capacity加速が台湾・韓国へ波及するか」をreview conditionにできる |
| Amazon | 約200の背景は得られるが、最新連続開示から変更イベントを再現できない | 単発の背景説明に留まり、再現可能な観測点としての追加価値が不足 |
| Meta | 同一定義rangeの下限が連続上昇し、AI/DC理由も残る | 「次回range維持」「lease定義」「後続実需」をreview conditionにできる |

コードやschemaは変更しない。当面は既存Decision Logの自由記述による判断理由、コメント、review / refutation conditionへの手動追記候補である。Snapshotへの自動追加価値は未検証である。

## 8. 継続更新負荷と有料データ

| Company | 公式資料 | 主な人手確認 | 負荷 |
|---|---|---|---|
| Microsoft | 規則的なIR HTML transcript + release/SEC | target CY/FY、finance/operating lease、経済的計画とreported CapExの分離 | Medium |
| Alphabet | 規則的なcall HTML/PDF + 8-K | range、買収影響、用途、guidanceが利用可能になったcall時刻 | Low–Medium |
| Amazon | release/8-K + 保存期限のあるwebcast | 年次数値の再提示、lease範囲、単発発言の永続性 | High |
| Meta | 規則的なrelease/8-K | range、finance lease principal定義、用途 | Low |

実測していない作業時間は記載しない。公式IR / SECだけでMicrosoft、Alphabet、Metaの問いに答えられ、有料データは不要である。Amazonを成立させるための有料契約も提案しない。

## 9. 会社別採否

### Microsoft — ADOPT（definition-aware限定）

最新2回は同じCY2026を対象とし、原資料、日付、actual、AI/DC用途を追跡できる。190→175はexactly comparableではないが、会社自身がlease分類変更とeconomic investment unchangedを説明しており、定義差を安全に記録できる。`definition changed / economic plan unchanged`として扱うこと自体が追加の判断材料になる。更新負荷はMediumで許容可能。

### Alphabet — ADOPT

最新3回で同一CY2026の175–185→180–190→195–205を公式資料から再現できる。Q1の買収影響というcaveatも説明でき、AI compute、servers、DC/network、capacity deliveryの用途が明確である。point-in-time、追加価値、更新負荷の条件を満たす。

### Amazon — DO NOT ADOPT

最新3回のうち同一CY2026の数値guidanceはQ4の約200だけで、Q1/Q2の永続的な公式release / SEC添付では再提示・変更を確認できない。日付、actual、AI用途を確認できても、2回以上の同一年度比較と継続更新性を満たさない。

### Meta — ADOPT

最新3回で同一CY2026、同一定義（finance lease principal込み）の115–135→125–145→130–145を再現できる。公開時点、AI/DC理由、既存実需への追加価値、低い更新負荷を満たす。

初版からの変更は**MicrosoftのみDO NOT ADOPT→ADOPT**である。Alphabet / MetaのADOPT、AmazonのDO NOT ADOPTは維持したが、根拠をすべて最新側の開示へ置き換えた。

## 10. 全体判定: 限定GO

Microsoft、Alphabet、Metaは、point-in-time追跡、同一target yearの比較、定義差の説明、AI/DC用途、既存情報への追加価値、許容可能な更新負荷を満たす。したがって「全4社統一機能」ではなく、**採用3社だけの小さなリサーチ機能を要件検討する価値がある**という限定GOとする。

今回、実装へは進まない。ユーザー判断なしにloader、UI、Decision Log連携、自動更新を開始しない。

## 11. GOの場合の最小機能候補

別途承認される場合も、Microsoft / Alphabet / Metaだけを対象とする。

1. 企業、開示日時、target year、actual、guidance、comparison basis、lease treatment、公式用途、source URLを持つ小さな手動更新データ。
2. 同一企業・同一target yearについて `raised / lowered / unchanged / direction strengthened / definition changed / not comparable` を表示。
3. Microsoftでは`reported CapEx change`と`company-stated economic investment change`を別項目にし、190→175をloweredへ自動分類しない。
4. AI専用額、会社横断合計、momentum score、売買シグナルを作らない。
5. Decision Log schemaへ接続せず、既存コメント／review conditionで前向きに利用価値を確認する。

## 12. 停止理由と未解決事項

Amazonは今回DO NOT ADOPTで終了する。年次CapEx guidanceと定義を永続的な公式release / SEC添付へ2回以上継続掲載する場合のみ再調査条件が成立する。別API、ベンダー、archive、OSSは探索しない。

未解決事項は、Microsoft/Alphabetの正確なguidance利用可能時刻を全開示で統一的にSEC acceptanceへ置き換えられないこと、採用3社の情報が実際にDecision Logの理由・反証条件を改善するかである。前者は日付または公式call時刻までの保守的記録で対応できる。後者は過去2～3事例の株価では評価せず、運用時の前向き観察でのみ評価する。
