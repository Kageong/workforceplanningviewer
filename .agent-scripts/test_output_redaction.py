# Purpose: Verify after-model email/phone masking keeps last 5 chars.
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from callbacks.output_redaction import redact_sensitive_text

sample = "Nina: nina.patel@corp.local, phone +60123451001"
out = redact_sensitive_text(sample)
assert "51001" in out and out.count("*") > 3, out
print(out)
print("redaction_ok")
