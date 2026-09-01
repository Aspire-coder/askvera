"""Application-scoped AWS client container."""

import boto3
from botocore.config import Config

from config import settings


def _client_config(*, read_timeout: int, max_attempts: int) -> Config:
    """Build a bounded client budget using total request attempts."""
    return Config(
        connect_timeout=settings.AWS_CONNECT_TIMEOUT_SECONDS,
        read_timeout=read_timeout,
        retries={"total_max_attempts": max_attempts, "mode": "standard"},
    )


class AwsClients:
    """Creates boto3 clients once using the EC2 IAM instance role."""

    def __init__(self) -> None:
        """Initialise reusable clients without explicit credentials."""
        background_config = _client_config(
            read_timeout=settings.AWS_READ_TIMEOUT_SECONDS,
            max_attempts=settings.AWS_MAX_ATTEMPTS,
        )
        interactive_config = _client_config(
            read_timeout=settings.AWS_INTERACTIVE_READ_TIMEOUT_SECONDS,
            max_attempts=settings.AWS_INTERACTIVE_MAX_ATTEMPTS,
        )
        pii_config = _client_config(
            read_timeout=settings.AWS_PII_READ_TIMEOUT_SECONDS,
            max_attempts=settings.AWS_PII_MAX_ATTEMPTS,
        )
        self.bedrock_agent_runtime = boto3.client("bedrock-agent-runtime", region_name=settings.AWS_REGION, config=background_config)
        self.bedrock_runtime = boto3.client("bedrock-runtime", region_name=settings.AWS_REGION, config=interactive_config)
        self.bedrock_embedding_runtime = boto3.client(
            "bedrock-runtime", region_name=settings.AWS_REGION, config=background_config
        )
        self.comprehend = boto3.client("comprehend", region_name=settings.AWS_REGION, config=pii_config)
        self.cognito_idp = boto3.client(
            "cognito-idp",
            region_name=settings.ADMIN_COGNITO_REGION or settings.AWS_REGION,
            config=background_config,
        )
        self.firehose = boto3.client("firehose", region_name=settings.AWS_REGION, config=background_config)
        self.secretsmanager = boto3.client("secretsmanager", region_name=settings.AWS_REGION, config=background_config)
        self.s3 = boto3.client("s3", region_name=settings.AWS_REGION, config=background_config)
        self.ses = boto3.client("ses", region_name=settings.AWS_REGION, config=background_config)
        self.sqs = boto3.client("sqs", region_name=settings.AWS_REGION, config=background_config)
        self.textract = boto3.client("textract", region_name=settings.AWS_REGION, config=background_config)


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
