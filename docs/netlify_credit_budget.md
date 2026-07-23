# Netlify Credit Budget

This project treats GitHub Pages as the daily public host. Netlify is a manual backup channel, not the daily compute engine.

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

- Manual workflow run with `deploy_to_netlify=true`.
- Urgent website/UI fix that should go live immediately.

Daily scheduled refreshes should be compute-only and should not publish to Netlify production.

## Expected Monthly Netlify Cost

Approximate deploy-only budget:

- Scheduled production publish: 0 deploys/month = 0 deploy credits/month.
- Manual emergency deploys: 15 credits each.
- Daily trading-day production publish: about 21 deploys/month = 315 credits/month, which exceeds the Free plan before traffic.

Target budget: zero scheduled Netlify deploy credits. GitHub Pages handles routine public refreshes.

## Implemented Lower-Credit Architecture

The self-hosted runner commits refreshed public JSON to GitHub. GitHub Pages rebuilds the app and serves those committed snapshots without consuming Netlify deploy credits.

