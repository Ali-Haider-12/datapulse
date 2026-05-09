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
