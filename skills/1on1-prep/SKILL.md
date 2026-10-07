---
name: 1on1-prep
description: Prepare a registered person's 1on1 memo using local People Manager goals, recent activity, and imported transcripts, separating evidence from the operator's interpretation.
---

# People Manager 1on1-prep

運用者が面談で使う準備メモを作る。最初に[1on1準備](../../references/prep.md)を読む。内容の入力はローカルの目標・活動ログ・議事録だけとする。

## 手順

1. このSKILL.mdの2階層上を`<plugin-root>`、利用者ワークスペースを`<workspace>`として絶対パスを確定する。
2. 指定された登録者のmember_idと面談日を確認する。対象者の指定がなければ確認する。Calendar自動判定の依頼がある場合だけ[定期実行](../../references/scheduling.md)の1on1節を読む。
3. goals.md、直近14日を含むactivity、最新の取込済みTranscript、前回準備メモを必要な範囲で読む。月境界なら前月の活動ログも読む。
4. 根拠の日付・出典を添え、6章で清書する。1〜4章と6章の本人事実・合意は根拠に限定し、推測は5章だけに置く。
5. observeは確認結果、dry-runは本文の表示まで。onの場合だけkind=prepのcommit-documentで保存し、読み戻す。対象者へ共有・通知しない。

```sh
python3 "<plugin-root>/scripts/people_manager.py" --workspace "<workspace>" commit-document --input "<準備メモJSON>"
```

活動の記録がないことを未達と判断しない。目標が未記入なら、その確認を最初の問いにする。Slack・Notionを新しく読み取って不足資料をその場で埋めず、収集・議事録取込を別の処理として案内する。

## 結果と次のアクション

メモの保存先またはプレビュー、参照期間、未取得資料、確認したい問いを短く報告する。次は面談で目標・本人の言葉・前回アクションを確認する。
