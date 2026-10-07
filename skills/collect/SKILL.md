---
name: collect
description: Collect a registered person's Slack work facts from public or operator-membership-verified channels and attributable Notion output into People Manager, with completeness and create-only mirroring.
---

# People Manager collect

活動事実を収集する。評価は書かない。実行前に[収集手順](../../references/collection.md)を読む。接続の機能・Notion保存先が未確認なら[接続・保存先の契約](../../references/connector-contract.md)の該当節を読む。

## 手順

1. このSKILL.mdの2階層上を`<plugin-root>`、利用者の開いたワークスペースを`<workspace>`として絶対パスを確定する。
2. ローカルconfig・stateを読み、activeな登録者、mode、Notion保存先、通知設定を確認する。Notion反映操作が依頼されているかも確認する。offなら終了する。
3. helperのwindowで開始・cutoffを固定する。Slack・Notionの対象者本人の事実をその範囲で読み取り、検索範囲・ページング・本人帰属の証跡を残す。
4. 収集結果をcapture JSONへ整理し、validate-captureで検査する。不完全な必須媒体は0件にせず、保存・カーソル更新を保留する。
5. observeは確認結果、dry-runは保存予定本文まで表示する。onの場合だけcommit-activityを実行し、保存結果を確認する。
6. ローカル保存後、Notion反映操作が依頼され、保存先がreadyの場合だけcreate-onlyで反映する。送信本文はhelperの`expected.body`を使う。現物を独立fetchで読み戻し、実取得の本文とhash・取得証跡をrecord-mirrorへ渡す。反映依頼がなければpendingを保持する。

```sh
python3 "<plugin-root>/scripts/people_manager.py" --workspace "<workspace>" window --member "<Slack ID>"
python3 "<plugin-root>/scripts/people_manager.py" --workspace "<workspace>" validate-capture --input "<capture JSON>"
python3 "<plugin-root>/scripts/people_manager.py" --workspace "<workspace>" commit-activity --input "<capture JSON>"
```

同じ人物・同じ暦日のセクションは再生成しない。Notionへの作成結果が不明なら、現物確認前に作成を再試行しない。対象者へ通知しない。

## 結果と次のアクション

取得範囲、媒体別complete/partial/missing/unsupported、保存先、Notionの読み戻し結果、保留理由を報告する。次は不足権限・本人帰属・未反映を解消する。問題がなければローカル資料を使って1on1-prepを作る。
