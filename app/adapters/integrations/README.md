# Integration Adapters

This package will hold external business-system adapters, for example:

- Gmail
- Slack
- GitHub
- HubSpot
- Notion
- WhatsApp
- Stripe

Each integration should converge on the same pattern:

1. adapter client
2. auth/refresh handling
3. sync translation
4. execution handlers
