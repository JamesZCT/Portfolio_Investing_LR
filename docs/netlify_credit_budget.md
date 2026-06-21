# Netlify Credit Budget

This project should treat Netlify as the production website host, not as the daily compute engine.

## Current Cost Model

Netlify credit-based pricing currently charges:

- Production deploy: 15 credits per successful production publish.
- Preview and branch deploys: free.
- Web requests: 2 credits per 10,000 requests.
- Bandwidth: 20 credits per GB.
- Compute: 10 credits per GB-hour.
- AI inference through Netlify AI Gateway or Agent Runners: model-dependent; Netlify converts model cost to credits.

The Free plan includes 300 credits per month. For this project, the expensive part is production deploy count, not local LLM inference.

## Operating Policy

The RTX 3090 Ti Windows runner should refresh market data and LLM sentiment locally, then commit JSON snapshots to GitHub.

Netlify production publishes should happen only when one of these is true:

- Weekly Friday production publish after market close.
- Manual workflow run with `deploy_to_netlify=true`.
- Urgent website/UI fix that should go live immediately.

Daily scheduled refreshes should be compute-only and should not publish to Netlify production.

## Expected Monthly Netlify Cost

Approximate deploy-only budget:

- Weekly production publish: 4 to 5 deploys/month = 60 to 75 credits/month.
- Manual emergency deploys: 15 credits each.
- Daily trading-day production publish: about 21 deploys/month = 315 credits/month, which exceeds the Free plan before traffic.

Target budget: keep this project at or below 75 credits/month, around 25% of the Free plan.

## Future Lower-Credit Architecture

To make the public site update daily without daily production deploys, move refreshed JSON outside the Netlify deploy artifact. Options:

- GitHub raw/CDN-backed snapshot URLs.
- Cloudflare R2 or another cheap object store.
- Supabase Storage.
- A tiny API endpoint hosted somewhere other than Netlify Functions.

Then Netlify can host the app shell and deploy only when the UI changes, while the dashboard fetches fresh JSON from the external data store.

