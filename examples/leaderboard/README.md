# Arcadia Games platform (demo monorepo)

Services:
- `services/game-api` — match lifecycle, emits `match.completed` events to Kafka
- `services/profile` — player profiles, friends graph (PostgreSQL)
- `services/leaderboard` — new: near-realtime rankings (this is the feature being designed)
