# apple-refurb-watch

Apple 整備済製品ストア（日本）の在庫を定期的に確認し、
**iPhone 15 Pro 256GB（全色）** が入荷したら通知します（新しい色が一覧に現れるたびに通知）。

- 監視ページ: https://www.apple.com/jp/shop/refurbished/iphone/iphone-15-pro
- 実行: GitHub Actions（`.github/workflows/watch.yml`）。スケジュールは同ファイルの `cron` で変更。
- 通知:
  1. ntfy.sh へプッシュ通知（リポジトリの Secret `NTFY_TOPIC` に入れたトピック宛。iPhone の ntfy アプリで購読する）
  2. GitHub Issue を作成し、所有者を担当者にする（GitHub からメールが届く）。売り切れたら自動でクローズ。
- 状態: `state.json`（在庫の有無・部品番号・価格・最終確認日）。新しい部品番号（色）が現れた時だけ通知。
- 監視対象を変えるときは `check.py` の `TARGET` と `LABEL` を編集。
- 手動実行・テスト通知: Actions タブ → watch → Run workflow（test にチェック）。
