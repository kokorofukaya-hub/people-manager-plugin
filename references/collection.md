# 活動収集

collectの実行時に読む。本人の業務発言・成果物を収集し、ローカルを正本として保存する。解釈・能力評価・目標の書き換えは含めない。

## 固定ウィンドウ

実行開始時刻を一度だけ確定し、helperのwindowでcutoffを分単位に切り下げる。取得範囲は`start <= happened_at < cutoff`。処理途中の現在時刻で上限を動かさない。

通常は最後に保存できたcutoffから開始する。初回は3日前、最大で7日前まで。古い未収集期間を切り詰める場合は、その範囲も報告する。未来のカーソル等の状態異常は更新せず停止する。

検索ツールが日付指定しか受け付けない場合も、返却された各時刻で固定窓へ絞る。取得のページングと範囲を確認できなければcompleteにしない。

```sh
python3 "<plugin-root>/scripts/people_manager.py" --workspace "<workspace>" window --member "<Slack ID>"
```

## 収集する事実

Slackは対象者本人の公開チャンネル投稿・日報・成果物URLと、運用者本人の参加が確認できた通常privateチャンネルの業務発言を拾う。対象業務のチャンネルに限らず、担当業務の事実を扱う。

- 本文が空の投稿、相槌だけの発言、他人の発言、DM・Group DMは除外する。
- 通常privateチャンネルは、当該実行で運用者本人の参加を確認できた場合だけ扱う。DM・Group DMと私事コンテンツは除外する。
- 本人が完了と書いたことと、第三者検証済みの完了は区別する。
- 本人の学び・困りごとの引用は原文と出典を保ち、共有面へ出す範囲を確認する。

Notionは、setupで確認した本人ユーザーID等から帰属を確認できる公開業務ページ・成果物を拾う。名前検索だけで本人ページと決めない。

People Managerが生成した活動mirror・月次・prepと、それらを保存する場所は収集元から除外する。生成ページを本人の新しい活動として再取り込みしない。

## capture JSON

入力はUTF-8 JSONファイル。日時はタイムゾーン付きISO 8601。`date`はAsia/Tokyoのcutoff日で、活動の発生日とは別に扱う。

```json
{
  "version": 1,
  "member_id": "U123EXAMPLE",
  "start": "2026-10-04T09:00:00+09:00",
  "cutoff": "2026-10-07T09:00:00+09:00",
  "date": "2026-10-07",
  "sources": {
    "slack": {
      "status": "complete",
      "start": "2026-10-04T09:00:00+09:00",
      "end": "2026-10-07T09:00:00+09:00",
      "pagination_complete": true,
      "scope": ["本人公開投稿と運用者の参加確認済み通常チャンネル"],
      "retrieval": "exhaustive",
      "evidence": ["対象者指定の投稿検索。チャンネル種別を確認。最終ページまで取得し、時刻で絞り込み"]
    },
    "notion": {
      "status": "complete",
      "start": "2026-10-04T09:00:00+09:00",
      "end": "2026-10-07T09:00:00+09:00",
      "pagination_complete": true,
      "attribution_complete": true,
      "scope": ["本人帰属を確認した業務ページ。生成場所を除外"],
      "retrieval": "exhaustive",
      "evidence": ["確認済み本人IDと対象範囲で検索。最終ページまで取得。生成場所を除外"]
    }
  },
  "facts": []
}
```

これは形式例であり、`complete`・scope・証跡の文字列は実際の取得結果で埋める。0件でも、検索範囲・ページングを確認できた場合にだけcompleteを使う。AI検索の要約や関連候補だけの返却を`retrieval: exhaustive`として扱わない。

各factは次の項目を持つ。

| 項目 | 内容 |
|---|---|
| source / source_id | `slack`または`notion`と元投稿・ページのID |
| url | 元資料のHTTPS URL |
| happened_at / text | 元事実の日時と、根拠を変えない本文 |
| activity_date | 任意。本文に明示された活動日をYYYY-MM-DDで渡す。なければhappened_atから算出 |
| author_id / visibility | Slackでは本人のSlack IDと`public`または`private_channel` |
| notion_user_id | Notionでは確認済み本人のNotionユーザーID |
| generated / private | 収集対象はともにfalse |

`evidence`には実際のツール呼出・対象範囲・取得ページ数・終端確認等の確認情報を残す。証跡を作り足さず、秘密値やDM本文を含めない。

private_channelのfactには`channel_id`と`membership`を追加し、capture全体にも`operator_slack_user_id`を入れる。

```json
{
  "operator_slack_user_id": "U456OPERATOR",
  "membership": {
    "operator_id": "U456OPERATOR",
    "channel_id": "C123EXAMPLE",
    "confirmed": true,
    "checked_at": "2026-10-07T09:00:00+09:00",
    "evidence": "当該実行の会話情報・参加者取得で運用者IDとの一致を確認"
  }
}
```

上の`membership`はfact内、`operator_slack_user_id`はcapture全体へ置く。運用者IDはconfigの設定と一致させる。checked_atはcutoff以降・検査時刻以前とし、ツール応答で確認できた根拠を使う。

Slackの`is_member`が示す主体はbot/appの場合もあるため、運用者本人の参加とは別に確認する。`is_private`はチャンネル種別、factの`private`は私事コンテンツの除外フラグであり、単純転記しない。参加未確認・種別不明はslack欠測として保存を止める。

## ローカル保存

validate-captureで登録・窓・媒体別完備・本人帰属・重複を検査する。両必須媒体がcompleteになり、検査に合格した場合だけonでcommit-activityを実行する。

```sh
python3 "<plugin-root>/scripts/people_manager.py" --workspace "<workspace>" validate-capture --input "<capture JSON>"
python3 "<plugin-root>/scripts/people_manager.py" --workspace "<workspace>" commit-activity --input "<capture JSON>"
```

`members/<member_id>/activity/YYYY-MM.md`に、1人・1暦日・1セクションで保存する。既存セクションは再生成しない。元source_idと日時の組み合わせを照合し、同じ事実を二重保存しない。

ローカル保存の成功後にだけカーソルを進める。欠測、検査失敗、同日既存、保存失敗では進めない。Notionの失敗を理由に、保存済みローカル記録を消したり作り直したりしない。

observeは読み取り結果の表示まで、dry-runは保存予定本文の表示まで。どちらも活動ログ・state・カーソル・Notionを更新しない。offは収集を開始しない。

## Notion反映と保留

Notion反映操作が依頼された場合だけ[接続・保存先の契約](connector-contract.md)の反映条件で作成・読み戻しを行う。日次キーは`people-manager:activity:<member_id>:<date>`。依頼がなければpendingを保持する。

反映のJSON・コマンドは[接続・保存先の契約](connector-contract.md)のrecord-mirror節を使う。inspectの返却`can_create: true`を確認してから1回だけ作成する。タイムアウトや応答不明はunknownを記録し、reconcileの完全検索・照合へ進める。

Notion作成にはinspectの`expected.body`をそのまま使う。可視Management IDとliteral text codeblockのwrapperであり、ローカルMarkdownは変更しない。source・relation・キー・propertiesと独立fetchのraw本文・fetch証跡をrecord-mirrorへ渡し、[コード契約](connector-contract.md#record-mirrorの入力と順序)の限定adapterで確認する。送信した本文・hashを読み戻しとして転記しない。Notionが失敗してもローカル正本は保持する。

失敗が3回に達したキーはheldとして自動再試行を止める。held、複数一致、本文不一致は利用者へ返す。stateを手で書き換えて作成済み証跡や失敗回数を消さない。

## 次のアクション

取得範囲・欠測・ローカル保存・Notion読み戻しをそれぞれ報告する。欠測は取得機能・権限・本人帰属を確認し、Notion未反映は既存キーの現物確認から再開する。
