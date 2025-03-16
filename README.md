# Development Environment Onboarding

This project contains CloudFormation templates and scripts for setting up development environments. The project is organized into two main components with numbered templates to indicate deployment order.

## 1. Administrator Setup (`/admin-setup`)

Contains CloudFormation templates and scripts for administrators to set up the foundational infrastructure:

- **00-admin-main.yaml**: Main template that integrates all administrator components
- **01-admin-network-infrastructure.yaml**: VPC, subnets, and VPC endpoints
- **02-admin-app-manager-setup.yaml**: Application Manager configuration
- **03-admin-patch-management.yaml**: Patch management for development instances
- **04-admin-monitoring-dashboard.yaml**: CloudWatch dashboard for monitoring

The numbering indicates the deployment order and dependencies between resources.

### Deployment Instructions for Administrators

1. Navigate to the admin-setup directory:
   ```
   cd admin-setup
   ```

2. Run the deployment script:
   ```
   ./admin-deploy.sh
   ```

## 2. Developer Environment Setup (`/developer-setup`)

Contains CloudFormation templates and scripts for developers to set up their development environments:

- **00-developer-main.yaml**: Main template for developer environment
- **01-developer-ec2-instance.yaml**: EC2 instance configuration for development

### Deployment Instructions for Developers

1. Navigate to the developer-setup directory:
   ```
   cd developer-setup
   ```

2. Run the deployment script:
   ```
   ./developer-deploy.sh
   ```

3. Select your preferred instance specification:
   - Normal (4 GB RAM, 2 vCPU - t3.medium)
   - High (8 GB RAM, 2 vCPU - t3.large)
   - Extra (16 GB RAM, 4 vCPU - t3.xlarge)

4. Wait for the deployment to complete. The script will output your instance ID and connection instructions.

## Connecting to Your Development Environment

### Using AWS Session Manager (Recommended)

Connect to your instance using AWS Session Manager:

```bash
aws ssm start-session --target i-xxxxxxxxxxxxxxxxx
```

Replace `i-xxxxxxxxxxxxxxxxx` with your instance ID from the deployment output.

### Using SSH with VS Code

1. Install the VS Code Remote - SSH extension.

2. Add the following to your SSH config file (`~/.ssh/config`):
   ```
   Host dev-environment
     HostName i-xxxxxxxxxxxxxxxxx
     User ubuntu
     ProxyCommand sh -c "aws ssm start-session --target %h --document-name AWS-StartSSHSession --parameters 'portNumber=%p'"
   ```

3. Connect from VS Code:
   - Open the Command Palette (Ctrl+Shift+P)
   - Select "Remote-SSH: Connect to Host..."
   - Choose "dev-environment"

## Development Environment Features

Your development environment comes pre-installed with:

- Ubuntu 24.04 LTS
- Docker
- Node.js 22 (via latest nvm)
- AWS CDK
- AWS CLI v2
- Git and basic development tools

## Using AWS CDK

The instance has AWS CDK pre-installed and is configured with the necessary permissions for CDK deployments:

```bash
# Initialize a new CDK project
mkdir my-cdk-app && cd my-cdk-app
cdk init app --language typescript

# Deploy a CDK stack
cdk deploy
```

## Updating Your Environment

To change your instance specification (e.g., from Normal to High), simply run the deployment script again and select a different specification:

```bash
./developer-deploy.sh
```

## Prerequisites

- AWS CLI installed and configured
- AWS SSO login credentials
- For developers: The administrator must have completed the admin setup first

## Architecture

The development environment consists of:

1. A secure VPC with private subnets (01-admin-network-infrastructure.yaml)
2. Application Manager configuration (02-admin-app-manager-setup.yaml)
3. Patch management (03-admin-patch-management.yaml)
4. Monitoring dashboard (04-admin-monitoring-dashboard.yaml)
5. Developer-specific EC2 instances with Ubuntu 24.04, Node.js 22, and AWS CDK (01-developer-ec2-instance.yaml)

## Troubleshooting

### Connection Issues

If you cannot connect to your instance:

1. Verify your AWS SSO session is active:
   ```bash
   aws sts get-caller-identity
   ```

2. Check if your instance is running:
   ```bash
   aws ec2 describe-instances --instance-ids i-xxxxxxxxxxxxxxxxx --query 'Reservations[0].Instances[0].State.Name'
   ```

3. Ensure Session Manager plugin is installed:
   ```bash
   aws ssm start-session --help
   ```

### Deployment Failures

If deployment fails:

1. Check CloudFormation events:
   ```bash
   aws cloudformation describe-stack-events --stack-name DevEnv-YourName
   ```

2. Verify your IAM permissions are sufficient for creating the resources.

## Cleaning Up

To delete your development environment:

```bash
aws cloudformation delete-stack --stack-name DevEnv-YourName
```

## Support

For issues or questions, please contact the administrator team.
