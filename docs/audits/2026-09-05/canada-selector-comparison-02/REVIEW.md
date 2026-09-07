# Aborted comparison - not a quality result

The Current worker stopped after recording two ordinary attempts and an error for the third case. The AWS SDK attempted `signin.CreateOAuth2Token` to refresh credentials inside the comparison's allowlisted wrapper. That operation was blocked; the worker stopped on the recorded isolation violation. Candidate never ran.

This was not a chatbot correctness failure or a completed safety gate. No blocked operation was allowed through and no allowlist was broadened. The existing AWS identity was subsequently verified outside the harness in us-east-1, allowing normal refresh without exposing token values. A fresh comparison uses a separate output directory. Preserve these original records.
