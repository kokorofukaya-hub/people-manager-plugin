# 接続・保存先の契約

setupと外部読み取り・Notion反映の前に、必要な節だけ読む。AIホストの接続済みツールで読み書きし、Python helperはローカル検査・保存を担当する。helperは外部認証や通信を担当しない。

## ワークスペースと識別子

- `<workspace>`は利用者が個人記録を保存すると決めたワークスペースの絶対パス。
- `<plugin-root>`は使用中SKILL.mdの2階層上。既存の会社ディレクトリや開発者の絶対パスを前提にしない。
- 保存先は`<workspace>/.people-manager/`。インストールキャッシュへ個人設定・活動・議事録を保存しない。
- `member_id`はSlack ID。Slackプロフィールの表示名は見せ方に使い、人物の一意識別に使わない。
- config/stateと個人資料はGit管理から除外する。追加トークン・秘密値を保存しない。

## 接続済みツールの確認

ホストで使えるSlack・Notionツールを確認し、実際の引数仕様で操作する。別ホストのツール名・検索フィルター・ページング方式をそのまま実行しない。

| 用途 | 必要な機能 | 機能がない場合 |
|---|---|---|
| Slack本人確認 | IDによるプロフィール取得 | 表示名未確認としてsetupを保留 |
| Slack収集 | 投稿者指定、チャンネル種別、運用者の参加確認、投稿時刻、全文・URL、ページング | 対応しない範囲をunsupported/partialとして保存を保留 |
| Notion本人確認 | 人物行・親DB・子DB・relationとschemaの取得 | 該当保存先だけ追加確認 |
| Notion収集 | 本人帰属、作成・活動時刻、ページURL、必要範囲のページング | 本人帰属または範囲未確認として保存を保留 |
| Notion反映 | 既存行の検索、実data sourceへの作成、本文・relation・親の読み戻し | ローカル保存まで。反映を未実行として残す |
| 議事録取込 | 指定ページのTranscript・日付・参加者の取得 | ローカル逐語録を指定するか不足を確認 |

権限不足はmissing、未完備はpartial、機能がない場合はunsupportedとする。completeは「明示した範囲を、本人帰属・ページングまで確認できた」という意味であり、ワークスペース内の全情報を取得したという保証ではない。

## Notion URLから解決する順序

1. ユーザーが指定したURLを取得し、管理ポータルか人物DBの行かを確認する。
2. ポータルなら、配下の人物DB・活動ログDB・議事録置場を確認する。人物行なら、親人物DBと既存のポータルへの参照を確認する。
3. 指定Slack IDに一致する既存プロパティ、確認済みrelation、またはユーザーが指定した人物行から対象を一意に決める。表示名の類似やページの`created_by`から決めない。
4. 活動ログDBの実data source、人物行へのrelationプロパティ、既存のtitle/date等の書き込み可能なプロパティを確認する。viewのURLを作成先として使わない。
5. 本人のNotionユーザーIDを別途確認し、活動ページの本人帰属に使う。人物ページの作成者を本人のNotionアカウントとみなさない。
6. 議事録置場が必要な場合だけ、指定rootを確認する。ポータルから見つからなければ、その置場またはローカルファイルの指定を確認する。

一意に決まらない項目だけ質問する。権限がない人物ページと、活動ログのrelationが書き込めるかどうかは別々に確認する。必要DB・列がなければ、その不足を説明し、自動追加しない。

## Notion反映の共通条件

ローカル保存後、Notion反映操作が依頼された場合だけ、確認済み活動ログDBへ作成する。mode=on、activity保存先status=ready、member_page_url確認済み、inspectの作成許可が必要。人物DB・プロフィールには日次活動や月次レポートを作らない。

helperにはNotion反映専用のon/off設定がない。ローカル保存時にpendingを記録し、操作依頼がなければその状態を保持する。保存先missingは未解決であり、明示的な反映offの代用にしない。

| 種別 | 固定キー |
|---|---|
| 活動 | `people-manager:activity:<member_id>:<YYYY-MM-DD>` |
| 月次 | `people-manager:monthly:<member_id>:<YYYY-MM>` |

作成前に、活動ログDBの同じキーを本人relationと合わせて検索する。一意な一致は本文まで読み戻し、内容が一致する場合だけ採用する。複数一致、別親、別人物、本文不一致は保留する。

新規作成は既存がないことを完全検索で確認できた場合だけ行う。ローカル本文は保持し、Notion作成にはinspectが返す`expected.body`をそのまま使う。helperが可視Management ID行と1個のliteral text codeblockへ包んだ送信本文である。作成後、親data source・対象者relation・キー・本文を独立fetchし、限定adapterで照合する。

作成リクエストの成功応答だけでは反映完了にしない。結果が不明なら再作成せず同じキーで現物検索する。既存本文・プロパティはcreate-onlyとして機械で上書きしない。

Notionの見た目だけを確認せず、実fetchの管理本文を照合する。`notion-plain-v1`はCRLF/CRをLFへ、code外の空行だけを除去し、bare/text/plain text/plaintextのfence labelだけを同じplain形式として扱う。code内の行・空行・空白・マークアップ・URLは変更しない。可視Management IDとcodeblock1個以外の非空行、人の追記、未知markupはheld。原文に既存fenceがあれば作成前に保留する。送信本文で読み戻しを代用しない。

## record-mirrorの入力と順序

ローカル正本を保存した後、実際のNotion検索結果を次の入力にする。例のID・URLは架空。`kind`はactivityまたはmonthly、`period`は日付または年月。

```json
{
  "member_id": "U123EXAMPLE",
  "kind": "activity",
  "period": "2026-10-07",
  "outcome": "inspect",
  "search": {
    "status": "complete",
    "pagination_complete": true,
    "key": "people-manager:activity:U123EXAMPLE:2026-10-07",
    "source_id": "confirmed-activity-data-source-id",
    "scope": ["指定data source内の同じ固定キーを検索"],
    "evidence": ["全ページング終端を確認。該当なし"],
    "matches": []
  }
}
```

```sh
python3 "<plugin-root>/scripts/people_manager.py" --workspace "<workspace>" record-mirror --input "<反映結果JSON>"
```

1. **inspect**：完全検索結果を渡す。一致0件かつ未作成なら、helperがstateへcreatingを保存し、`can_create: true`を返す。この返却がない場合は作成しない。
2. **作成**：許可された1回のconnector作成を行う。helperが返した`expected`のsource_id・relation・properties・キーに合わせ、`expected.body`をそのまま送る。
3. **created**：作成したpage_idと独立fetchのreadbackを渡す。親・relation・キー・propertiesの完全一致、可視キーの一致、限定canonicalの一致、完全取得の証跡が揃った場合だけconfirmedになる。成功応答だけ、または送信値のechoは読み戻しとしない。
4. **unknown**：作成応答不明・作成直後停止ならunknownを記録する。creating/unknownの再inspectは2回目の作成許可を返さない。
5. **reconcile**：creating/unknownからは、同じキーを完全検索して現物を確認する。一致1件はreadbackと照合、0件はpendingに戻る。その後の新しいinspectが許可した場合だけ再作成できる。
6. **failed**：確認できた失敗を記録し、結果不明のcreating/unknownを消さない。結果不明を未作成に変換しない。3回失敗でheldとなる。

`expected`のコード契約は`source_id`、`relation`、`key`、`properties`、`local_body_sha256`、`adapter: notion-plain-v1`、送信用`body`、`sent_body_sha256`、`canonical_sent_sha256`。先頭の可視行は`Management ID: <key>`、その後はblankとliteral text codeblock1個であり、codeblock内に保存済みローカル全文を含む。

`matches`の各pageと`readback`は`page_id`、`source_id`、`relation`、`key`、`properties`、独立fetch由来の`body`、その実raw本文の`body_sha256`を持つ。propertiesは`expected.properties`と完全一致する形に照合する。page.keyだけに依存せず、helperがbody先頭の可視Management IDも解析する。

readbackには次のfetch証跡も渡す。例の時刻・証跡は実際の独立取得結果に置き換える。`truncated`、`unknown_block_count`、`unknown_block_ids`は元fetchの値を確認し、矛盾するcompleteラベルを作らない。

```json
{
  "fetch": {
    "status": "complete",
    "pagination_complete": true,
    "independent": true,
    "method": "connector-fetch",
    "fetched_at": "2026-10-07T09:01:00+09:00",
    "evidence": ["実際の独立fetchの呼出IDと全本文取得の根拠"],
    "truncated": false,
    "unknown_block_count": 0,
    "unknown_block_ids": []
  }
}
```

bodyはconnectorで独立取得した管理本文からlosslessに抽出し、helperがそのrawと限定canonicalを別々にhashする。送信rawと実fetch rawのhashは同一でなくてもよい。送信hashを実fetch hashへ転記しない。広い意味正規化、見た目の類似、タグや未知blockの削除は行わない。

stateには元localの`body_sha256`、送信の`sent_body_sha256`、実fetchの`fetched_body_sha256`、`canonical_sent_sha256`、`canonical_fetched_sha256`、`adapter`、`fetched_at`、`fetch_evidence`を別保存する。confirmed済みでも今回のsearch/readbackがあれば再検証し、消失・追記・複数一致・不一致をheldにする。source・relation・propertiesの設定変更も、過去のbindingと元page_idを残してheldにする。

標準Notion MCPとのlive roundtripは未検証。限定変換以外を必要とする返却やcode内原文を完全取得できない接続は、反映未確認として保留する。

状態はpending／creating／unknown／confirmed／held。複数一致、親・人物・プロパティ・キー・本文の不一致はheld。heldは自動再試行せず利用者へ返す。既存confirmedは再作成・上書きしない。

## setup断片と設定変更

setupの`--input`には、その人の解決結果と共通設定の断片を渡す。次は架空の形式例で、URL・ユーザーID・sourceは実際の読み取りで確認した値に置き換える。

```json
{
  "mode": "observe",
  "display_name": "対象者の確認済み表示名",
  "active": true,
  "notion_user_id": "confirmed-notion-user-id",
  "member_page_url": "https://www.notion.so/11111111111111111111111111111111",
  "meeting_roots": [],
  "notion_targets": {
    "activity": {
      "status": "ready",
      "unique": true,
      "source_id": "confirmed-activity-data-source-id",
      "properties": {}
    }
  },
  "notification": {"mode": "off"}
}
```

`notion_targets.activity.properties`は既存DBで照合した固定プロパティ値を持つ。キー・対象者・期間・種別の動的値はhelperの`expected.properties`に追加される。AIは実schemaに合わせてそれらを写像し、読み戻しも同じ形式で確認する。

保存先が未解決ならactivityの`status`を`missing`にし、解決済みと偽らない。setupの任意項目は`timezone`、`mode`、`notion_targets`、`notification`、`display_name`、`active`、`notion_user_id`、`member_page_url`、`meeting_roots`。

設定変更は既存config全体を読み、必要な値だけ変更したJSONをconfigureへ渡す。登録者のID集合を変えず、保存stateを保持する。追加登録はsetupを使う。

```sh
python3 "<plugin-root>/scripts/people_manager.py" --workspace "<workspace>" configure --input "<更新したconfig全体のJSON>"
python3 "<plugin-root>/scripts/people_manager.py" --workspace "<workspace>" validate-config
```

通常privateチャンネルも収集する場合は、通知offのまま`notification.operator_slack_user_id`を設定できる。通知を有効にする場合は、`mode: on`と同じ運用者IDの`destination_slack_user_id`を明示する。

## 通知

通知は既定で無効。対象者へのDM・チャンネル通知は行わない。必要な場合は、対象者と異なる運用者のSlack IDと通知許可を明示的に設定する。

運用者向けの通知は保存結果・取得範囲・欠測・参照先に絞り、私的DMや面談Transcriptを本文へ載せない。ホストとユーザーの送信ルールに従い、設定値だけで未承認の送信を開始しない。

## 次のアクション

解決した人物・data source・relation・本人NotionユーザーIDを設定に記録し、validate-configを実行する。未解決はそのまま報告し、取得結果で補完したことにしない。
