# 1. PostgreSQL as the system of record

Date: 2024-02-12

## Status

Accepted

## Context

Player, match and purchase data needs transactions and strong consistency.

## Decision

We will use PostgreSQL 15 (managed, Multi-AZ) as the system of record for all player-owned data.
Caches and derived stores are allowed but must be rebuildable from PostgreSQL or the event log.

## Consequences

Derived read models must document how they are rebuilt.
