#!/bin/bash

# Deploy the base infrastructure for development environments
# This script should be run once by an administrator

set -e

STACK_NAME="DevEnvironment-Admin-Setup"
REGION=$(aws configure get region)
if [ -z "$REGION" ]; then
    REGION="us-east-1"
    echo "No AWS region found in configuration, defaulting to $REGION"
fi

# Check if AWS CLI is installed
if ! command -v aws &> /dev/null; then
    echo "AWS CLI is not installed. Please install it first."
    exit 1
fi

# Check if user is authenticated
aws sts get-caller-identity > /dev/null 2>&1
if [ $? -ne 0 ]; then
    echo "Not authenticated with AWS. Please run 'aws sso login' first."
    exit 1
fi

echo "Deploying administrator setup to region: $REGION"

# Check if the stack exists
if aws cloudformation describe-stacks --stack-name $STACK_NAME --region $REGION 2>&1 | grep -q 'Stack with id'; then
    # Update the stack
    echo "Updating existing stack: $STACK_NAME"
    aws cloudformation deploy \
        --template-file 00-admin-main.yaml \
        --stack-name $STACK_NAME \
        --capabilities CAPABILITY_NAMED_IAM \
        --region $REGION \
        --tags ManagedBy=CloudFormation Environment=Development
else
    # Create the stack
    echo "Creating new stack: $STACK_NAME"
    aws cloudformation deploy \
        --template-file 00-admin-main.yaml \
        --stack-name $STACK_NAME \
        --capabilities CAPABILITY_NAMED_IAM \
        --region $REGION \
        --tags ManagedBy=CloudFormation Environment=Development
fi

# Wait for stack to complete
echo "Waiting for stack deployment to complete..."
aws cloudformation wait stack-update-complete --stack-name $STACK_NAME --region $REGION || \
aws cloudformation wait stack-create-complete --stack-name $STACK_NAME --region $REGION

echo "Administrator setup complete!"
