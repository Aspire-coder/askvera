---
type: "Reference"
title: "Quickstart"
openwiki_generated: true
---

## Deployment

```bash
sudo./deployment/deploy.sh
```

Deployment validates SSM configuration, runs tests, restarts the service, and verifies health. On failure, it rolls back to the previous Git revision.

Recent changes include updates to the deployment script to handle new configuration settings and improved rollback logic.