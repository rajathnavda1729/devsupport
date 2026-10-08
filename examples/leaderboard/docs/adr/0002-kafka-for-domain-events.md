---
status: accepted
date: 2024-05-03
tags: [messaging, events]
---
# Kafka for domain events

## Context and Problem Statement
Services need to react to gameplay events (match completed, purchase made) without tight coupling.

## Decision Outcome
Chosen option: "Kafka (MSK)", because it gives durable, replayable, partitioned event streams.
All cross-service domain events are published to Kafka topics keyed by player id, retained 7 days.
