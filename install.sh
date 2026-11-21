#!/usr/bin/env bash
set -euo pipefail

echo "=== HarnessXGate One-Command Installer (macOS / Linux / WSL) ==="

if ! command -v python3 >/dev/null 2>&1; then
  echo "[ERROR] Python 3.10+ is required." >&2
  exit 1
fi

INSTALL_DIR="$HOME/.harnessxgate/app"
BIN_DIR="$HOME/.local/bin"
mkdir -p "$BIN_DIR" "$(dirname "$INSTALL_DIR")"

if command -v git >/dev/null 2>&1; then
  if [ -d "$INSTALL_DIR/.git" ]; then
    echo "Updating HarnessXGate..."
    git -C "$INSTALL_DIR" pull --ff-only
  else
    echo "Downloading HarnessXGate..."
    git clone --depth 1 https://github.com/Eli-Mira/HarnessXGate.git "$INSTALL_DIR"
  fi
else
  echo "Downloading HarnessXGate archive..."
  TMP_TAR="$(mktemp)"
  curl -fsSL https://github.com/Eli-Mira/HarnessXGate/archive/refs/heads/main.tar.gz -o "$TMP_TAR"
  rm -rf "$INSTALL_DIR"
  mkdir -p "$INSTALL_DIR"
  tar -xzf "$TMP_TAR" --strip-components=1 -C "$INSTALL_DIR"
  rm -f "$TMP_TAR"
fi

cat > "$BIN_DIR/hxg" <<EOF
#!/usr/bin/env bash
export PYTHONPATH="$INSTALL_DIR:\${PYTHONPATH:-}"
exec python3 -m harnessxgate "\$@"
EOF
chmod +x "$BIN_DIR/hxg"
ln -sf "$BIN_DIR/hxg" "$BIN_DIR/harnessxgate"

echo ""
echo "[OK] HarnessXGate installed at $BIN_DIR/hxg"
echo "Make sure $BIN_DIR is on your PATH, then run: hxg"
echo ""
"$BIN_DIR/hxg" ui
