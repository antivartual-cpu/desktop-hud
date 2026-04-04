#!/bin/bash
# run_desktop_hud.sh
# Desktop HUD 起動スクリプト
# .desktop ファイルや自動起動から呼ばれることを想定している。

# スクリプト自身があるディレクトリを取得し、そこへ移動する
# （app.py が相対パスで他ファイルを参照する将来の拡張に備える）
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

# 仮想環境の Python で app.py を起動する
exec "${SCRIPT_DIR}/.venv/bin/python" "${SCRIPT_DIR}/app.py"
