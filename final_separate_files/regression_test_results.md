# Week 4 Regression Test Results

| Case | Baseline | Post-fix | Post-fix failures |
| --- | --- | --- | --- |
| happy_age4_blocks_patience | FAIL (moral_alignment) | FAIL | required_interests_included; moral_alignment |
| happy_age8_forest_confidence | FAIL (required_interests_included; theme_alignment; child_safe_content) | FAIL | required_interests_included |
| known_failure_exact_character_name_leak | FAIL (age_appropriate_length; required_interests_included; moral_alignment) | FAIL | required_interests_included; moral_alignment |
| happy_age6_space_soccer_kindness | PASS (none) | PASS | none |

The regression sample includes three previously failing examples and one previously passing example. The passing example stayed passing; the failed examples still need a deterministic repair loop for missing interests.
