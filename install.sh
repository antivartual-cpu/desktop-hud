#!/bin/bash
# install.sh
# Desktop HUD インストールスクリプト
# Ubuntu 系 Linux / Zorin OS 向け
# 実行したユーザーの $HOME を使ってインストールする。
#
# 使い方:
#   cd ~/desktop_hud
#   bash install.sh              # 通常インストール
#   bash install.sh --autostart  # 自動起動も同時に有効化

set -e  # エラーで即停止

# ── 引数パース ────────────────────────────────────────────────────────────────
ENABLE_AUTOSTART=false
for arg in "$@"; do
    case "${arg}" in
        --autostart) ENABLE_AUTOSTART=true ;;
        --help|-h)
            echo "使い方: bash install.sh [--autostart]"
            echo "  --autostart  ログイン時の自動起動も有効にする"
            exit 0
            ;;
        *)
            echo "不明なオプション: ${arg}" >&2
            echo "使い方: bash install.sh [--autostart]" >&2
            exit 1
            ;;
    esac
done

# ── 色定義（ターミナル出力用） ──────────────────────────────────────────────
GREEN="\033[0;32m"
YELLOW="\033[1;33m"
RED="\033[0;31m"
NC="\033[0m"  # 色リセット

info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*" >&2; }

# ── 基本パス設定 ──────────────────────────────────────────────────────────────
# スクリプト自身が置かれているディレクトリを APP_DIR とする
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${APP_DIR}/.venv"
DESKTOP_FILE_NAME="desktop-hud.desktop"
APPS_DIR="${HOME}/.local/share/applications"
AUTOSTART_DIR="${HOME}/.config/autostart"
DESKTOP_DIR=""   # 後で自動検出

info "インストール先: ${APP_DIR}"

# ── python3 の確認 ────────────────────────────────────────────────────────────
if ! command -v python3 &>/dev/null; then
    error "python3 が見つかりません。"
    error "  sudo apt install python3 python3-venv python3-pip libxcb-cursor0"
    exit 1
fi
PYTHON_VER=$(python3 --version)
info "Python: ${PYTHON_VER}"

# ── python3-venv の確認 ───────────────────────────────────────────────────────
if ! python3 -c "import venv" &>/dev/null; then
    error "python3-venv が見つかりません。"
    error "  sudo apt install python3-venv"
    exit 1
fi

# ── 仮想環境の作成（既存があればスキップ） ───────────────────────────────────
if [ ! -d "${VENV_DIR}" ]; then
    info ".venv を作成中..."
    python3 -m venv "${VENV_DIR}"
else
    info ".venv は既に存在します（スキップ）"
fi

# ── 依存ライブラリのインストール ──────────────────────────────────────────────
info "依存ライブラリをインストール中..."
"${VENV_DIR}/bin/pip" install --upgrade pip --quiet
"${VENV_DIR}/bin/pip" install -r "${APP_DIR}/requirements.txt" --quiet
info "依存インストール完了"

# ── run_desktop_hud.sh の実行権限確認 ────────────────────────────────────────
chmod +x "${APP_DIR}/run_desktop_hud.sh"
info "run_desktop_hud.sh: 実行権限 OK"

# ── デスクトップフォルダの自動検出 ───────────────────────────────────────────
# xdg-user-dir コマンドがあれば正式なデスクトップパスを取得する
if command -v xdg-user-dir &>/dev/null; then
    DESKTOP_DIR="$(xdg-user-dir DESKTOP 2>/dev/null)"
fi
# フォールバック: 日本語環境 / 英語環境を順に試す
if [ -z "${DESKTOP_DIR}" ] || [ ! -d "${DESKTOP_DIR}" ]; then
    for candidate in "${HOME}/デスクトップ" "${HOME}/Desktop"; do
        if [ -d "${candidate}" ]; then
            DESKTOP_DIR="${candidate}"
            break
        fi
    done
fi

# ── .desktop ファイルの内容を生成する関数 ────────────────────────────────────
make_desktop_content() {
    cat <<EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=Desktop HUD
Name[ja]=Desktop HUD
Comment=CPU/メモリ/温度/ストレージ監視HUD
Comment[ja]=CPU/メモリ/温度/ストレージ監視HUD
Exec=${APP_DIR}/run_desktop_hud.sh
Icon=${APP_DIR}/icon.svg
Terminal=false
Categories=Utility;System;Monitor;
StartupNotify=false
EOF
}

# ── ~/.local/share/applications/ への登録 ────────────────────────────────────
mkdir -p "${APPS_DIR}"
APPS_DESKTOP="${APPS_DIR}/${DESKTOP_FILE_NAME}"
make_desktop_content > "${APPS_DESKTOP}"
chmod +x "${APPS_DESKTOP}"
info "アプリ登録: ${APPS_DESKTOP}"

# アプリDBを更新してメニューに反映させる
if command -v update-desktop-database &>/dev/null; then
    update-desktop-database "${APPS_DIR}" 2>/dev/null || true
fi

# ── デスクトップへの配置 ─────────────────────────────────────────────────────
if [ -n "${DESKTOP_DIR}" ] && [ -d "${DESKTOP_DIR}" ]; then
    DESK_FILE="${DESKTOP_DIR}/Desktop HUD.desktop"
    make_desktop_content > "${DESK_FILE}"
    chmod +x "${DESK_FILE}"
    # Nautilus / GNOME 向け: trusted フラグを立てて「信頼」ダイアログを省略する
    if command -v gio &>/dev/null; then
        gio set "${DESK_FILE}" metadata::trusted true 2>/dev/null || true
    fi
    info "デスクトップ配置: ${DESK_FILE}"
else
    warn "デスクトップフォルダが見つかりませんでした（手動で配置してください）"
fi

# ── 自動起動の設定（--autostart 指定時のみ） ─────────────────────────────────
if "${ENABLE_AUTOSTART}"; then
    mkdir -p "${AUTOSTART_DIR}"
    make_desktop_content > "${AUTOSTART_DIR}/${DESKTOP_FILE_NAME}"
    chmod +x "${AUTOSTART_DIR}/${DESKTOP_FILE_NAME}"
    info "自動起動登録: ${AUTOSTART_DIR}/${DESKTOP_FILE_NAME}"
fi

# ── 完了メッセージ ────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}=============================="
echo -e " インストール完了！"
echo -e "==============================${NC}"
echo ""
echo "起動方法:"
echo "  ${APP_DIR}/run_desktop_hud.sh"
echo ""
if [ -n "${DESKTOP_DIR}" ] && [ -d "${DESKTOP_DIR}" ]; then
    echo "デスクトップアイコンをダブルクリックしても起動できます。"
    echo "（初回は「起動を信頼する」が表示される場合があります）"
    echo ""
fi
if "${ENABLE_AUTOSTART}"; then
    echo "自動起動: 有効（ログイン時に自動起動します）"
    echo "  無効にするには: rm ${AUTOSTART_DIR}/${DESKTOP_FILE_NAME}"
else
    echo "自動起動を有効にするには:"
    echo "  bash ${APP_DIR}/install.sh --autostart"
fi
echo ""
