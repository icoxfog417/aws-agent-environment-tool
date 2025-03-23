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
├── application/     # Python CLI application code
├── infrastructure/  # CloudFormation templates for AWS infrastructure
│   ├── initial/     # Base infrastructure templates
│   └── template/    # Launch templates and service catalog configurations
├── .venv/           # Python virtual environment (created by uv)
├── pyproject.toml   # Python project configuration
└── README.md        # This file
```

## How to Use the Tool

### Prerequisites

- AWS CLI configured with appropriate credentials
- Python 3.12 or higher
- uv package manager

### How to Initialize the Environment

As an administrator, you need to set up the base infrastructure before agents can launch their working environments:

1. Install the required dependencies:

```bash
uv add boto3 click
```

2. Deploy the infrastructure:

```bash
python -m application.cli admin deploy [--region REGION]
```

#### Infrastructure Deployment Details

The deployment process creates several CloudFormation stacks that set up the complete environment:

```mermaid
flowchart TD
    A[Admin Deploy Command] --> B[Initial Infrastructure]
    A --> C[Template Infrastructure]
    
    B --> D[Main Admin Stack]
    B --> E[Network Infrastructure]
    B --> F[Service Catalog Setup]
    B --> G[Patch Management]
    B --> H[Monitoring Dashboard]
    
    C --> I[Launch Templates]
    C --> J[Service Catalog Registration]
    
    I --> K[Standard Environment]
    I --> L[High Performance Environment]
    I --> M[Extra Performance Environment]
    
    K --> N[t3.medium Instance]
    L --> O[t3.large Instance]
    M --> P[t3.xlarge Instance]
```

The deployment creates the following stacks:

1. **Initial Infrastructure (`infrastructure/initial/`)**
   - **Main Admin Stack (`00-admin-main.yaml`)**
     - Core stack that orchestrates the deployment of all other stacks
   - **Network Infrastructure (`01-admin-network-infrastructure.yaml`)**
     - VPC with private subnets
     - Security Groups for development access
     - SSM VPC Endpoints for secure instance management
   - **Service Catalog Setup (`02-admin-service-catalog-setup.yaml`)**
     - Service Catalog Portfolio configuration
     - Application Registry setup
     - S3 Bucket for artifacts
   - **Patch Management (`03-admin-patch-management.yaml`)**
     - Systems Manager Patch Baseline
   - **Monitoring Dashboard (`04-admin-monitoring-dashboard.yaml`)**
     - CloudWatch dashboards for environment monitoring
     - Alarms for idle instance detection

2. **Template Infrastructure (`infrastructure/template/`)**
   - **Launch Templates (`05-admin-launch-template.yaml`)**
     - EC2 Launch Templates for different instance types
   - **Service Catalog Registration (`06-admin-register-launch-templates.yaml`)**
     - Products for different environment sizes:
       - Standard: 4GB RAM, 2 vCPU (t3.medium)
       - High Performance: 8GB RAM, 2 vCPU (t3.large)
       - Extra Performance: 16GB RAM, 4 vCPU (t3.xlarge)

### How to Launch Environment and Connect Through VSCode

As an agent, you can launch your working environment:

1. Launch a new environment:

```bash
python -m application.cli developer launch [--region REGION] [--type standard|high|extra]
```

2. Check the status of your environment:

```bash
python -m application.cli developer status --name YOUR_ENVIRONMENT_NAME
```

3. Once the environment is ready, get the connection details:

```bash
python -m application.cli developer outputs --name YOUR_ENVIRONMENT_NAME
```

4. Connect to your environment through VSCode:
   - Install the "Remote - SSH" extension in VSCode
   - Use the connection details from the previous step to configure a new SSH host
   - Connect to the host through the Remote Explorer in VSCode

5. When you're done, terminate your environment:

```bash
python -m application.cli developer terminate --name YOUR_ENVIRONMENT_NAME
```

### Additional Commands

List all your provisioned environments:

```bash
python -m application.cli developer list [--region REGION]
```

## How to Contribute

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Commit your changes (`git commit -m 'Add some amazing feature'`)
5. Push to the branch (`git push origin feature/amazing-feature`)
6. Open a Pull Request

### Development Guidelines

- Use type hints for all Python code
- Follow PEP 8 style guidelines
- Write unit tests for new functionality
- Update documentation as needed

## License

This project is licensed under the terms of the license included in the [LICENSE](LICENSE) file.
