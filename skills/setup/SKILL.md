---
name: setup
description: Set up People Manager for a named person's Slack ID and Notion URL, resolving the person, existing storage destinations, and connector capabilities before collection.
---

# People Manager setup

対象者のSlack IDとNotion URLから登録を始める。最初に[接続・保存先の契約](../../references/connector-contract.md)を読み、本人・人物行・活動ログDBを一意に確認する。

## 手順

1. 現在の利用者ワークスペースを絶対パスで確定する。このSKILL.mdの2階層上を`<plugin-root>`とし、インストールキャッシュを保存先に使わない。
2. 接続済みSlackで指定IDのプロフィールを取得し、表示名を確認する。識別子は表示名ではなくSlack IDに固定する。
3. 指定Notion URLと必要な親・子を取得し、人物行、人物DB、活動ログDBの実data source、対象者relationを照合する。本人のNotionユーザーIDも確認する。ページの`created_by`から対象者を推定しない。
4. 一致が複数ある、権限がない、必要保存先がない場合は、該当項目だけ確認する。新しいDB・列を自動作成しない。
5. 解決結果を設定JSONにまとめ、helperのsetupを実行してvalidate-configで確認する。helper既定はoff、通知無効。ユーザーが読み取り確認を依頼していればobserveを明示設定する。設定が未解決でも、その不足を明示してstatusへ引き継ぐ。

```sh
python3 "<plugin-root>/scripts/people_manager.py" --workspace "<workspace>" setup --slack-user-id "<Slack ID>" --notion-url "<Notion URL>" --input "<設定JSON>"
python3 "<plugin-root>/scripts/people_manager.py" --workspace "<workspace>" validate-config
```

設定JSONは[接続・保存先の契約](../../references/connector-contract.md)のsetup断片に従う。既存設定のmode等を変更する場合は、同文書のconfigure手順を使う。

初期化後、`.people-manager/`がGit管理から除外されることと、個人記録の保存先が利用者ワークスペース内であることを確認する。秘密値を設定JSONに入れない。

## 結果と次のアクション

人物・保存先・接続機能の確認済み項目、未解決項目、現在のmodeを短く報告する。次はcollectをobserveで1回実行する。定期実行の依頼がある場合だけ[定期実行](../../references/scheduling.md)を読む。
