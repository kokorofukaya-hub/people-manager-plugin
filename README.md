# People Manager

**Slack IDとNotion URLを登録し、本人の業務活動、1on1の準備メモ、月次レポートを管理するプラグインです。** インターン・社員などの区分を問わず、特定の人との面談を担当する運用者向けです。ローカルMarkdownを正本にし、Notionには確認済みの活動記録を初回作成で反映します。

## できること

| 機能 | 入力 | 結果 |
|---|---|---|
| setup | Slack ID、Notion URL | 人物・保存先・接続権限の確認とローカル設定 |
| collect | 接続済みのSlack・Notion | 本人の公開発言、参加確認済みprivateチャンネルの業務発言・成果物を保存 |
| meeting-import | 指定したNotion議事録またはローカルファイル | 話者・日付・参加者・逐語録をローカルへ保存 |
| 1on1-prep | ローカルの目標・直近14日の活動・最新議事録 | 事実と運用者の解釈を分けた6章の準備メモ |
| monthly | 指定月または前月の活動ログ | 出典付き月次レポートとNotionへの初回反映 |
| status | ローカル設定・実行状態 | 欠測、未反映、保留、定期実行の確認状況 |

議事録の録音・音声認識は提供しません。議事録を取り込んだ後の1on1準備は、ローカル資料だけで実行できます。

## 最短導入

Python 3.9以上を利用できる環境と、使用するAIホストに接続済みのSlack・Notionが必要です。追加のAPIトークン、専用MCPサーバー、Supabaseは不要です。接続先の権限や検索・ページング機能は、setupで確認します。

Codexでは、リポジトリへアクセスできるアカウントで実行します。

```sh
codex plugin marketplace add https://github.com/kokorofukaya-hub/people-manager-plugin --json
codex plugin add people-manager@people-manager-plugins --json
```

Claude Codeでは、次を実行します。

```text
/plugin marketplace add kokorofukaya-hub/people-manager-plugin
/plugin install people-manager@people-manager-plugins
```

導入方法は[Codexの公式プラグイン案内](https://developers.openai.com/plugins/build/plugins)と[Claude Codeの公式プラグイン案内](https://code.claude.com/docs/en/discover-plugins)でも確認できます。privateリポジトリの閲覧権限がない場合は、先にリポジトリへのアクセスを確認してください。

導入後、個人記録を保存するワークスペースを開き、次の依頼を貼り付けます。

```text
People Managerのsetupを使ってください。
対象者のSlack ID: <対象者のSlack ID>
Notion URL: <人物行または管理ポータルのURL>
個人記録は、このワークスペースの.people-managerに保存してください。
SlackプロフィールとNotionの保存先を確認し、曖昧な項目だけ質問してください。
まずobserveで確認し、通知と定期実行は登録しないでください。
```

2つの入力から確認を始めます。Notionの人物行・活動ログDB・本人のNotionユーザーID・議事録置場を一意に識別できない場合は、その項目だけ追加で確認します。任意のURL1つからすべての保存先を解決できるとは限りません。

## 初回確認から運用へ

1. setupの結果で、Slackプロフィール、対象者の人物行、活動ログDB、本人のNotionユーザーIDを確認します。
2. `collectをobserveで実行して`と依頼し、取得範囲と欠測理由を確認します。
3. 設定を確認したら、`People Managerをonにして、今回の活動を収集・保存して`と依頼します。Notion反映も必要なら、`確認した活動ログDBへNotion反映もして`と指定します。
4. 必要な議事録を取り込み、`対象者の1on1-prepを作って`、`前月のmonthlyを作って`と依頼します。

helperの初期モードは`off`です。setupへの依頼で`observe`を明示すると読み取り確認を始められます。`observe`・`dry-run`では活動ログや実行stateを更新しません。通知は既定で無効です。

通常privateチャンネルは、運用者本人の参加が当該実行で確認できた場合だけ収集します。必要な場合は運用者Slack IDを追加指定してください。通知の有効化とは別の設定です。定期起動はホストのスケジューラーへ別途登録します。

## 保存されるもの

```text
<利用者のワークスペース>/.people-manager/
├── config.json
├── state.json
└── members/<Slack ID>/
    ├── goals.md
    ├── activity/YYYY-MM.md
    ├── meetings/
    ├── prep/
    └── monthly/
```

Slack IDを固定の`member_id`として使います。表示名が変わっても記録の識別子は変わりません。個人記録はプラグインのインストールキャッシュへ保存せず、ワークスペースの`.people-manager/`をGit管理から除外します。

| モード | 動作 |
|---|---|
| off | 対象処理を停止 |
| observe | 読み取り・確認結果の表示まで |
| dry-run | 保存予定の本文・操作を表示まで |
| on | ローカル保存。Notionは保存先確認済みかつ反映操作の依頼がある場合だけ |

Slack・Notionの必須収集元が不完全な回は保存カーソルを進めません。権限不足や検索未完了を「活動0件」に変換せず、取得できた範囲と未確認を表示します。

## 共有と通知

Notionの人物ページはプロフィール、活動ログDBは日々の事実と月次レポートに使います。活動から性格・目標・参加目的を推測して人物プロフィールを書き換えません。

Notion反映は固定キーで既存ページを確認するcreate-onlyです。helperに反映専用スイッチはなく、ローカル保存時にpendingを記録します。反映操作の依頼がなければpendingを保持します。

作成結果が不明な場合は現物を検索して照合し、確認前に再作成しません。話者不明の発言やAI要約を本人の発言根拠にせず、非公開面談の内容は活動ログDB・月次レポートへ転載しません。

対象者のDM本文は収集しません。対象者へのDM・チャンネル通知も行いません。通知が必要な場合は、対象者と異なる運用者IDと通知設定を明示してください。

## 定期実行と確認範囲

活動収集は48時間おき、月次は毎月1日09:00（Asia/Tokyo）を設定案としています。手動運用はSlack・Notionの2コネクターで始められます。

1on1の30分前に自動準備するには、追加でCalendar接続、対象者メールアドレス、ホストの定期実行機能が必要です。インストール成功、予定登録成功、実際の定期実行成功は別々に確認します。

Notionへ送る本文だけ、可視の管理IDと本文1個のテキストコードブロックで包みます（`notion-plain-v1`）。Notionではテキストとして読み、ローカルではMarkdownを維持します。読み戻しは改行コード、コードブロック外の空行、限定した言語名の違いだけを正規化し、ブロック内の本文・空白・空行は厳密に照合します。未知の変換や人の追記は保留します。本文内にコードフェンスがある場合も、作成前に停止します。

この配布物の本番Slack・Notion連携、通常画面でのプラグイン導入、定期実行の完走は未検証です。

ローカルhelperの検証結果を本番連携の成功として扱わないでください。未保存の収集時に生じた欠測は実行時に表示し、statusから過去の欠測履歴を復元できるとは限りません。

## 次のアクション

まずsetup用の依頼文で対象者を登録してください。取得範囲・保存先を確認した後、手動の初回収集で読み戻しまで確認します。定期実行の設定手順は[定期実行の参照文書](references/scheduling.md)にあります。
