#!/bin/bash

# Deploy a development environment for a developer
# This script should be run by each developer to create their environment

set -e

# Check if AWS CLI is installed
if ! command -v aws &> /dev/null; then
    echo "AWS CLI is not installed. Please install it first."
    exit 1
fi

# Check if user is authenticated with AWS SSO
aws sts get-caller-identity > /dev/null 2>&1
if [ $? -ne 0 ]; then
    echo "Not authenticated with AWS. Please run 'aws sso login' first."
    exit 1
fi

# Get SSO user information
SSO_USER_INFO=$(aws sts get-caller-identity --query 'Arn' --output text)
DEVELOPER_NAME=$(echo $SSO_USER_INFO | cut -d'/' -f2)
DEVELOPER_EMAIL="${DEVELOPER_NAME}@company.com"  # Adjust as needed

# Set region if not already set
if [ -z "$AWS_REGION" ]; then
    export AWS_REGION="us-east-1"  # Change to your preferred region
    echo "AWS_REGION not set, using default: $AWS_REGION"
fi

# Ask for instance specification
echo "Select instance specification:"
echo "1) Normal (4 GB RAM, 2 vCPU - t3.medium)"
echo "2) High (8 GB RAM, 2 vCPU - t3.large)"
echo "3) Extra (16 GB RAM, 4 vCPU - t3.xlarge)"
read -p "Enter your choice [1]: " INSTANCE_CHOICE

case $INSTANCE_CHOICE in
    2) INSTANCE_SPEC="High" ;;
    3) INSTANCE_SPEC="Extra" ;;
    *) INSTANCE_SPEC="Normal" ;;
esac

echo "Deploying development environment for $DEVELOPER_EMAIL with instance specification: $INSTANCE_SPEC"

# Create a stack name based on developer name
STACK_NAME="DevEnv-$(echo $DEVELOPER_NAME | tr ' ' '-')"

# Deploy the CloudFormation stack
aws cloudformation deploy \
  --template-file 00-developer-main.yaml \
  --stack-name $STACK_NAME \
  --capabilities CAPABILITY_IAM \
  --parameter-overrides \
    InstanceSpec=$INSTANCE_SPEC \
    DeveloperEmail=$DEVELOPER_EMAIL \
    ProjectTag=DevelopmentEnv \
    ManagedByTag=Developer \
  --tags Project=DevelopmentEnv ManagedBy=Developer Email=$DEVELOPER_EMAIL

# Wait for stack to complete
echo "Waiting for stack deployment to complete..."
aws cloudformation wait stack-create-complete --stack-name $STACK_NAME || \
aws cloudformation wait stack-update-complete --stack-name $STACK_NAME

# Get instance ID and other outputs
INSTANCE_ID=$(aws cloudformation describe-stacks --stack-name $STACK_NAME --query "Stacks[0].Outputs[?OutputKey=='InstanceId'].OutputValue" --output text)
INSTANCE_TYPE=$(aws cloudformation describe-stacks --stack-name $STACK_NAME --query "Stacks[0].Outputs[?OutputKey=='SelectedInstanceType'].OutputValue" --output text)
INSTANCE_MEMORY=$(aws cloudformation describe-stacks --stack-name $STACK_NAME --query "Stacks[0].Outputs[?OutputKey=='InstanceMemory'].OutputValue" --output text)
INSTANCE_CPU=$(aws cloudformation describe-stacks --stack-name $STACK_NAME --query "Stacks[0].Outputs[?OutputKey=='InstanceCPU'].OutputValue" --output text)

echo "Development environment deployed successfully!"
echo "Instance ID: $INSTANCE_ID"
echo "Instance Type: $INSTANCE_TYPE ($INSTANCE_MEMORY, $INSTANCE_CPU)"
echo ""
echo "To connect to your instance using Session Manager:"
echo "aws ssm start-session --target $INSTANCE_ID --region $AWS_REGION"
echo ""
echo "For more information on how to use your development environment,"
echo "please refer to the README.md file."
