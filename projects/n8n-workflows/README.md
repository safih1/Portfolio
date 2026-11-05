# n8n Workflows

Ready-to-import automation templates. Each file is an n8n workflow export.

| File | What it does | Main nodes |
|---|---|---|
| `jobadder_transcription_workflow.json` | Reads a call log sheet, pulls JobAdder candidates, matches by phone, and writes transcripts back as notes | Google Sheets, HTTP Request, Code |
| `n8n_daily_report_workflow.json` | Builds a weekday sales report and posts/emails it to the team | Schedule, Google Sheets, Slack, Email |
| `n8n_ecommerce_workflow.json` | Handles new Shopify orders: logs them, alerts the team, emails the customer, and updates inventory | Webhook, Google Sheets, Slack, Email, IF |
| `n8n_lead_automation_workflow.json` | Captures leads from a webhook, validates them, saves to Sheets, creates a HubSpot contact, and notifies sales | Webhook, IF, Google Sheets, HubSpot, Email |
| `n8n_lead_workflow.json` | Sends a first-touch email to pending leads and tracks status | Schedule, Google Sheets, Gmail, Slack |

## Import

1. Open n8n and go to **Workflows → Import from file**.
2. Pick a JSON file.
3. Open each node and select your own credentials.
4. Replace the placeholder values:
   - `YOUR_GOOGLE_SHEET_URL`
   - `YOUR_FOLDER_ID`
   - `yourbusiness.com` email addresses and links
   - Webhook paths, if you want unique ones
5. Test the workflow manually before activating it.

## Notes

- Credential blocks and instance IDs were removed from these exports, so n8n will ask you to choose credentials on import.
- The templates reference Google Sheets, Slack, Gmail, HubSpot, Shopify, and JobAdder. You need accounts and OAuth connections for the services you use.
- Review triggers (schedules, webhooks) before turning a workflow on so you don't send duplicate messages.
