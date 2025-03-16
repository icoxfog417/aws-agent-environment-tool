# Development Environment Administration Guide

This guide explains how to set up and manage the AWS development environment infrastructure for your team.

## Prerequisites

- AWS CLI installed and configured
- Administrator access to your AWS account
- IAM Identity Center (SSO) configured for your organization

## Initial Setup

### 1. Deploy Base Infrastructure

Run the admin deployment script to set up the base infrastructure:

```bash
./admin-deploy.sh
```

This script deploys the main CloudFormation template (`00-admin-main.yaml`), which includes:
- Network infrastructure (VPC, subnets, SSM endpoints)
- Application Manager configuration (without AttributeGroups)
- Patch management system for Ubuntu instances
- CloudWatch monitoring dashboard for instance count tracking

### 2. Configure IAM Identity Center

1. Go to the AWS IAM Identity Center console
2. Create permission sets for your developers and administrators
3. Assign appropriate permissions:
   - For developers: EC2, SSM, and CloudFormation access with appropriate restrictions
   - For administrators: Full access to manage the environment
4. Add your team members to the appropriate permission sets

### 3. Verify Infrastructure

1. Check that all CloudFormation stacks deployed successfully:
   ```bash
   aws cloudformation describe-stacks --stack-name DevEnvironment-Admin-Setup
   ```

2. Verify that the Application Manager shows the DevEnvironment application:
   ```bash
   aws servicecatalog-appregistry list-applications
   ```

3. Check that the CloudWatch dashboard is displaying correctly:
   ```bash
   aws cloudwatch list-dashboards
   ```

## Managing Environments

Use the admin management script to manage developer environments:

```bash
# List all environments
./admin-manage-environments.sh list

# Stop inactive environments
./admin-manage-environments.sh stop-inactive

# Update all environments
./admin-manage-environments.sh update-all
```

## Maintenance Commands

### View Resources

```bash
# List all stacks in the environment
aws cloudformation list-stacks --stack-status-filter CREATE_COMPLETE UPDATE_COMPLETE

# View details of the main stack
aws cloudformation describe-stacks --stack-name DevEnvironment-Admin-Setup

# List all nested stacks
aws cloudformation list-stack-resources --stack-name DevEnvironment-Admin-Setup

# List all EC2 instances with the project tag
aws ec2 describe-instances --filters "Name=tag:Project,Values=DevelopmentEnv" --query "Reservations[].Instances[]"

# Check patch compliance status for Ubuntu instances
aws ssm list-compliance-items --resource-ids $(aws ec2 describe-instances --filters "Name=tag:Project,Values=DevelopmentEnv" --query "Reservations[].Instances[].InstanceId" --output text) --resource-types ManagedInstance
```

### Update Infrastructure

```bash
# Update the entire environment
./admin-deploy.sh

# Update a specific component template and deploy it
# Example for updating the network infrastructure:
aws cloudformation update-stack \
  --stack-name DevEnvironment-Network \
  --template-body file://01-admin-network-infrastructure.yaml \
  --parameters ParameterKey=ProjectTag,ParameterValue=DevelopmentEnv ParameterKey=ManagedByTag,ParameterValue=Administrator

# Apply patches immediately to all instances
aws ssm send-command \
  --document-name "AWS-RunPatchBaseline" \
  --targets "Key=tag:Project,Values=DevelopmentEnv" \
  --parameters "Operation=Install,RebootOption=RebootIfNeeded"
```

### Cost Optimization

```bash
# List running instances with their details
aws ec2 describe-instances \
  --filters "Name=instance-state-name,Values=running" "Name=tag:Project,Values=DevelopmentEnv" \
  --query "Reservations[].Instances[].{ID:InstanceId,Type:InstanceType,AZ:Placement.AvailabilityZone,State:State.Name}"

# Check the CloudWatch alarm for idle instances
aws cloudwatch describe-alarms \
  --alarm-names "DevelopmentEnv-IdleInstancesAlarm"

# Stop idle instances (low CPU for extended period)
aws ec2 stop-instances --instance-ids <instance-id>

# Get CPU utilization metrics for an instance over the past 24 hours
aws cloudwatch get-metric-statistics \
  --namespace AWS/EC2 \
  --metric-name CPUUtilization \
  --dimensions Name=InstanceId,Value=<instance-id> \
  --start-time $(date -d '24 hours ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date +%Y-%m-%dT%H:%M:%S) \
  --period 3600 \
  --statistics Average
```

## Troubleshooting

### Common Issues

1. **SSM Connection Issues**
   - Verify that all three SSM endpoints are working:
     ```bash
     aws ec2 describe-vpc-endpoints \
       --filters "Name=vpc-id,Values=$(aws cloudformation describe-stacks --stack-name DevEnvironment-Admin-Setup --query "Stacks[0].Outputs[?OutputKey=='VpcId'].OutputValue" --output text)"
     ```
   - Check that the instance has the SSM agent installed and running:
     ```bash
     aws ssm describe-instance-information
     ```

2. **Permission Problems**
   - Verify that the developer has the correct permission set in IAM Identity Center
   - Check that the instance has the correct tags:
     ```bash
     aws ec2 describe-tags --filters "Name=resource-id,Values=<instance-id>"
     ```

3. **CloudFormation Deployment Failures**
   - Check CloudFormation events for specific error messages:
     ```bash
     aws cloudformation describe-stack-events --stack-name DevEnvironment-Admin-Setup
     ```
   - Validate templates before deployment:
     ```bash
     aws cloudformation validate-template --template-body file://00-admin-main.yaml
     ```

For additional help, refer to the AWS documentation or contact AWS Support.
