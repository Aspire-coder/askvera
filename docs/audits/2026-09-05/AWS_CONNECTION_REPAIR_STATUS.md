# Secure connection repair investigation - 2026-09-06

- User clarified that the deployed environment is a test environment with no users.
- Existing askvera-review AWS session verified successfully: account 615592621509, IAM identity pavan410. No new login required.
- Initial sandbox check could not access the AWS profile; the permitted outside-sandbox identity check succeeded. Do not interpret the initial error as a missing profile.
- Nonsecret MCP initialization and all available tool-list pages succeeded. Eight tools were returned, including aws___run_script but not aws___call_aws.
- The installed official asm-exec and upstream main still require aws___call_aws. Reinstalling that same implementation does not establish a repair.
- No secret was requested, no database query was run, and no deployed service was changed.

## Supported alternative to investigate

The official wrapper also supports a localhost Secrets Manager Agent backend. Current AWS documentation calls this the AWS Workload Credentials Provider and provides a signed Windows binary. A temporary local instance could avoid the incompatible MCP resolver without changing EC2 or exposing RDS publicly.

Before use: obtain approval for the additional credential-handling process, verify its signature/checksum, confirm loopback-only binding and SSRF token handling, disable file logging/prefetch, and verify wrapper compatibility. Use only asm-exec dynamic references for secret resolution, never direct daemon requests. Stop the helper and any database tunnel after the bounded read-only export. This alternative is not installed or verified yet.

## Follow-up: approved local helper verified

- User approved installation. Downloaded official AWS Workload Credentials Provider 3.1.1 Windows binary into the workspace's `.aws-helper-tools` directory, outside the application checkout.
- SHA-256 matched AWS documentation: `5fbdac4017e630556b94b90e5ed9ed11be69ac7a47e67655e20181ce990dbe12`; Windows Authenticode status Valid, signer Amazon Web Services, Inc.
- No persistent Windows service installed. Configuration disables file logging and uses a small cache, with no prefetch configuration.
- Initial profile-based startup failed with dispatch failure. Supplying the existing short-lived AWS session in memory through the official wrapper's credential loader allowed startup. This indicates a credential-loading compatibility issue; its precise SDK cause was not traced.
- Verified the running process had only loopback listening addresses before resolving any database credential.
- The unchanged official asm-exec resolved the database password reference into a child process. The child returned only a fixed success message. No credential was displayed or saved.
- Temporary helper stopped successfully after the check. No database connection, metadata export, EC2 change, or chatbot deployment occurred.
- Secure credential resolution is now verified. Next: re-establish the private database tunnel and run the bounded read-only metadata export, then build the matched evaluation snapshot.

References:
- https://docs.aws.amazon.com/secretsmanager/latest/userguide/workload-credentials-provider.html
- https://github.com/aws/agent-toolkit-for-aws/blob/main/plugins/aws-core/skills/aws-secrets-manager/references/asm-exec
