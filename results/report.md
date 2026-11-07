# Pilot report

Records: 50. F1 is base-pair F1; invalid predictions score 0.

## Summary per method

| method | n | valid | P | R | F1 | F1 (valid only) | F1 ±1 slip | latency s | tokens in/out |
|---|---|---|---|---|---|---|---|---|---|
| rnafold | 50 | 50/50 | 0.625 | 0.693 | 0.654 | 0.654 | 0.673 | 0.014 | 0/0 |

## Exact F1 per family

| method | 16S_rRNA | 5S_rRNA | RNaseP | SRP | tRNA | tmRNA |
|---|---|---|---|---|---|---|
| rnafold | 0.588 (n=12) | 0.644 (n=11) | 0.647 (n=3) | 0.692 (n=12) | 0.663 (n=11) | 1.000 (n=1) |

## Failure taxonomy (primary class)

| method | call_error | no_structure | invalid_chars | unbalanced | length_mismatch | empty_prediction | low_f1 | ok |
|---|---|---|---|---|---|---|---|---|
| rnafold | 0 | 0 | 0 | 0 | 0 | 0 | 13 | 37 |

## Flags

| method | flags |
|---|---|
| rnafold | slip_sensitive: 2 |

Taxonomy definitions: see evals/taxonomy.py.
