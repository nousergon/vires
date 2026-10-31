# optional_ssm_env.sh — converge OPTIONAL SSM-backed secrets into the box .env.
#
# Sourced by deploy-on-merge.sh (and by tests/test_deploy_optional_keys.py, with
# a stub `aws` on PATH). Callers set ENV_FILE before calling anything here.
#
# Why this exists (vires-ops#82, PROD-06): the old hydration blocks only ever
# WROTE a key. When the SSM parameter was gone they logged and left whatever an
# earlier deploy had written, so deleting the parameter revoked nothing, even
# after a redeploy and restart. The rule here is three-state:
#
#   present  -> the key is (re)written to .env
#   absent   -> CONFIRMED ParameterNotFound: the key is removed from .env
#   unknown  -> anything else (AccessDenied, throttling, network, an empty or
#               "None" value): .env is left exactly as it is
#
# Only a confirmed absence clears a key. A transient AWS failure must never
# switch a working feature off, and must never be read as "the key is gone".
# Values are never echoed or traced (callers run without `set -x`).

# ssm_fetch NAME [--with-decryption]
#   Sets SSM_STATE (present|absent|unknown) and SSM_VALUE (empty unless present).
ssm_fetch() {
  local name="$1" decrypt="${2:-}" out err rc errfile
  SSM_STATE=unknown
  SSM_VALUE=""
  errfile=$(mktemp) || return 0
  # shellcheck disable=SC2086  # $decrypt is intentionally word-split (0 or 1 arg)
  out=$(aws ssm get-parameter --name "$name" $decrypt \
          --query Parameter.Value --output text 2>"$errfile")
  rc=$?
  err=$(cat "$errfile" 2>/dev/null)
  rm -f "$errfile"
  if [ "$rc" -eq 0 ]; then
    if [ -n "$out" ] && [ "$out" != "None" ]; then
      SSM_STATE=present
      SSM_VALUE="$out"
    fi
  elif printf '%s' "$err" | grep -q '(ParameterNotFound)'; then
    SSM_STATE=absent
  fi
  return 0
}

# env_clear KEY... — drop every KEY= line from $ENV_FILE.
env_clear() {
  local key pattern=""
  for key in "$@"; do
    pattern="${pattern:+$pattern|}^${key}="
  done
  grep -vE "$pattern" "$ENV_FILE" > "$ENV_FILE.tmp" || true
  mv "$ENV_FILE.tmp" "$ENV_FILE"
  chmod 600 "$ENV_FILE"
}

# env_set KEY VALUE — replace KEY's line in $ENV_FILE.
env_set() {
  env_clear "$1"
  printf '%s=%s\n' "$1" "$2" >> "$ENV_FILE"
  chmod 600 "$ENV_FILE"
}

# env_has KEY — true when $ENV_FILE carries a KEY= line.
env_has() {
  grep -q "^$1=" "$ENV_FILE" 2>/dev/null
}

# hydrate_optional_key PARAM ENV_KEY LABEL
#   Converge one optional SecureString into .env. Prints one status line.
hydrate_optional_key() {
  local param="$1" key="$2" label="$3"
  ssm_fetch "$param" --with-decryption
  case "$SSM_STATE" in
    present)
      env_set "$key" "$SSM_VALUE"
      echo "${label}: hydrated key from ${param}"
      ;;
    absent)
      if env_has "$key"; then
        env_clear "$key"
        echo "${label}: ${param} not found — cleared the previously hydrated key (revoked)"
      else
        echo "${label}: no key at ${param} — feature unavailable (non-fatal)"
      fi
      ;;
    *)
      echo "${label}: could not read ${param} (not a confirmed ParameterNotFound) — .env left unchanged"
      ;;
  esac
  SSM_VALUE=""
}

# hydrate_optional_pair PARAM_A KEY_A DECRYPT_A PARAM_B KEY_B DECRYPT_B LABEL
#   Converge a keypair that is only usable whole (e.g. VAPID). Both present ->
#   both written. Either CONFIRMED absent -> both cleared, because half a pair
#   serves nothing. Otherwise (any unknown) -> .env left unchanged.
hydrate_optional_pair() {
  local pa="$1" ka="$2" da="$3" pb="$4" kb="$5" db="$6" label="$7"
  local sa va sb vb
  ssm_fetch "$pa" "$da"; sa="$SSM_STATE"; va="$SSM_VALUE"
  ssm_fetch "$pb" "$db"; sb="$SSM_STATE"; vb="$SSM_VALUE"
  SSM_VALUE=""
  if [ "$sa" = present ] && [ "$sb" = present ]; then
    env_set "$ka" "$va"
    env_set "$kb" "$vb"
    echo "${label}: hydrated keypair from SSM"
  elif [ "$sa" = absent ] || [ "$sb" = absent ]; then
    if env_has "$ka" || env_has "$kb"; then
      env_clear "$ka" "$kb"
      echo "${label}: keypair not found in SSM — cleared the previously hydrated pair (revoked)"
    else
      echo "${label}: no keypair in SSM — feature unavailable (non-fatal)"
    fi
  else
    echo "${label}: could not read the keypair (not a confirmed ParameterNotFound) — .env left unchanged"
  fi
}
