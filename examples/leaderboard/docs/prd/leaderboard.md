Product request — Near-realtime leaderboards (from: Head of Live Ops)

Players keep asking where they stand. We want leaderboards in the game client:
- A global leaderboard plus one per region (EU, NA, APAC), for the current season (weekly seasons, reset Monday 00:00 UTC) and all-time.
- Players see the top 100 and "my rank" with the 10 players above and below them.
- A friends leaderboard (friends come from the profile service).
- Scores come from completed matches (game-api already publishes match.completed to Kafka). A player's season score is the sum of their match score deltas.
- It must feel live: after a match ends the new rank should show up within a second or two.
- Scale: 5M daily active players, ~40M total players. Peak 20k match completions per second during events, leaderboard reads peak around 60k/s.
- Ties: whoever reached the score first ranks higher.
- We had cheaters last season pushing absurd scores — we need to make sure bogus scores don't hit the board, and we must be able to remove a cheater and fix the board quickly.
- Must not show wrong ranks after an outage; it's fine to be briefly stale but not wrong.
- Launch target: 6 weeks.
