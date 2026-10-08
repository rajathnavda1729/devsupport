"""match.completed event (published to Kafka topic `match.completed`, key = player_id)."""
MATCH_COMPLETED_SCHEMA = {
    "event_id": "uuid",
    "player_id": "uuid",
    "match_id": "uuid",
    "region": "eu|na|apac",
    "score_delta": "int",
    "completed_at": "iso8601",
}
