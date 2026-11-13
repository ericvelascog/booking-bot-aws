#!/usr/bin/env bash
# Ejecuta `terraform plan` en los tres stacks y escribe plan-comment.md: el
# comentario que .github/workflows/plan.yml publica en el pull request.
#
# - Solo lee. Usa -lock=false porque el rol del plan no puede escribir nada, ni
#   siquiera el candado del estado. Un plan no cambia nada, así que no lo necesita.
# - Antes de publicar, tapa el número de la cuenta de AWS: el repo es público.
#   Los valores sensibles (el secreto del origen, el email) ya los tapa Terraform.
#
# Necesita: credenciales de AWS (el rol de solo lectura), TF_VAR_alert_email,
# HEAD_SHA y RUN_URL.
set -uo pipefail

COMMENT=plan-comment.md
MAX_CHARS=20000 # GitHub admite 65.536 caracteres por comentario: tres planes de 20.000 caben

if [ -z "${TF_VAR_alert_email:-}" ]; then
  echo "::error::Missing the ALERT_EMAIL repository secret: the bootstrap plan needs it"
  exit 1
fi

ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
failed=0
details=""

# Tapa el número de cuenta y recorta los planes muy largos
clean() {
  sed "s/${ACCOUNT_ID}/***/g" "$1" | head -c "$MAX_CHARS"
  if [ "$(wc -c < "$1")" -gt "$MAX_CHARS" ]; then
    printf '\n... (truncated: the full plan is in the workflow log)\n'
  fi
}

{
  echo "## Terraform plan"
  echo
  echo "Commit \`${HEAD_SHA:0:7}\`, computed with a read-only role. [Workflow run](${RUN_URL})"
  echo
  echo "| Stack | Result |"
  echo "|---|---|"
} > "$COMMENT"

for stack in bootstrap app edge; do
  dir="infra/$stack"

  # edge lee el ALB de app: si app está apagada, no hay nada con lo que comparar
  if [ "$stack" = edge ] && ! aws elbv2 describe-load-balancers --names booking-bot-alb > /dev/null 2>&1; then
    echo "| \`$stack\` | ⏭️ Skipped: the app stack is down, and edge reads its load balancer |" >> "$COMMENT"
    continue
  fi

  echo "::group::terraform plan ($stack)"
  if terraform -chdir="$dir" init -input=false -no-color > "init-$stack.log" 2>&1 \
    && terraform -chdir="$dir" plan -input=false -no-color -lock=false -out=tfplan 2>&1 | tee "plan-$stack.log"; then
    terraform -chdir="$dir" show -no-color tfplan > "plan-$stack.txt"
    result=$(grep -m1 -E '^(Plan:|No changes\.)' "plan-$stack.txt" || echo "Only output changes")
    icon="✅"
    [[ "$result" == *"to destroy"* && "$result" != *" 0 to destroy"* ]] && icon="⚠️"
  else
    failed=1
    result="Plan failed"
    icon="❌"
    cat "init-$stack.log" "plan-$stack.log" 2> /dev/null | tail -40 > "plan-$stack.txt"
  fi
  echo "::endgroup::"

  echo "| \`$stack\` | $icon $result |" >> "$COMMENT"
  details+=$'\n'"<details><summary><code>$stack</code>: $result</summary>"$'\n\n```text\n'"$(clean "plan-$stack.txt")"$'\n```\n\n</details>\n'
done

echo "$details" >> "$COMMENT"
exit "$failed"
