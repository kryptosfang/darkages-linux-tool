#!/bin/bash

# setup_permissions.sh - Assist user in setting up /dev/input permissions
TARGET_USER=${SUDO_USER:-$USER}

echo "Running: usermod -aG input $TARGET_USER"

if usermod -aG input "$TARGET_USER"; then
    echo ""
    echo "SUCCESS: Group membership updated for $TARGET_USER."
    echo "CRITICAL: You MUST log out and log back in (or restart) for these changes to take effect."
else
    echo "ERROR: Failed to update group membership."
fi
