#!/bin/bash
set -e

# Twilio Phone Number Setup Script for DataPulse Voice Incident Response
# This script configures a Twilio phone number to forward calls to DataPulse backend

echo "=== DataPulse Twilio Setup ==="

# Step 1: Check if twilio CLI is available
if ! command -v twilio &> /dev/null; then
    echo "ERROR: twilio CLI not found. Please install it first:"
    echo "  npm install -g twilio-cli"
    echo "  Then authenticate: twilio login"
    echo ""
    echo "Creating manual setup instructions at TWILIO_SETUP.md..."
    
    cat > /opt/data/datapulse/TWILIO_SETUP.md << 'EOF'
# Twilio Manual Setup Instructions for DataPulse Voice

Since the `twilio` CLI is not available, follow these manual steps to set up voice incident response:

## Prerequisites
1. Twilio account (sign up at twilio.com)
2. Twilio phone number (can be purchased in console)
3. Publicly accessible URL for your DataPulse backend (use ngrok for local dev)

## Steps
1. **Buy a phone number** (if you don't have one):
   - Go to Twilio Console → Phone Numbers → Manage → Buy a Number
   - Select US country code, choose a number with Voice capability

2. **Configure the phone number**:
   - Go to Twilio Console → Phone Numbers → Manage → Active Numbers
   - Click on your phone number
   - Scroll to "Voice Configuration"
   - Set "A Call Comes In" to "Webhook"
   - Set the webhook URL to: `https://YOUR_BACKEND_URL/api/voice/incoming`
   - Set method to `HTTP POST`
   - Save configuration

3. **Test the setup**:
   - Call your Twilio phone number
   - You should hear: "Welcome to DataPulse incident response. Please state your command."
   - Speak one of the supported commands:
     - "What's the status?"
     - "Approve incident [ID]"
     - "Start patrol"

## Notes
- For local development, use [ngrok](https://ngrok.com) to expose your backend:
  `ngrok http 8000` (if backend runs on port 8000)
- Replace YOUR_BACKEND_URL with the ngrok URL (e.g., https://abc123.ngrok.io)
EOF
    
    echo "Manual instructions written to /opt/data/datapulse/TWILIO_SETUP.md"
    exit 1
fi

# Step 2: Check if twilio is authenticated
if ! twilio profiles:list &> /dev/null; then
    echo "ERROR: twilio CLI not authenticated. Run: twilio login"
    exit 1
fi

# Step 3: Get backend URL from user
read -p "Enter your DataPulse backend public URL (e.g., https://datapulse.example.com): " BACKEND_URL

if [ -z "$BACKEND_URL" ]; then
    echo "ERROR: Backend URL is required"
    exit 1
fi

# Remove trailing slash if present
BACKEND_URL=${BACKEND_URL%/}
WEBHOOK_URL="${BACKEND_URL}/api/voice/incoming"

echo "Webhook URL will be set to: $WEBHOOK_URL"

# Step 4: Buy a phone number (US)
echo "Buying a US phone number with Voice capability..."
TWILIO_NUMBER=$(twilio phone-numbers:buy --country-code US --voice-enabled --properties "phoneNumber" --no-header)

if [ -z "$TWILIO_NUMBER" ]; then
    echo "ERROR: Failed to buy phone number. Check Twilio account balance."
    exit 1
fi

echo "Purchased phone number: $TWILIO_NUMBER"

# Step 5: Configure webhook for the number
echo "Configuring webhook for $TWILIO_NUMBER..."
twilio phone-numbers:update --phone-number "$TWILIO_NUMBER" --voice-url "$WEBHOOK_URL"

if [ $? -eq 0 ]; then
    echo ""
    echo "=== Setup Complete ==="
    echo "Your DataPulse voice incident response number: $TWILIO_NUMBER"
    echo "Call this number to use voice commands!"
else
    echo "ERROR: Failed to configure webhook"
    exit 1
fi
