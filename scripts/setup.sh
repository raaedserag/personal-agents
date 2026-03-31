#!/bin/bash
# Nerve Center — First-time setup wizard
set -e

echo "⚡ Nerve Center Setup"
echo "====================="
echo ""

# Create secrets directory
mkdir -p secrets

# Check for required files
if [ ! -f "secrets/shared.env" ]; then
    echo "Creating secrets/shared.env..."
    read -p "  Anthropic API key (or press Enter to skip): " ANTHROPIC_KEY
    read -p "  Agent API key (press Enter to auto-generate): " AGENT_KEY
    read -p "  Dashboard PIN (default: 1234): " DASH_PIN

    AGENT_KEY=${AGENT_KEY:-$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")}
    DASH_PIN=${DASH_PIN:-1234}

    cat > secrets/shared.env << EOF
ANTHROPIC_API_KEY=${ANTHROPIC_KEY}
AGENT_API_KEY=${AGENT_KEY}
DASHBOARD_PIN=${DASH_PIN}
EOF
    echo "  ✓ secrets/shared.env created"
else
    echo "  ✓ secrets/shared.env exists"
fi

# Yassir profile secrets
if [ ! -f "secrets/yassir.env" ]; then
    echo ""
    echo "Setting up Yassir profile..."
    read -p "  Jira domain (e.g., https://org.atlassian.net): " JIRA_DOMAIN
    read -p "  Jira email: " JIRA_EMAIL
    read -p "  Jira API token: " JIRA_TOKEN
    read -p "  GitHub org name: " GH_ORG
    read -p "  GitHub token: " GH_TOKEN

    cat > secrets/yassir.env << EOF
YASSIR_JIRA_DOMAIN=${JIRA_DOMAIN}
YASSIR_JIRA_EMAIL=${JIRA_EMAIL}
YASSIR_JIRA_TOKEN=${JIRA_TOKEN}
YASSIR_GITHUB_ORG=${GH_ORG}
YASSIR_GITHUB_TOKEN=${GH_TOKEN}
YASSIR_SLACK_WORKSPACE=
YASSIR_SLACK_BOT_TOKEN=
YASSIR_GCP_PROJECT=
EOF
    echo "  ✓ secrets/yassir.env created"
else
    echo "  ✓ secrets/yassir.env exists"
fi

echo ""
echo "Setup complete! Next steps:"
echo ""
echo "  1. Review and fill in any blank values in secrets/*.env"
echo "  2. Update profiles/yassir.yaml with your Jira project keys"
echo "  3. Run: docker compose up --build"
echo "  4. Test: curl http://localhost:10000/health"
echo "  5. Use CLI: python interfaces/cli/nerve.py health"
echo ""
echo "To install the CLI globally:"
echo "  pip install -r interfaces/cli/requirements.txt"
echo "  alias nerve='python $(pwd)/interfaces/cli/nerve.py'"
echo ""
