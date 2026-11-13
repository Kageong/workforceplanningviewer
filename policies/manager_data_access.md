# Manager data access

- Only users with role **Manager** may query workforce data through this application.
- Each manager is scoped to a single `working_unit_id`.
- Cross-unit employee or shift visibility is prohibited.
- Employee **email** and **contact_number** may be queried but model output is redacted to show only the **last 5 characters** of each value.
