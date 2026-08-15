#!/usr/bin/env bash
# Install Thales CAs from potions/certs/ into the system trust store.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CERTS="$ROOT/certs"

if ! sudo -n true 2>/dev/null; then
  echo "Needs sudo. Re-run as:  sudo bash $0"
fi

install_one() {
  local src="$1"
  local dest_name="$2"
  local out="/usr/local/share/ca-certificates/${dest_name}.crt"
  [[ -f "$src" ]] || return 1
  if openssl x509 -in "$src" -inform PEM -noout 2>/dev/null; then
    sudo cp "$src" "$out"
  else
    sudo openssl x509 -in "$src" -inform DER -out "$out"
  fi
  echo "installed $out"
  openssl x509 -in "$out" -noout -subject -issuer
}

# Prefer PEM if present; accept several export names.
install_one "$CERTS/thales_ca_v3_root.pem" "thales_root_ca_v3" \
  || install_one "$CERTS/thales_ca_v3_root.cer" "thales_root_ca_v3" \
  || install_one "$CERTS/thales_root_ca_v3.pem" "thales_root_ca_v3" \
  || install_one "$CERTS/thales_root_ca_v3.cer" "thales_root_ca_v3" \
  || echo "WARNING: Thales Root CA V3 not found in certs/ (needed)"

install_one "$CERTS/thales_ca_v4.pem" "thales_ca_v4" \
  || install_one "$CERTS/thales_ca_v4.cer" "thales_ca_v4" || true

install_one "$CERTS/thales_ca_v4_l2.pem" "thales_ca_v4_l2" \
  || install_one "$CERTS/thales_ca_v4_l2.cer" "thales_ca_v4_l2" || true

sudo update-ca-certificates
echo ""
echo "Test:"
echo "  agent -p --force --workspace $ROOT 'Reply with exactly: pong'"
