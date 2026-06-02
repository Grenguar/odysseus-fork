#!/usr/bin/env bash
# Deploy Odysseus to AWS via CloudFormation.
#
# Prerequisites — both secrets live in SSM as SecureStrings, parked
# manually before first deploy (CFN can't create SecureStrings):
#   1. Fine-grained GitHub PAT for `Grenguar/odysseus-fork` at
#      /odysseus/github/pat
#   2. Reusable Tailscale auth key (Reusable=ON, Ephemeral=OFF,
#      Tag=tag:odysseus) at /odysseus/tailscale/authkey
#
#   aws ssm put-parameter --region eu-west-1 --profile igor \
#     --name /odysseus/github/pat --type SecureString --value 'github_pat_...'
#   aws ssm put-parameter --region eu-west-1 --profile igor \
#     --name /odysseus/tailscale/authkey --type SecureString \
#     --value 'tskey-auth-...'
#
# Usage:
#   export AWS_PROFILE=igor
#   export AWS_REGION=eu-west-1
#   # Optional overrides:
#   export ADMIN_USERNAME=igor             # default: igor
#   export INSTANCE_TYPE=t4g.medium        # default: t4g.medium
#   export DATA_VOL_GB=30                  # default: 30
#   export GIT_REF=main                    # default: main (pin to a SHA in prod)
#
#   ./deploy.sh

set -euo pipefail

STACK_NAME="${STACK_NAME:-odysseus-agent}"
REGION="${AWS_REGION:-eu-west-1}"
TEMPLATE="$(dirname "$0")/odysseus-stack.yaml"

# Preflight: both secrets must already be in SSM as SecureStrings.
# Failing fast here saves us a ~5-minute round-trip where the instance
# boots, runs `tailscale up`, fails, and CFN times out waiting for the
# resource signal.
preflight_secret() {
  local name="$1"
  if ! aws ssm get-parameter --region "$REGION" --name "$name" --with-decryption >/dev/null 2>&1; then
    echo "ERROR: $name not found in SSM (region=$REGION)." >&2
    echo "       Create it:" >&2
    echo "         aws ssm put-parameter --region $REGION --profile \$AWS_PROFILE \\" >&2
    echo "           --name $name --type SecureString --value '...'" >&2
    return 1
  fi
}

echo ">> Preflight: SecureString parameters in SSM..."
preflight_secret /odysseus/github/pat       || exit 2
preflight_secret /odysseus/tailscale/authkey || exit 2
echo "   ok"

PARAMS=(
  "InstanceType=${INSTANCE_TYPE:-t4g.medium}"
  "DataVolumeSizeGb=${DATA_VOL_GB:-30}"
  "AdminUsername=${ADMIN_USERNAME:-igor}"
  "OdysseusGitRef=${GIT_REF:-main}"
)

echo ">> Stack:    $STACK_NAME"
echo ">> Region:   $REGION"
echo ">> Template: $TEMPLATE"
echo ""

aws cloudformation validate-template \
  --region "$REGION" \
  --template-body "file://${TEMPLATE}" >/dev/null

aws cloudformation deploy \
  --region "$REGION" \
  --stack-name "$STACK_NAME" \
  --template-file "$TEMPLATE" \
  --capabilities CAPABILITY_IAM \
  --parameter-overrides "${PARAMS[@]}" \
  --no-fail-on-empty-changeset

echo ""
echo ">> Stack outputs:"
aws cloudformation describe-stacks \
  --region "$REGION" \
  --stack-name "$STACK_NAME" \
  --query 'Stacks[0].Outputs[].[OutputKey,OutputValue]' \
  --output table

echo ""
echo "Bootstrap takes ~5-8 min (Python deps install is the slow part)."
echo "Tail it:"
INSTANCE_ID=$(aws cloudformation describe-stack-resources \
  --region "$REGION" --stack-name "$STACK_NAME" \
  --logical-resource-id OdysseusInstance \
  --query 'StackResources[0].PhysicalResourceId' --output text)
echo "  aws ssm start-session --region $REGION --target $INSTANCE_ID"
echo "  # then: sudo tail -f /var/log/odysseus-bootstrap.log"
echo ""
echo "Once it's up, fetch the one-time setup token:"
echo "  aws ssm get-parameter --region $REGION \\"
echo "    --name /odysseus/setup-token --query Parameter.Value --output text"
echo ""
echo "Then open https://odysseus.<your-tailnet>.ts.net in any tailnet"
echo "device's browser and complete setup."
