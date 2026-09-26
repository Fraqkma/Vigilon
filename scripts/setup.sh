#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
env_file="$root/.env"
[[ -e "$env_file" ]] || cp "$root/.env.example" "$env_file"
if ! grep -Eq 'generate-with-scripts/setup\.ps1|set-a-unique-password' "$env_file"; then
  echo '.env already contains configuration; left unchanged.'
  exit 0
fi
secret="$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')"
key="$(python3 -c 'import base64,secrets; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())')"
db_password="$(python3 -c 'import secrets; print(secrets.token_hex(24))')"
admin_password=''
if grep -q 'VIGILON_ADMIN_PASSWORD=set-a-unique-password' "$env_file"; then
  read -r -s -p 'Choose the local admin password (12+ characters): ' admin_password; echo
  if (( ${#admin_password} < 12 )); then echo 'The administrator password must contain at least 12 characters.' >&2; exit 1; fi
fi
python3 - "$env_file" "$secret" "$key" "$admin_password" "$db_password" <<'PY'
import pathlib,sys
p=pathlib.Path(sys.argv[1]); s=p.read_text(encoding='utf-8')
s=s.replace('VIGILON_SECRET_KEY=generate-with-scripts/setup.ps1','VIGILON_SECRET_KEY='+sys.argv[2])
s=s.replace('VIGILON_ENCRYPTION_KEY=generate-with-scripts/setup.ps1','VIGILON_ENCRYPTION_KEY='+sys.argv[3])
s=s.replace('VIGILON_ADMIN_PASSWORD=set-a-unique-password','VIGILON_ADMIN_PASSWORD='+sys.argv[4])
s=s.replace('POSTGRES_PASSWORD=generate-with-scripts/setup.ps1','POSTGRES_PASSWORD='+sys.argv[5])
p.write_text(s,encoding='utf-8')
PY
unset secret key db_password admin_password
echo 'Filled missing .env placeholders with local secrets and the chosen admin password.'
