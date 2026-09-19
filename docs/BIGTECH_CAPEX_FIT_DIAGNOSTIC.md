# Big Tech AI関連CapEx 限定採否診断

調査日: 2026-09-19
判定: **限定GO（Alphabet / MetaのみADOPT）**

## 1. 調査目的

検証した問いは「同一企業・同一対象年度のCapEx guidance変更と投資用途の説明が、台湾受注・韓国輸出に加えて、日本半導体株の判断理由または次の確認事項を変えるか」である。取得可能性やCapEx増加だけでは採用しない。株価リターン、勝率、相関、先行性、売買予測力は、2～3事例では評価しない。

## 2. Astra決定と今回の範囲

Decision Log / Forward Validationの運用を最優先とし、具体的支障がない限り機能追加しない。現行実装には理由、コメント、見直し・反証条件、不変Snapshot、20・60・120営業日後の同一終点評価があり、今回と分離すべき重大な既知障害は確認しなかった。半導体の大型拡張、Cycle Score、条件・重み最適化、韓国長期履歴再探索は停止を維持する。

今回はMicrosoft、Alphabet、Amazon、Metaの公式IR / SECだけを使い、各社3開示で終了した。本番loader、UI、DB、Decision Log schema、Historical Validation、自動更新は変更しない。

## 3. 対象企業と開示選定

将来リターンを見る前に、最新側から同一年度比較の可否を固定した。

| Company | 固定した開示 | 数値guidanceの対象年度 | 選定結果 |
|---|---|---:|---|
| Microsoft | FY2026 Q1 / Q2 / Q3 calls | FY2026またはCY2026 | FY26の数値通期guidanceは連続しない。Q3でCY2026を初めて数値化 |
| Alphabet | 2025 Q1 / Q2 / Q3 calls | CY2025 | 3回連続で同じ通期CapExを比較可能 |
| Amazon | 2025 Q1 / Q2 / Q3 releases | CY2025 | 公式リリースに通期CapEx guidanceがないためcomparison unavailable |
| Meta | 2025 Q1 / Q2 / Q3 releases | CY2025 | 3回連続で同一定義のレンジを比較可能 |

## 4. 会社別公式データ源と公開時点

### Microsoft

- [FY2026 Q1 call, 2025-10-29](https://www.microsoft.com/en-us/investor/events/fy-2026/earnings-fy-2026-q1)
- [FY2026 Q2 call, 2026-01-28](https://www.microsoft.com/en-us/investor/events/fy-2026/earnings-fy-2026-q2)
- [FY2026 Q3 call, 2026-04-29](https://www.microsoft.com/en-us/investor/events/fy-2026/earnings-fy-2026-q3)

会社公式HTML transcriptは日付、発言、実績、guidanceを追跡できる。ページにはcall開始時刻が明示されないため、公開日は確認済み、正確な利用可能時刻は未確認とする。一般的なafter-market時刻は補完しない。

### Alphabet

- [2025 Q1 call, 2025-04-24 13:30 PT](https://abc.xyz/investor/events/event-details/2025/2025-Q1-Earnings-Call/default.aspx)
- [2025 Q2 call, 2025-07-23 13:30 PT](https://abc.xyz/investor/events/event-details/2025/2025-Q2-Earnings-Call/)
- [2025 Q3 call, 2025-10-29 14:30 PT](https://abc.xyz/investor/events/event-details/2025/2025-Q3-Earnings-Call-2025-4OI4Bac_Q9/default.aspx)
- SEC例: [2025 Q2 8-K（accepted 2025-07-23 16:01:33 ET）](https://www.sec.gov/Archives/edgar/data/1652044/000165204425000056/0001652044-25-000056-index.htm)、[2025 Q3 8-K（accepted 2025-10-29 16:01:48 ET）](https://www.sec.gov/Archives/edgar/data/1652044/000165204425000087/0001652044-25-000087-index.htm)

公式callページが日時と永続的なHTML/PDF transcriptを持つ。Q2・Q3のSEC acceptanceも追跡可能である。guidance本文を確実に利用可能とする時点には、公式call開始日時を使える。

### Amazon

- [2025 Q1 release, 2025-05-01](https://ir.aboutamazon.com/news-release/news-release-details/2025/Amazon-com-Announces-First-Quarter-Results/)
- [2025 Q2 release, 2025-07-31](https://ir.aboutamazon.com/news-release/news-release-details/2025/Amazon-com-Announces-Second-Quarter-Results/)
- [2025 Q3 release, 2025-10-30](https://ir.aboutamazon.com/news-release/news-release-details/2025/Amazon-com-Announces-Third-Quarter-Results/)
- SEC例: [2025 Q2 8-K（accepted 2025-07-31 16:13:17 ET）](https://www.sec.gov/Archives/edgar/data/1018724/000101872425000084/0001018724-25-000084-index.htm)

日付とSEC acceptanceは追跡できる。しかし3回の公式release / 8-K添付にあるforward guidanceは売上・営業利益で、通期CapEx guidanceを掲載しない。callは当日17:00 ETで公式webcastされたが、ページ記載の保存期間は少なくとも3か月で、今回確認した公式テキストだけでは当時の通期CapEx guidanceを3回再現できない。

### Meta

- [2025 Q1 release, 2025-04-30](https://investor.atmeta.com/investor-news/press-release-details/2025/Meta-Reports-First-Quarter-2025-Results/)
- [2025 Q2 release, 2025-07-30](https://investor.atmeta.com/investor-news/press-release-details/2025/Meta-Reports-Second-Quarter-2025-Results/)
- [2025 Q3 release, 2025-10-29](https://investor.atmeta.com/investor-news/press-release-details/2025/Meta-Reports-Third-Quarter-2025-Results/)
- SEC: [Q1 accepted 2025-04-30 16:16:00 ET](https://www.sec.gov/Archives/edgar/data/1326801/000132680125000050/0001326801-25-000050-index.htm)、[Q2 accepted 2025-07-30 16:13:01 ET](https://www.sec.gov/Archives/edgar/data/1326801/000162828025036719/0001628280-25-036719-index.html)、[Q3 accepted 2025-10-29 16:08:34 ET](https://www.sec.gov/Archives/edgar/data/1326801/000162828025047114/0001628280-25-047114-index.htm)

guidanceを含むreleaseが8-K Exhibit 99.1として残り、秒単位のSEC acceptanceをpoint-in-time利用可能時刻にできる。call時刻はQ1/Q2 17:00 ET、Q3 16:30 ETだが、release guidanceはそれ以前のSEC acceptanceで既に確認可能である。

## 5. 主要比較表

金額はUSD billion。ActualとGuidanceは混ぜずに記載する。

| Company / Disclosure | Published at | Actual CapEx | Full-year guidance | Definition / lease | 公式用途説明 | 前回比 | 比較可能性 / PIT |
|---|---|---:|---:|---|---|---|---|
| Microsoft FY26 Q1 | 2025-10-29、時刻未確認 | 34.9 | FY26はFY25より高い成長率（定性） | total CapEx。うちfinance leases 11.1、cash PP&E 19.4を別記 | GPU/CPU、Azure、first-party AI、R&D、更新投資、長期DC | 数値通期比較不能 | not comparable / Partial |
| Microsoft FY26 Q2 | 2026-01-28、時刻未確認 | 37.5 | Q3は前四半期比減（定性） | total CapEx。finance leases 6.7、cash PP&E 29.9 | 約2/3がGPU/CPU、AI利用、R&D、network更新 | 対象が次四半期 | not comparable / Partial |
| Microsoft FY26 Q3 | 2026-04-29、時刻未確認 | 31.9 | CY2026 約190（うち価格影響約25） | total CapEx。finance leases 4.7、cash PP&E 30.9 | GPU/CPU/storage、AI platform/apps/services、DC capacity | 年次数値の初回 | not comparable / Partial |
| Alphabet 2025 Q1 | 2025-04-24 13:30 PT | 17.2 | 約75 | reported CapEx / cash technical infrastructure。lease principal込みとは記載しない | servers、data centers、Google Services / Cloud / DeepMind | unchanged | exactly comparable / Yes |
| Alphabet 2025 Q2 | 2025-07-23 13:30 PT | 22.4 | 約85 | 同上 | 約2/3 servers、約1/3 DC/network。Cloud需要対応 | **raised 75→85** | exactly comparable / Yes |
| Alphabet 2025 Q3 | 2025-10-29 14:30 PT | 24.0 | 91–93 | 同上 | 約60% servers、40% DC/network、Cloud需要・TPU | **raised 85→91–93** | exactly comparable / Yes |
| Amazon 2025 Q1 | 2025-05-01、SEC/call時刻追跡可 | quarterly cash-flow actualあり | releaseにはなし | purchases of PP&E、sales/incentives、finance leaseを別項目で開示。guidance範囲との対応未確認 | releaseにはAI製品・AWS需要説明あり | unavailable | not comparable / Partial |
| Amazon 2025 Q2 | 2025-07-31 16:13:17 ET（SEC） | purchases of PP&E 32.183 | releaseにはなし | 同上 | AWS、AI zones、cloud/AI infrastructure投資 | unavailable | not comparable / Partial |
| Amazon 2025 Q3 | 2025-10-30、call 17:00 ET | purchases of PP&E 35.095 | releaseにはなし | 同上 | AI/core infrastructure需要、capacity追加 | unavailable | not comparable / Partial |
| Meta 2025 Q1 | 2025-04-30 16:16:00 ET（SEC） | 13.69 | 64–72 | purchases of PP&E **+ finance lease principal** | AI向け追加DC、hardware cost。大半はcore business | **raised 60–65→64–72** | exactly comparable / Yes |
| Meta 2025 Q2 | 2025-07-30 16:13:01 ET（SEC） | 17.01 | 66–72 | 同上 | AI effortsとbusiness operations向けcapacity | **narrowed/raised floor 64→66** | exactly comparable / Yes |
| Meta 2025 Q3 | 2025-10-29 16:08:34 ET（SEC） | 19.37 | 70–72 | 同上 | infrastructure capacity、own buildとthird-party cloud、AI models/products | **raised floor 66→70** | exactly comparable / Yes |

MicrosoftのCY2026約190はFY26 Q1/Q2の定性guidanceと同一対象年度の連続値ではない。Amazonについて、二次資料で流通するcall上の年次数字を公式保存テキストで確認できないため採用しない。

## 6. CapEx定義、lease、actual vs guidance

- **Microsoft:** `Capital expenditures`はfinance leasesを含むtotalを示し、cash paid for PP&Eを別掲する。四半期ごとにlease開始時の全額認識で振れ得る。Actualの34.9→37.5→31.9をFY guidance変更と解釈しない。
- **Alphabet:** IRのreported CapExはtechnical infrastructure中心のcash CapExとして説明される。会社間比較用にMeta型のfinance lease principal込みへ変換しない。
- **Amazon:** cash flowのpurchases of PP&E、proceeds/incentives、finance leases、financing obligationsが別々に存在する。公式releaseに連続した年次guidanceと定義対応がないため差額を出さない。
- **Meta:** guidanceとactualはいずれもpurchases of PP&Eにprincipal payments on finance leasesを加えた定義を明示する。3開示はexactly comparableである。

4社合計や会社間ランキングは、leaseと認識基準が違うため作らない。総CapExをAI専用額とせず、AI比率も推定しない。

## 7. AI / Data Center公式説明と当アプリ側の推論

### 企業が公式に説明した事実

- Microsoft: GPU/CPU、storage、datacenter、Azure需要、first-party AI、R&D、network更新を同じCapEx内で説明する。
- Alphabet: servers、data centers、networking、Google Cloud需要、Google DeepMindを含むtechnical infrastructure。Q2の引上げ理由はserver追加・納入時期・DC建設加速。
- Amazon: AWSのAI/core infrastructure需要、Trainium等を説明するが、総CapExにはstores、robotics、satellite等も含み得る。
- Meta: AI efforts向けDC・hardware、core business、own infrastructure、third-party cloudを説明する。

### 当アプリ側の仮説

公式説明からAI専用金額は得られない。採用する場合の仮説は、server / accelerator / memory / networking / data-center capacityの計画変更が、後続するTaiwan Orders、Korea Exports、日本の生産・装置・在庫を確認する上流の観測点になる、という範囲に限定する。

東京エレクトロンはwafer fab equipment、アドバンテストはtest、ディスコはcutting / grinding / packaging周辺、キオクシアはmemory / storageという既存の事業経路を確認対象にできる。ただし「特定企業のCapEx増加が特定日本株を上昇させる」とは言えない。

## 8. 既存台湾・韓国情報への追加価値

| Company | 追加情報 | 判断理由・次の確認事項を変えるか |
|---|---|---|
| Microsoft | AI infrastructureの構成とcapacity制約は詳しいが、同一年次guidance変更を連続測定できない | 背景説明には有用。定量的な変更イベントとしては採用条件を満たさない |
| Alphabet | 75→85→91–93と同一年内に増額し、servers/DC/networkとCloud需要を公式説明 | 台湾・韓国の実需が弱い時でも、上流計画が維持・増額かを反証条件として追加できる |
| Amazon | AWS需要の背景説明は増えるが、公式保存テキストから連続年次guidanceを再現できない | 手作業のcall確認に依存し、既存情報を超える再現可能な観測点にならない |
| Meta | 同一定義レンジの下限引上げとAI/DC理由を同時に追跡可能 | 上流capacity planの変化を明確な次回確認事項として残せる |

追加価値は台湾・韓国を置換することではなく、計画（Big Tech）→受注（台湾）→輸出（韓国）→日本の生産・装置という時間順のうち「計画」を説明することである。採用2社でも計画と実需が乖離する可能性を明示する。

## 9. Decision Logでの利用候補

コードやschemaは変更しない。既存の自由記述で以下のように利用できる。

- 判断理由・コメント: 「Alphabetの同一CY guidanceが増額。ただし台湾受注で未確認」
- review condition: 「次回Alphabet/Meta決算で同一年度guidanceの維持、定義変更、AI/DC用途を確認」
- 反証条件: 「guidance lowered、definition changed、または台湾・韓国の後続実需が改善しない」

現行SnapshotにBig Tech値を自動追加する価値はまだ検証されていない。まず手動コメント／review conditionとして前向きに有用性を観察する。

## 10. 継続更新負荷と自動化可能性

| Company | 公式資料数/回 | 所在・形式 | 例外と人手確認 | 負荷 |
|---|---:|---|---|---|
| Microsoft | call transcript + release/SECの2前後 | 規則的なIR HTML | target FY、quarter/annual、lease mixを毎回判定 | Medium–High |
| Alphabet | call HTML/PDF + 8-Kの2 | 規則的、transcript継続 | guidance値、server/DC mix、call時刻を確認 | Low–Medium |
| Amazon | release/8-K + webcastの2～3 | releaseは規則的、webcast保存は有限 | 年次CapEx発言とlease範囲の手動確認が必要 | High |
| Meta | release/8-Kの1～2 | 規則的HTML、guidance位置も安定 | rangeとlease定義変更を確認 | Low |

実測していない作業時間は記載しない。公式IR / SECだけでAlphabetとMetaの問いには答えられ、有料データは不要である。Microsoft/Amazonを成立させるための有料契約も提案しない。

## 11. 会社別採否

### Microsoft — DO NOT ADOPT

原資料、日付、Actual、AI用途は追跡できる。しかし選定した3回では同一対象年度の数値CapEx guidanceが2回以上なく、FY/quarter/CYを混ぜない限りguidance changeを作れない。背景資料としては優秀でも、今回の機能要件には不適合。

### Alphabet — ADOPT

同一CY2025、同じreported CapExについて75→85→91–93を公式transcriptで再現でき、call日時も確認できる。server / DC / networkingとCloud・DeepMind需要の公式説明があり、台湾・韓国より上流の計画変更として追加価値がある。更新負荷は許容範囲。

### Amazon — DO NOT ADOPT

日付、SEC acceptance、Actual、AWS/AI用途は確認できる。一方、3回の公式release / 8-K添付は通期CapEx guidanceを継続掲載せず、期間限定webcastの人手確認に依存する。今回の公式保存テキストだけでは条件2・3・6を満たさない。別archive探索は行わない。

### Meta — ADOPT

同一CY2025、同一定義（finance lease principal込み）の64–72→66–72→70–72を8-K添付で再現でき、SEC acceptanceが利用可能時点になる。AI/DC capacityの公式理由、既存実需への追加価値、低い更新負荷を満たす。

## 12. 全体判定: 限定GO

AlphabetとMetaに限れば、point-in-time追跡、同一年度比較、定義説明、AI/DC用途、既存情報への追加価値、継続更新性を満たす。したがって「全4社統一機能」ではなく、**2社だけの小さなリサーチ機能を次に要件検討する価値がある**という限定GOとする。

今回、実装へは進まない。ユーザー判断なしにloader、UI、Decision Log連携、自動更新を開始しない。

## 13. GOの場合の最小機能候補

実装を別途承認する場合も、最初はAlphabet / Metaだけを対象にする。

1. 企業、開示日時、target FY、actual、guidance、定義、lease treatment、公式用途、source URLを持つ小さな手動更新データ。
2. 同一企業・同一FY・同一定義だけで `raised / lowered / unchanged / definition changed / not comparable` を表示。
3. AI専用額、会社横断合計、momentum score、売買シグナルを作らない。
4. Decision Logのschemaへ接続せず、当面は既存コメント／review conditionで前向きに利用価値を確認。

## 14. 停止理由と再調査条件

MicrosoftとAmazonは今回DO NOT ADOPTで終了する。Microsoftが同一定義の年次数値guidanceを2回以上継続開示する、またはAmazonが年次CapEx guidanceと定義を永続的な公式release / SEC添付へ継続掲載する場合のみ再調査条件が成立する。別API、ベンダー、archive、OSSは探索しない。

残る未解決事項は、採用2社のguidanceが実際にDecision Logの理由・反証条件を改善するかである。これは過去2～3事例の株価で判定せず、運用時の前向き観察でのみ評価する。
