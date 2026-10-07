---
name: meeting-import
description: Import a specified Notion meeting record or local transcript into People Manager, preserving date, participants, speaker attribution, and private meeting boundaries.
---

# People Manager meeting-import

指定された議事録をローカルへ取り込む。最初に[議事録取込](../../references/meetings.md)を読む。Notion議事録置場を解決する場合だけ[接続・保存先の契約](../../references/connector-contract.md)の議事録節を読む。

## 手順

1. このSKILL.mdの2階層上を`<plugin-root>`、利用者ワークスペースを`<workspace>`として絶対パスを確定する。
2. 登録済みのmember_idと、ユーザーが指定したNotion議事録またはローカルファイルを確認する。会議の日付・参加者・本文を取得する。
3. Transcriptを話者別に整理する。話者が不明な発言はnullのまま保存し、本人の発言として扱わない。AI要約があっても逐語録の代わりに使わない。
4. 元議事録を識別するmeeting_idと出典を付け、helperの取込JSONにする。既存議事録を再生成・上書きしない。
5. modeに応じて確認・プレビューまで進め、onの場合だけhelperで保存する。議事録はローカルの面談用資料とし、活動ログDB・月次に転載しない。

```sh
python3 "<plugin-root>/scripts/people_manager.py" --workspace "<workspace>" import-meeting --input "<議事録JSON>"
```

録音、音声認識、指定外の議事録探索はこのスキルの範囲に含めない。崩れた文章の意味や不明話者を推測で補わない。

## 結果と次のアクション

保存先、日付、参加者、出典、話者不明・読取不足を報告する。次は1on1-prepで目標・活動ログ・取込済みTranscriptを参照する。
