# 市場ダッシュボード

FRED、Yahoo Finance、財務省の公開データをまとめて確認するStreamlitアプリです。市場指標の比較、騰落率、急変検知、相関分析、米国経済イベント、米国マクロ局面などを表示します。

## ローカルで起動する

リポジトリのルートで次を実行します。

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
streamlit run app.py
```

テストと構文確認:

```powershell
python -m unittest -v
python -m py_compile app.py
```

main向けPRとmainへのpushでは、GitHub Actionsの`CI` workflowがPython 3.12で依存関係確認、全単体テスト、全Pythonファイルの構文検査を実行します。CIは外部データ取得やSecretsを使用せず、APIレスポンスはテスト内の固定データ・モックで検証します。

## Streamlit Community Cloudのデプロイ設定

このアプリのデプロイ座標は次のとおりです。

| 項目 | 設定値 |
| --- | --- |
| Repository | `nlqlzzz/economic-dashboard` |
| Branch | `main` |
| Main file path | `app.py` |
| Python dependencies | ルートの`requirements.txt` |

Community Cloudはリポジトリのルートを作業ディレクトリとしてアプリを実行します。`app.py`と`requirements.txt`はルートに置いたままにしてください。

## 更新を反映する手順

1. 機能ブランチのPRが`main`へマージ済みかGitHubで確認する。
2. PRのマージコミットに、変更対象のファイルが含まれているか確認する。
3. Community Cloudのアプリ設定が、上記のRepository、Branch、Main file pathを指しているか確認する。
4. アプリを開き、数分待ってから再読み込みする。
5. 反映されない場合はCloudログを確認する。
6. ログに明確なエラーがなく、古いコードやキャッシュが残っている疑いがある場合だけRebootする。

データ取得には最大6時間のキャッシュがあります。画面構成やコードが更新済みでも値だけ古い場合は、コードのデプロイ失敗ではなくデータキャッシュの可能性があります。

## Cloudログを確認する

デプロイ済みアプリの右下にある`Manage app`からログを開きます。次を順に確認します。

- GitHubから最新コミットを取得できているか
- `requirements.txt`のインストールに失敗していないか
- `app.py`のimport・構文エラーがないか
- FRED、Yahoo Finance、財務省への接続エラーがないか
- 起動後に例外で停止していないか

依存関係を追加・変更した場合は、Pythonのimportだけでなく`requirements.txt`も同じPRに含めます。

## Reboot手順

Rebootは利用中のユーザーを一時的に切断し、再デプロイに数分かかる場合があります。

### Workspaceから

1. [Streamlit Community Cloud](https://share.streamlit.io/)を開く。
2. 対象アプリのメニュー（`⋮`）を開く。
3. `Reboot`を選択する。
4. 確認画面でもう一度`Reboot`を選択する。

### デプロイ済みアプリから

1. アプリ右下の`Manage app`を開く。
2. メニュー（`⋮`）から`Reboot app`を選択する。
3. 確認画面でRebootを実行する。

Reboot後はCloudログで依存関係のインストールと`app.py`の起動完了を確認します。

## Secretsの扱い

- APIキーや認証情報をGitへコミットしないでください。
- ローカル用の`.streamlit/secrets.toml`と`.env`は`.gitignore`対象です。
- CloudでSecretsが必要になった場合は、アプリの`Settings` → `Secrets`へ登録します。
- エラー報告やログ共有の前に、トークン、Cookie、URLパラメータなどの機密情報が含まれていないか確認します。

日本半導体テーマの「半導体製造装置受注」には、e-Stat APIのアプリケーションIDが必要です。ローカルでは`.streamlit/secrets.toml`、Community CloudではアプリのSecretsへ次の形式で登録します。

```toml
ESTAT_APP_ID = "取得したアプリケーションID"
```

環境変数`ESTAT_APP_ID`でも設定できます。値そのものはGit、画面、エラーログへ記録しないでください。

## 公式ドキュメント

- [Deploy your app on Community Cloud](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy)
- [App dependencies](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/app-dependencies)
- [Reboot your app](https://docs.streamlit.io/deploy/streamlit-community-cloud/manage-your-app/reboot-your-app)
- [App settings](https://docs.streamlit.io/deploy/streamlit-community-cloud/manage-your-app/app-settings)
