# Detecting Overspending and Unusual Transactions

## Budget status thresholds
- Under 80% of category budget used: on track.
- 80-100%: warning; mention remaining amount and days left in month.
- Over 100%: overspent; show overage and suggest which category could be trimmed.

## Pace check
Compare share of budget used with share of month elapsed. 70% of the dining budget gone in the first 10 days of a 30-day month signals overspending even though it is under 80%.

## Anomaly rules
- A transaction more than 3x the user's median in that category is unusual.
- The same merchant and amount twice within 48 hours may be a duplicate charge.
- A category with spend 50% above its 3-month average deserves a mention.
- New merchants with large amounts should be confirmed with the user.

## Agent guidance
Flag anomalies as questions, not accusations: "This looks higher than usual - was it expected?" Never report an anomaly without citing the transaction date, merchant and amount from tool output.
