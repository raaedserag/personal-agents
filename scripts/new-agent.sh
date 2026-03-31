#!/bin/bash
# Scaffold a new agent from the template
set -e

if [ -z "$1" ]; then
    echo "Usage: ./scripts/new-agent.sh <agent-name>"
    echo "Example: ./scripts/new-agent.sh github-agent"
    exit 1
fi

AGENT_NAME=$1
AGENT_DIR="agents/$AGENT_NAME"

if [ -d "$AGENT_DIR" ]; then
    echo "Error: $AGENT_DIR already exists"
    exit 1
fi

echo "Creating agent: $AGENT_NAME"

cp -r agents/_template "$AGENT_DIR"

# Update placeholders
sed -i "s/AGENT_NAME/$AGENT_NAME/g" "$AGENT_DIR/SOUL.md"
sed -i "s/AGENT_NAME/$AGENT_NAME/g" "$AGENT_DIR/DUTIES.md"
sed -i "s/AGENT_NAME/$AGENT_NAME/g" "$AGENT_DIR/agent.yaml"

echo "✓ Created $AGENT_DIR"
echo ""
echo "Next steps:"
echo "  1. Edit $AGENT_DIR/SOUL.md — define agent identity"
echo "  2. Edit $AGENT_DIR/DUTIES.md — define permissions"
echo "  3. Add skills to $AGENT_DIR/skills/"
echo "  4. Update $AGENT_DIR/api.py with endpoints"
echo "  5. Add service to docker-compose.yml"
echo "  6. Register in conductor/config.yaml"
