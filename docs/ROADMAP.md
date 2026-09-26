# Roadmap

1. Add a real detector plugin behind the existing availability/event contract. Start with one scoped event (person-down or obstruction), document model/license provenance, temporal tracking needs, calibration, evaluation clips, false-positive/false-negative measures, and hardware profile. Keep it disabled until those checks are met.
2. Build a consented, privacy-reviewed local evaluation set with representative camera angles, lighting, occlusion, and negative scenes. Evaluate temporal duration, cooldown, recurrence, and event-to-snapshot alignment before operator trials.
3. Add an editable normalized polygon/rectangle zone UI, explicit schedule/timezone evaluation, and bounded administrator connection-check endpoint; verify letterbox mapping and source safety policies.
4. Add deployment hardening for password reset/session revocation, secure reverse-proxy/TLS operation, scheduled evidence cleanup, backup/restore of encryption keys, and Compose/PostgreSQL CI.
5. Add external notification channels and short clips only behind durable delivery state, deduplication, retention controls, and tests. Keep current notification and evidence claims limited to in-app/snapshot behavior.
