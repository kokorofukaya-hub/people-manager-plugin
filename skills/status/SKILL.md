---
name: status
description: Read People Manager's local configuration and state to report registered people, modes, cursors, unresolved destinations, held mirrors, and unverified scheduled execution.
---

# People Manager status

ローカルの現在状態を確認する。外部の活動を新しく収集せず、設定や失敗回数を変更しない。

## 手順

1. このSKILL.mdの2階層上を`<plugin-root>`、利用者ワークスペースを`<workspace>`として絶対パスを確定する。
2. helperのstatusとvalidate-configを実行し、登録者、mode、未解決設定、保存カーソル、Notion反映の工程を読む。
3. 未解決保存先、作成結果不明、heldを別々に報告する。失敗・未実行を0件や成功として表示しない。未保存収集のpartial/missing/unsupportedはstateに履歴保存されないため、実行時の結果が手元になければ未確認とする。
4. 定期実行の状態を尋ねられた場合だけ[定期実行](../../references/scheduling.md)を読む。ローカルstateだけでホスト予定の登録・稼働を断定しない。

```sh
python3 "<plugin-root>/scripts/people_manager.py" --workspace "<workspace>" status
python3 "<plugin-root>/scripts/people_manager.py" --workspace "<workspace>" validate-config
```

## 結果と次のアクション

確認済み、未確認、次の操作を短く分ける。未反映がある場合は[収集手順](../../references/collection.md)または[月次集計](../../references/monthly.md)の読み戻し手順へ進む。状況確認だけで新しいページを作成しない。
