# AWS Agent Environment Tool

A command-line tool for setting up and managing cloud environments (EC2 instances) for agents that can connect through VSCode.

## Purpose

This tool provides a streamlined way to:

1. Set up the necessary AWS infrastructure for agent working environments
2. Launch and manage EC2 instances configured for agents to work efficiently
3. Connect to these environments through VSCode
4. Manage the lifecycle of agent environments

## Folder Structure

```
onboarding/
├── application/        # Python CLI application code
│   ├── __init__.py
│   └── cli.py          # CLI implementation
├── infrastructure/     # CloudFormation templates for AWS infrastructure
│   ├── 01-base-deployment.yaml    # Base deployment template
│   ├── 03-product-template.yaml   # Product template
│   ├── 04-product-service-template.yaml  # Service template
│   ├── 01-base/       # Base infrastructure templates
│   │   ├── 01-network-infrastructure.yaml
│   │   └── 02-service-catalog.yaml
│   ├── 02-template/   # Launch templates for EC2 instances 
│   │   └── ubuntu-template.yaml
│   ├── 03-product/    # Generated product templates (created during deployment)
│   ├── 04-product-service/ # Generated service templates (created during deployment)
│   └── experimental/   # Experimental features
│       ├── 0a-admin-patch-management.yaml
│       └── 0b-admin-monitoring-dashboard.yaml
├── tests/             # Test directory
├── pyproject.toml     # Python project configuration
├── uv.lock            # Package lock file for uv package manager
└── README.md          # This file
```

## How to Use the Tool

### Prerequisites

- AWS CLI configured with appropriate credentials
- Python 3.12 or higher
- uv package manager

### Setup for Administrators

As an administrator, you need to set up the base infrastructure before agents can launch their working environments:

1. Install the required dependencies:

```bash
uv add boto3 click
```

2. Deploy the infrastructure:

```bash
uv run python -m application.cli admin deploy [--region REGION] [--artifact-bucket-name NAME]
```

Options:
- `--region`: Specify an AWS region (defaults to the region from AWS configuration)
- `--artifact-bucket-name`: Name for the S3 bucket to store artifacts (will be suffixed with account ID)

### Launching Development Environments for Developers

Once the administrator has set up the infrastructure, developers can launch their own environments:

```bash
uv run python -m application.cli developer launch --region REGION --key KEY_NAME --type TYPE
```

Required parameters:
- `--region`: AWS region where the infrastructure is deployed
- `--key`: Name of an existing EC2 key pair for SSH access
- `--type`: Type of environment to launch (standard, high, or extra)
  - standard: 4GB RAM, 2 vCPU (t3.medium)
  - high: 8GB RAM, 2 vCPU (t3.large)
  - extra: 16GB RAM, 4 vCPU (t3.xlarge)

After launching an environment, you'll receive instructions on how to connect to the instance.

## Infrastructure Deployment Details

The infrastructure deployment process includes:
1. Creating an S3 bucket for CloudFormation templates and artifacts
2. Deploying base network infrastructure (VPC, subnets, etc.)
3. Setting up Service Catalog with launch templates
4. Creating product templates for different environment types

The deployment is handled through AWS CloudFormation to ensure consistent and repeatable infrastructure.

