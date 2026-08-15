# Exception alert email (plain text)

Subject: `potions: ALERT <hub> — <exception class>`

```text
ALERT: <incomplete | pending_normalization | validation_fail | job_error>

Market/variant: <…>
Detail: <one or two lines from RUN_COMPLETE / log>

Do not promote until resolved.
Hub: live/state/<hub>/
```
