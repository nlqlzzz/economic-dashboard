# Decision Log MVP セットアップ

## 目的

Core20について、その時点で確定した人間の投資方針と分析Snapshotを追記保存し、後日の個別株・TOPIX連動ETFのリターンで前向きに検証します。判断は注文・約定・保有数量・実現損益とは別物です。「実判断」も実際に約定したことを意味しません。

## 1. Supabaseテーブルを作成する

1. 個人用Supabase Projectを用意します。
2. Supabase DashboardのSQL Editorを開きます。
3. [`supabase/migrations/202609140001_create_investment_decisions.sql`](../supabase/migrations/202609140001_create_investment_decisions.sql)の全内容を貼り付け、1回実行します。
4. `public.investment_decisions`が作成されたことをTable Editorで確認します。

Migrationは判断区分、20/60/120営業日、理由タグ、判断モード、Human source、正の参考価格、JSON objectにDB制約を設けます。過去判断は更新せず、新しい行を追加します。将来の訂正は`supersedes_decision_id`で関連付けられる構造です。

## 2. Streamlit Secretsを設定する

Streamlit Community CloudのApp settings > Secrets、またはローカルの`.streamlit/secrets.toml`へ次を設定します。

```toml
SUPABASE_URL = "https://YOUR_PROJECT.supabase.co"
SUPABASE_SECRET_KEY = "YOUR_SUPABASE_SECRET_KEY"
DECISION_LOG_PASSWORD = "YOUR_LONG_UNIQUE_PASSWORD"
```

名前とダミー値は[`.streamlit/secrets.example.toml`](../.streamlit/secrets.example.toml)にもあります。実際のSecret KeyとPasswordをGitHub、Issue、PR、ログ、スクリーンショットへ置かないでください。`SUPABASE_SECRET_KEY`はStreamlitサーバー内だけで使用し、HTMLやブラウザへ渡しません。

## 3. RLSとアクセス方針

MigrationはRLSを有効化・強制し、`anon`と`authenticated`の権限を剥奪します。これらのrole向けpolicyは作成しません。ブラウザ側のPublishable/anon Keyからは直接読み書きできません。`service_role`の既存権限も一度剥奪し、サーバー側のSecret Keyには`select`と`insert`だけを付与します。DBと通常UIの双方で更新・削除経路を設けない追記型です。

Supabase AuthはMVPでは使いません。`DECISION_LOG_PASSWORD`は1人利用の簡易ゲートであり、本格的な利用者認証ではありません。認証成功状態だけをStreamlit sessionへ保持し、入力されたパスワード自体は不要になった時点でsession stateから除去します。

## 4. 判断時点Snapshot

登録時に、その画面で利用できた次の情報を小さなJSONとして複製保存します。後日に最新データから当時の状態を再計算しません。

- Snapshot schema versionと取得日時
- 品質処理済み参考価格、価格基準日、1・3か月の絶対／TOPIX比リターン
- Fundamentals取得状態、Fiscal Year / Quarter、開示日、業績Momentum
- 利用可能な会社予想の対象期と主要値
- 評価水準の状態
- 投資上の確認事項とデータ制約
- Market Betaと主要Primary Driver表示値

巨大な価格SeriesやDataFrameは保存しません。Snapshotは当時の画面情報の記録であり、データベンダーの完全なpoint-in-timeデータを保証するものではありません。

## 5. 前向き検証

登録時の個別株と1306.Tは、品質処理後に共通して存在する最新日次終値を参考価格とします。これは約定価格ではありません。

- 1か月: 20営業日
- 3か月: 60営業日
- 6か月: 120営業日

1306.Tの判断基準日後20・60・120番目の取引観測日を共通終点とし、個別株にも同じ日付の価格がある場合だけ両リターンとTOPIX超過を計算します。未到来は「評価待ち」、品質停止・長期欠損・共通終点の価格欠損は「評価不能」です。後日の別価格へ飛ばして代用しません。後日の株式分割やデータ改定等で現在系列の基準日価格が保存値から大きく変わった場合も、補正係数を推測せず評価不能にします。

「判断方向との整合（参考）」は、買う／保有継続ならTOPIX超過が正、売却／見送りなら負かだけを示します。正解・成功・利益ではなく、絶対リターン、リスク、機会費用、手数料を含みません。売却や見送りを空売り損益へ変換しません。

## 未設定・障害時

3つのSecretsのいずれかがなければ「Decision Logは未設定」と表示し、登録・履歴だけを停止します。Supabase障害もDecision Log内で短いエラーにし、日本株分析や他画面は継続します。ローカルファイルへの自動fallbackはありません。
