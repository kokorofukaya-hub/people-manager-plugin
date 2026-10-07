# 月次活動レポート

指定月、または実行時点のAsia/Tokyo前月の収集済み業務活動を、出典付きでまとめる。ローカル正本を作り、反映操作が依頼された場合に限り既存のNotion活動ログDBへ初回作成する。

## 月への帰属

対象月と前後月のactivityを読む。活動日は記録内に明示された日付を優先し、なければ元投稿・ページの日時を使う。収集日・セクションの日付・ファイル名だけで実績月を決めない。

- 前月ファイルに含まれる対象月の活動、翌月初回収集に含まれる対象月末の活動を確認する。
- 明示活動日と投稿日が異なる場合は、活動日を使い投稿日も添える。
- 活動日が確定できない記録は「月帰属未確定」として別に置く。
- 元source_id・時刻で重複を照合し、一度だけ扱う。
- 予定・相談・本人の完了報告・検証済み完了を区別する。

読み取った月の範囲と媒体の欠測を明記する。記録がないことを活動なし・未達と判断せず、投稿件数から総稼働時間や能力評価を計算しない。

## レポートの構成

「対象期間／活動事実／進行・要確認／次月確認／根拠」の短い構成にする。各事実へ元URLとローカル出典を添える。

goals.mdは次月の確認事項を考えるために読む。活動から本人の性格・参加目的・目標を推測し直したり、人物プロフィールを更新したりしない。

meetingsの非公開面談、prep、私的DMを本文へ転載しない。出典を確認できない事実は本文へ追加せず、必要な確認として残す。

## ローカル保存

commit-documentの入力は次の形式。`evidence_fact_keys`は保存済みactivityのfactコメントまたは`activity/records/`のJSONにある実際のキーを使い、推測で組み立てない。

```json
{
  "member_id": "U123EXAMPLE",
  "kind": "monthly",
  "period": "2026-09",
  "body": "対象期間・活動事実・要確認・次月確認・根拠を含む本文",
  "evidence_fact_keys": [],
  "private_meeting_ids": []
}
```

```sh
python3 "<plugin-root>/scripts/people_manager.py" --workspace "<workspace>" commit-document --input "<月次レポートJSON>"
```

例の空配列は形式例。事実を記載する場合は、対応する保存済みfactのキーを列挙する。非公開議事録への参照は入れない。

onの場合だけ`members/<member_id>/monthly/YYYY-MM.md`へ保存する。helperが固定キーのmarkerを1つだけ付ける。本文は見出し・段落・箇条書きで構成し、fence・HTML tableは入れない。Notion作成には保存後の原文を包んだinspectの`expected.body`を使う。ローカル本文を直接送信しない。

observe・dry-runは表示まで。同じ月の既存正本は再生成・差し替えをしない。再試行で対象月や初回作成日を変えない。日次本文・sidecarが人手変更または中断で整合しない場合は、月次保存を止めて照合する。

## Notionへの初回反映

固定キーは`people-manager:monthly:<member_id>:<YYYY-MM>`。反映先は活動ログDBで、人物DBの子ページには作らない。

mode=on、保存先ready、本人relation確認済みの場合に、依頼された反映を実行する。反映依頼がなければローカル保存後のpendingを保持する。

[接続・保存先の契約](connector-contract.md)の反映条件で、親source・対象者relation・properties・固定キー・可視Management ID・literal code内の全文を照合する。`expected.body`を送信し、独立fetchのraw本文と完全取得の証跡をrecord-mirrorへ渡す。raw送信hashとraw実fetch hashは別々に記録し、限定canonicalの一致を確認する。source・relation・キーが一致しても、code内の空白・空行・本文が違う既存ページは採用しない。

作成結果が不明なら現物検索へ進む。確認前に再作成しない。複数一致・読み戻し不一致・3回失敗は保留し、利用者へ返す。既存正本とNotion本文は機械で上書きしない。

## 次のアクション

対象月・取得範囲・保存先・Notion反映・未確認を報告する。翌月も実行する場合は、[定期実行](scheduling.md)で登録と実行確認を別々に行う。
