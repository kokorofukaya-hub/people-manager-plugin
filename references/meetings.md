# 議事録取込

指定されたNotion議事録またはローカル逐語録を、面談準備の入力として保存する。録音・音声認識・議事録サービスの同期は提供しない。

## 取り込む範囲

登録されたmember_id、会議を識別するmeeting_id、日付、参加者、元URLまたはファイル、Transcriptを確認する。対象者が参加した記録か確定できない場合は、その不足を確認する。

Notionの場合は、setupで指定した議事録rootまたはユーザーが直接指定したページを読む。置場の指定だけを手掛かりに、関係のない会議や私的DMへ探索を広げない。

ローカルの場合は利用者ワークスペース内の指定ファイルを読み、話者ラベルと日時を保つ。source_fileは既存ファイルの絶対パスで渡す。ワークスペース外や秘密ファイルは取り込まない。

## 取込JSON

```json
{
  "member_id": "U123EXAMPLE",
  "meeting_id": "meeting-example-2026-10-07",
  "source_url": "https://www.notion.so/22222222222222222222222222222222",
  "date": "2026-10-07",
  "participants": ["対象者", "運用者"],
  "transcript": [
    {"speaker": "対象者", "text": "次回までに資料の初稿を作ります。"},
    {"speaker": null, "text": "話者を確認できない発言。"}
  ]
}
```

ローカル議事録なら`source_url`の代わりに`source_file`を渡す。片方だけ指定する。`summary`は任意で保存できるが、本人発言の根拠として扱わない。例の人物・発言・URLは架空の形式例。

```sh
python3 "<plugin-root>/scripts/people_manager.py" --workspace "<workspace>" import-meeting --input "<議事録JSON>"
```

## 話者帰属と保存

- 本人の発言は本人と確認できた話者ラベルのTranscriptだけから取る。
- 話者不明はnullとして残し、本人の希望・約束・実績へ変換しない。
- AI要約がある場合も、元Transcriptを根拠として別々に扱う。
- 読めない文字起こしは「未確認」とし、意味を推測して補わない。
- 同じmeeting_idが既存なら再生成・上書きせず、内容差がある場合は保留する。

mode=onの場合に、`members/<member_id>/meetings/`へローカル保存する。observe・dry-runは確認・プレビューまで。面談の内容はprivateとして扱い、活動mirror・月次レポートへ転載しない。

## 次のアクション

取込後のファイルを読み戻し、日付・参加者・話者・本文の保持を確認する。次は1on1-prepで、本人に帰属する希望と前回ネクストアクションだけを根拠付きで使う。
