---
name: monthly
description: Create a source-backed People Manager monthly activity report from local activity dates, reading adjacent months and optionally mirroring once to the existing activity database.
---

# People Manager monthly

活動日で対象月を確定し、月次レポートを作る。最初に[月次集計](../../references/monthly.md)を読む。Notion反映の依頼がある場合だけ[接続・保存先の契約](../../references/connector-contract.md)の反映節を読む。

## 手順

1. このSKILL.mdの2階層上を`<plugin-root>`、利用者ワークスペースを`<workspace>`として絶対パスを確定する。
2. 登録者と対象月を確認する。指定がなければAsia/Tokyoの前月を使う。再試行では初回の対象月を維持する。
3. 対象月と前後月のローカルactivityを読み、活動日で絞る。収集日・ファイル名から活動月を決めない。
4. 元source_id・日時で重複を除き、対象期間／活動事実／進行・要確認／次月確認／根拠で書く。非公開面談・prepを転載しない。
5. kind=monthly、period=YYYY-MM、参照したevidence_fact_keysをcommit-documentの入力にする。既存月次は再生成しない。observe・dry-runは表示まで、onだけ保存する。
6. Notion反映操作が依頼され、保存先がreadyなら、活動ログDBの同じ固定キーを確認し、helperの`expected.body`でcreate-only反映する。独立fetchの実本文とhash・取得証跡を読み戻し照合へ渡す。依頼がなければpendingを保持する。人物プロフィールを変更しない。

```sh
python3 "<plugin-root>/scripts/people_manager.py" --workspace "<workspace>" commit-document --input "<月次レポートJSON>"
```

欠測・対象月への帰属不明は明記する。投稿件数から総稼働時間・仕事量・能力評価を算出しない。作成結果不明のNotionページを確認前に再作成しない。

## 結果と次のアクション

対象月、根拠範囲、保存先、Notion読み戻しの成否、欠測・保留を報告する。次は翌月の面談で未確認事項を確認し、定期実行を希望する場合だけ[定期実行](../../references/scheduling.md)へ進む。
