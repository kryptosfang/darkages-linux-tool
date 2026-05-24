#!/bin/bash
set -e

if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

echo "Installing requirements..."
venv/bin/pip install -r requirements.txt


CURRENT_USER=$(whoami)

echo "Checking permissions for $CURRENT_USER..."

# Check if user is already in the 'input' group
if groups "$CURRENT_USER" | grep -q "\binput\b"; then
    echo "SUCCESS: You are already a member of the 'input' group."
    echo "You should be able to run improved_walk.py without sudo."
    exit 0
fi

echo "NOTICE: You are not a member of the 'input' group."
echo "This is required to read keyboard events globally without using sudo."
echo ""
read -pr "Would you like to add '$CURRENT_USER' to the 'input' group now? (y/n): " confirm

if [[ $confirm == [yY] || $confirm == [yY][eE][sS] ]]; then
  ./setup_permissions.sh
else
    echo "Operation cancelled. You will still need to use 'sudo' to run the walk script."
fi
