# Preferred rails for an intent:
# jq -c 'select(.record_type=="task_rail_preference" and .intent==$intent)' --arg intent dispatch_ticket graph/task-rail-preferences.jsonl

# Repository preferred rails sorted after slurp:
# jq -s 'sort_by(.repository.repository_id, -.usage_count)[] | {repository: .repository.repository_id, intent, rail, usage_count}' graph/task-rail-preferences.jsonl

# Slot adjustments by repository:
# jq -c '. as $p | .slot_adjustments[]? | {repository: $p.repository.repository_id, intent: $p.intent, rail: $p.rail, adjustment: .}' graph/task-rail-preferences.jsonl

# Drift candidates:
# jq -c 'select(.drift_status != "ok" and .drift_status != "unknown")' graph/task-rail-preferences.jsonl
