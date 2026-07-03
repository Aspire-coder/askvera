"""Application-scoped AWS client container."""

import boto3
from botocore.config import Config

from config import settings


class AwsClients:
    """Creates boto3 clients once using the EC2 IAM instance role."""

    def __init__(self) -> None:
        """Initialise reusable clients without explicit credentials."""
        client_config = Config(
            connect_timeout=settings.AWS_CONNECT_TIMEOUT_SECONDS,
            read_timeout=settings.AWS_READ_TIMEOUT_SECONDS,
            retries={"max_attempts": settings.AWS_MAX_ATTEMPTS, "mode": "standard"},
        )
        self.bedrock_agent_runtime = boto3.client("bedrock-agent-runtime", region_name=settings.AWS_REGION, config=client_config)
        self.bedrock_runtime = boto3.client("bedrock-runtime", region_name=settings.AWS_REGION, config=client_config)
        self.comprehend = boto3.client("comprehend", region_name=settings.AWS_REGION, config=client_config)
        self.firehose = boto3.client("firehose", region_name=settings.AWS_REGION, config=client_config)
        self.secretsmanager = boto3.client("secretsmanager", region_name=settings.AWS_REGION, config=client_config)
        self.s3 = boto3.client("s3", region_name=settings.AWS_REGION, config=client_config)
        self.sqs = boto3.client("sqs", region_name=settings.AWS_REGION, config=client_config)


aws_clients: AwsClients | None = None


def init_aws_clients() -> AwsClients:
    """Create and store application-scoped AWS clients."""
    global aws_clients
    aws_clients = AwsClients()
    return aws_clients


def get_aws_clients() -> AwsClients:
    """Return initialized AWS clients."""
    if aws_clients is None:
        return init_aws_clients()
    return aws_clients
