# 経済イベントカレンダーの更新手順

米雇用統計、米CPI、FOMC政策金利発表の日程は、`config/us_economic_events.json`で管理します。アプリ本体へ日付を直接追加しないでください。

## 更新手順

1. [BLS Release Calendar](https://www.bls.gov/schedule/)と[FOMC Calendars](https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm)で公式日程を確認する。
2. `events`へ公表日、`event_type`、`source`を追加し、全出所を通して日付の昇順に並べる。
3. 各出所の`coverage_end`を、その出所の最終収録日と一致させる。
4. 公表時刻またはタイムゾーンが公式情報で変更された場合だけ、出所設定の`release_time`または`timezone`を変更する。
5. `python -m unittest -v test_economic_calendar.py`と全単体テストを実行する。
6. 画面の収録期限、日本時間、公表元リンクを確認し、1回の更新を1つのPRにする。

検証処理は、未対応のイベント種別、出所の不一致、不正な日付・時刻、重複、並び順、収録期限の不一致をアプリ起動時とテスト時に検出します。米国東部時間から日本時間への変換にはタイムゾーン情報を使うため、夏時間と標準時間を固定の時差で扱いません。

BLSの翌年日程は公式掲載後に追加してください。FOMCの将来日程は変更される可能性があるため、更新時に公式ページと照合してください。市場予想値は公式日程データには含まれないため、信頼できる取得元と利用条件を確認できるまで表示しません。
