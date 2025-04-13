#!/usr/bin/env python3
"""
Onboarding CLI - A tool for managing development environments
"""

import os
import sys
import getpass
import json
import datetime
import time
from pathlib import Path
import click
import boto3
from botocore.exceptions import ClientError, NoCredentialsError
from typing import Optional, Dict, List, Any, Tuple


def check_aws_credentials() -> bool:
    """Check if AWS credentials are available and valid"""
    try:
        sts = boto3.client('sts')
        sts.get_caller_identity()
        return True
    except (ClientError, NoCredentialsError):
        return False


def get_aws_region() -> str:
    """Get the AWS region from configuration or use default"""
    session = boto3.session.Session()
    region = session.region_name
    if not region:
        region = "us-east-1"
        click.echo(f"No AWS region found in configuration, defaulting to {region}")
    return region


def deploy_cloudformation_stack(template_path: str, stack_name: str, region: str, parameters: Optional[Dict[str, str]] = None) -> None:
    """Deploy a CloudFormation stack using boto3"""
    cf_client = boto3.client('cloudformation', region_name=region)
    
    # Read the template file
    with open(template_path, 'r') as file:
        template_body = file.read()
    
    # Check if stack exists
    stack_exists = False
    try:
        cf_client.describe_stacks(StackName=stack_name)
        stack_exists = True
    except ClientError as e:
        if 'does not exist' not in str(e):
            click.echo(f"Error checking stack: {e}", err=True)
            sys.exit(1)
    
    action = "Updating" if stack_exists else "Creating"
    click.echo(f"{action} stack: {stack_name}")
    
    # Convert parameters to CloudFormation format if provided
    cf_parameters = []
    if parameters:
        for key, value in parameters.items():
            cf_parameters.append({
                'ParameterKey': key,
                'ParameterValue': value
            })
    
    # Deploy the stack
    try:
        if stack_exists:
            cf_client.update_stack(
                StackName=stack_name,
                TemplateBody=template_body,
                Parameters=cf_parameters,
                Capabilities=['CAPABILITY_NAMED_IAM'],
                Tags=[
                    {'Key': 'ManagedBy', 'Value': 'Administrator'},
                    {'Key': 'Environment', 'Value': 'Development'}
                ]
            )
        else:
            cf_client.create_stack(
                StackName=stack_name,
                TemplateBody=template_body,
                Parameters=cf_parameters,
                Capabilities=['CAPABILITY_NAMED_IAM'],
                Tags=[
                    {'Key': 'ManagedBy', 'Value': 'Administrator'},
                    {'Key': 'Environment', 'Value': 'Development'}
                ]
            )
        
        # Wait for stack to complete
        click.echo(f"Waiting for {stack_name} deployment to complete...")
        waiter_type = 'stack_update_complete' if stack_exists else 'stack_create_complete'
        waiter = cf_client.get_waiter(waiter_type)
        waiter.wait(StackName=stack_name)
        
    except ClientError as e:
        if 'No updates are to be performed' in str(e):
            click.echo(f"No updates needed for stack {stack_name}")
        else:
            click.echo(f"Error deploying stack: {e}", err=True)
            sys.exit(1)


def check_s3_bucket_exists(bucket_name: str, region: str) -> bool:
    """Check if an S3 bucket exists"""
    s3_client = boto3.client('s3', region_name=region)
    
    try:
        s3_client.head_bucket(Bucket=bucket_name)
        return True
    except ClientError as e:
        error_code = int(e.response['Error']['Code'])
        if error_code == 404:
            return False
        else:
            click.echo(f"Error checking bucket: {e}", err=True)
            sys.exit(1)


def create_s3_bucket(bucket_name: str, region: str) -> None:
    """Create an S3 bucket with versioning and encryption enabled"""
    s3_client = boto3.client('s3', region_name=region)
    
    click.echo(f"Creating S3 bucket: {bucket_name}")
    try:
        # AWS requires different API calls for us-east-1 vs other regions
        # For us-east-1, specifying LocationConstraint causes an error
        if region == 'us-east-1':
            s3_client.create_bucket(Bucket=bucket_name)
        else:
            s3_client.create_bucket(
                Bucket=bucket_name,
                CreateBucketConfiguration={'LocationConstraint': region}
            )
        
        # Enable versioning
        s3_client.put_bucket_versioning(
            Bucket=bucket_name,
            VersioningConfiguration={'Status': 'Enabled'}
        )
        
        # Enable encryption
        s3_client.put_bucket_encryption(
            Bucket=bucket_name,
            ServerSideEncryptionConfiguration={
                'Rules': [
                    {'ApplyServerSideEncryptionByDefault': {'SSEAlgorithm': 'AES256'}}
                ]
            }
        )
        
        click.echo(f"S3 bucket {bucket_name} created successfully")
    except ClientError as create_error:
        click.echo(f"Error creating bucket: {create_error}", err=True)
        sys.exit(1)


def upload_templates_to_s3(bucket_name: str, region: str) -> None:
    """Upload CloudFormation templates to S3 bucket"""
    s3_client = boto3.client('s3', region_name=region)
    
    # Get the infrastructure directory using pathlib
    infra_dir = Path(__file__).parent.parent / "infrastructure"
    
    # Define directories to process
    directories = [
        infra_dir,
        infra_dir / "initial",
        infra_dir / "template"
    ]
    
    click.echo("Uploading CloudFormation templates to S3...")
    
    # Upload files from each directory
    for directory in directories:
        if directory.exists():
            for file_path in directory.glob("*.yaml"):
                # All templates go to the infrastructure/ prefix
                s3_key = f"infrastructure/{file_path.name}"
                
                click.echo(f"Uploading {file_path} to s3://{bucket_name}/{s3_key}")
                try:
                    s3_client.upload_file(str(file_path), bucket_name, s3_key)
                except ClientError as e:
                    click.echo(f"Error uploading file: {e}", err=True)
                    sys.exit(1)
    
    # Upload the dev-environment-template.yaml to templates/ prefix
    dev_env_template = infra_dir / "template" / "dev-environment-template.yaml"
    if dev_env_template.exists():
        s3_key = "templates/dev-environment-template.yaml"
        click.echo(f"Uploading {dev_env_template} to s3://{bucket_name}/{s3_key}")
        try:
            s3_client.upload_file(str(dev_env_template), bucket_name, s3_key)
        except ClientError as e:
            click.echo(f"Error uploading file: {e}", err=True)
            sys.exit(1)
    else:
        click.echo(f"Warning: {dev_env_template} not found", err=True)
    
    click.echo(click.style("All templates uploaded successfully", fg="green"))


@click.group()
def cli():
    """Onboarding CLI - Manage development environments"""
    pass


@cli.group()
def admin():
    """Administrator commands for setting up development environments"""
    pass


@cli.group()
def developer():
    """Developer commands for launching development environments"""
    pass


@admin.command("deploy")
@click.option("--region", help="AWS region to deploy to")
@click.option("--artifact-bucket-name", help="Name for the S3 bucket to store artifacts (will be suffixed with account ID)")
def admin_deploy(region: Optional[str], artifact_bucket_name: Optional[str]):
    """Deploy the base infrastructure for development environments"""
    click.echo(click.style("=== Administrator Setup Deployment ===", fg="blue"))
    
    # Check AWS credentials
    if not check_aws_credentials():
        click.echo("Not authenticated with AWS. Please run 'aws sso login' first.", err=True)
        sys.exit(1)
    
    # Get region if not provided
    if not region:
        region = get_aws_region()
    
    # Get AWS account ID
    sts_client = boto3.client('sts', region_name=region)
    account_id = sts_client.get_caller_identity()["Account"]
    
    # Set default artifact bucket name if not provided
    if not artifact_bucket_name:
        artifact_bucket_name = "agent-devenv-artifacts"
    
    # Create the full bucket name with account ID suffix
    full_bucket_name = f"{artifact_bucket_name}-{account_id}"
    
    click.echo(f"Deploying administrator setup to region: {region}")
    
    # Check if S3 bucket exists, create if it doesn't
    bucket_exists = check_s3_bucket_exists(full_bucket_name, region)
    if bucket_exists:
        click.echo(f"S3 bucket {full_bucket_name} already exists")
    else:
        create_s3_bucket(full_bucket_name, region)
    
    # Upload CloudFormation templates to S3
    upload_templates_to_s3(full_bucket_name, region)
    
    # Get the infrastructure directory
    infra_dir = Path(__file__).parent.parent / "infrastructure"
    
    # Deploy the master deployment stack
    master_stack_name = "AgentDevEnv-Infrastructure-Master"
    click.echo("Deploying master CloudFormation stack...")
    
    # Use the deploy_cloudformation_stack function with parameters
    deploy_cloudformation_stack(
        str(infra_dir / "00-admin-deployment.yaml"),
        master_stack_name,
        region,
        parameters={
            'ArtifactBucketName': full_bucket_name
        }
    )
    
    click.echo(click.style("Administrator setup complete!", fg="green"))
    click.echo(f"Master stack: {master_stack_name}")
    click.echo(f"Artifact S3 bucket: {full_bucket_name}")
    click.echo("")
    click.echo(click.style("You can now launch development environments using:", fg="blue"))
    click.echo("python -m application.cli developer launch --key keyname [--region REGION] [--type standard|high|extra]")


@developer.command("launch")
@click.option("--region", required=True, help="AWS region to deploy to")
@click.option("--type", "env_type", type=click.Choice(["standard", "high", "extra"]), required=True,
              help="Environment type (standard, high, or extra performance)")
@click.option("--key", required=True, help="Key name")
def developer_launch(region: str, env_type: str, key: str):
    """Launch a development environment from Service Catalog"""
    click.echo(click.style("=== Development Environment Launcher ===", fg="blue"))
    click.echo(click.style("This script will help you launch a development environment from Service Catalog", fg="yellow"))
    
    # Check AWS credentials
    if not check_aws_credentials():
        click.echo("Not authenticated with AWS. Please run 'aws sso login' first.", err=True)
        sys.exit(1)

    # Initialize Service Catalog client
    sc_client = boto3.client('servicecatalog', region_name=region)
    
    # Get portfolio ID
    portfolio_name = "Development Environment Portfolio"
    click.echo("Fetching available development environment templates...")
    
    try:
        portfolios = sc_client.list_portfolios()
        portfolio_id = None
        
        for portfolio in portfolios.get('PortfolioDetails', []):
            if portfolio.get('DisplayName') == portfolio_name:
                portfolio_id = portfolio.get('Id')
                break
        
        if not portfolio_id:
            click.echo(click.style(f"No portfolio found with name '{portfolio_name}'.", fg="yellow"))
            click.echo("Please check with your administrator that the environment is properly set up.")
            sys.exit(1)
        
        click.echo(click.style(f"Found portfolio: {portfolio_id}", fg="green"))
        
        # List products in the portfolio
        search_products_response = sc_client.search_products_as_admin(PortfolioId=portfolio_id)
        products = []

        for product_view_detail in search_products_response.get('ProductViewDetails', []):
            product_view = product_view_detail.get('ProductViewSummary', {})
            products.append({
                'Id': product_view.get('ProductId'),
                'Name': product_view.get('Name'),
                'Description': product_view.get('ShortDescription', 'No description available')
            })
        
        # Display products
        click.echo("Available development environment templates:")
        click.echo(click.style("ID\t\t\t\tName\t\t\t\tDescription", fg="blue"))
        for product in products:
            click.echo(f"{product['Id']}\t{product['Name']}\t{product['Description']}")
        
        # Get environment type from user if not provided
        if not env_type:
            click.echo("")
            click.echo(click.style("Select a development environment type:", fg="yellow"))
            click.echo("1) Standard Development Environment (4GB RAM, 2 vCPU - t3.medium)")
            click.echo("2) High Performance Development Environment (8GB RAM, 2 vCPU - t3.large)")
            click.echo("3) Extra Performance Development Environment (16GB RAM, 4 vCPU - t3.xlarge)")
            
            choice = click.prompt("Enter your choice", type=click.Choice(["1", "2", "3"]))
            
            if choice == "1":
                env_type = "standard"
            elif choice == "2":
                env_type = "high"
            elif choice == "3":
                env_type = "extra"
        
        # Map environment type to instance type
        instance_type_map = {
            "standard": "t3.medium",
            "high": "t3.large",
            "extra": "t3.xlarge"
        }
        
        instance_type = instance_type_map[env_type]
        
        # Use the unified Development Environment product
        product_name = "Development Environment"
        
        # Get product ID based on name
        product_id = None
        for product in products:
            if product["Name"] == product_name:
                product_id = product["Id"]
                break
        
        if not product_id:
            click.echo(click.style(f"Error: Could not find product with name '{product_name}'.", fg="red"))
            sys.exit(1)
        
        # Get provisioning artifact ID (version)
        describe_product_response = sc_client.describe_product(Id=product_id)
        provisioning_artifacts = describe_product_response.get('ProvisioningArtifacts', [])
        
        if not provisioning_artifacts:
            click.echo(click.style("Error: No provisioning artifacts found for product.", fg="red"))
            sys.exit(1)
        
        # Use the first (latest) provisioning artifact
        artifact_id = provisioning_artifacts[0].get('Id')
        
        # Get username for unique naming
        username = getpass.getuser()
        timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        provisioned_product_name = f"{username}-dev-env-{timestamp}"
        
        click.echo(click.style("Launching development environment...", fg="blue"))
        click.echo(f"Product: {product_name}")
        click.echo(f"Instance Type: {instance_type}")
        click.echo(f"Provisioned Product Name: {provisioned_product_name}")
        
        # Launch the product with parameters
        provision_response = sc_client.provision_product(
            ProductId=product_id,
            ProvisioningArtifactId=artifact_id,
            ProvisionedProductName=provisioned_product_name,
            ProvisioningParameters=[
                {
                    'Key': 'InstanceType',
                    'Value': instance_type
                },
                {
                    'Key': 'UserName',
                    'Value': username
                },
                {
                    'Key': 'KeyName',
                    'Value': key
                }
            ]
        )
        
        click.echo(click.style("Development environment launch initiated!", fg="green"))
        click.echo(f"Provisioned Product ID: {provision_response.get('RecordDetail', {}).get('ProvisionedProductId')}")
        click.echo("")
        click.echo(click.style("To check the status of your environment:", fg="yellow"))
        click.echo(f"Run: python -m application.cli developer status --name {provisioned_product_name}")
        click.echo("")
        click.echo(click.style("Once provisioning is complete, you can find your instance ID in the outputs.", fg="yellow"))
        click.echo(f"Run: python -m application.cli developer outputs --name {provisioned_product_name}")
        click.echo("")
        click.echo(click.style("To connect to your instance using Session Manager:", fg="blue"))
        click.echo("aws ssm start-session --target i-xxxxxxxxxxxxxxxxx")
        click.echo("(Replace i-xxxxxxxxxxxxxxxxx with your actual instance ID from the outputs)")
        
    except ClientError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@developer.command("status")
@click.option("--name", required=True, help="Name of the provisioned product")
@click.option("--region", help="AWS region")
def developer_status(name: str, region: Optional[str]):
    """Check the status of a provisioned development environment"""
    if not check_aws_credentials():
        click.echo("Not authenticated with AWS. Please run 'aws sso login' first.", err=True)
        sys.exit(1)
    
    if not region:
        region = get_aws_region()
    
    sc_client = boto3.client('servicecatalog', region_name=region)
    
    try:
        response = sc_client.describe_provisioned_product(Name=name)
        product_detail = response.get('ProvisionedProductDetail', {})
        
        status = product_detail.get('Status')
        status_message = product_detail.get('StatusMessage', 'No status message available')
        
        click.echo(f"Provisioned Product: {name}")
        click.echo(f"Status: {status}")
        click.echo(f"Status Message: {status_message}")
        click.echo(f"Created: {product_detail.get('CreatedTime')}")
        
        if status == 'ERROR':
            click.echo(click.style("Provisioning failed. Check the AWS Service Catalog console for more details.", fg="red"))
        elif status == 'AVAILABLE':
            click.echo(click.style("Provisioning completed successfully!", fg="green"))
    
    except ClientError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@developer.command("outputs")
@click.option("--name", required=True, help="Name of the provisioned product")
@click.option("--region", help="AWS region")
def developer_outputs(name: str, region: Optional[str]):
    """Get the outputs of a provisioned development environment"""
    if not check_aws_credentials():
        click.echo("Not authenticated with AWS. Please run 'aws sso login' first.", err=True)
        sys.exit(1)
    
    if not region:
        region = get_aws_region()
    
    sc_client = boto3.client('servicecatalog', region_name=region)
    
    try:
        response = sc_client.describe_provisioned_product(Name=name)
        outputs = response.get('ProvisionedProductDetail', {}).get('Outputs', [])
        
        if not outputs:
            click.echo("No outputs found for this provisioned product.")
            return
        
        click.echo(click.style(f"Outputs for {name}:", fg="blue"))
        for output in outputs:
            output_key = output.get('OutputKey')
            output_value = output.get('OutputValue')
            description = output.get('Description', 'No description')
            
            click.echo(f"{output_key}: {output_value}")
            click.echo(f"  Description: {description}")
        
        # Look for instance ID specifically
        instance_ids = [output.get('OutputValue') for output in outputs 
                       if output.get('OutputKey') == 'InstanceId' or 'instance' in output.get('OutputKey', '').lower()]
        
        if instance_ids:
            click.echo("")
            click.echo(click.style("To connect to your instance using Session Manager:", fg="green"))
            for instance_id in instance_ids:
                click.echo(f"aws ssm start-session --target {instance_id}")
    
    except ClientError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@developer.command("list")
@click.option("--region", help="AWS region")
def developer_list(region: Optional[str]):
    """List all provisioned development environments"""
    if not check_aws_credentials():
        click.echo("Not authenticated with AWS. Please run 'aws sso login' first.", err=True)
        sys.exit(1)
    
    if not region:
        region = get_aws_region()
    
    sc_client = boto3.client('servicecatalog', region_name=region)
    
    try:
        response = sc_client.search_provisioned_products()
        products = response.get('ProvisionedProducts', [])
        
        if not products:
            click.echo("No provisioned products found.")
            return
        
        click.echo(click.style("Provisioned Development Environments:", fg="blue"))
        click.echo(f"{'Name':<40} {'Status':<15} {'Type':<30} {'Created'}")
        click.echo("-" * 100)
        
        for product in products:
            name = product.get('Name')
            status = product.get('Status')
            product_type = product.get('Type')
            created = product.get('CreatedTime').strftime("%Y-%m-%d %H:%M:%S") if product.get('CreatedTime') else "Unknown"
            
            status_color = "green" if status == "AVAILABLE" else "yellow" if status == "UNDER_CHANGE" else "red"
            
            click.echo(f"{name:<40} {click.style(f'{status:<15}', fg=status_color)} {product_type:<30} {created}")
    
    except ClientError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@developer.command("terminate")
@click.option("--name", required=True, help="Name of the provisioned product to terminate")
@click.option("--region", help="AWS region")
@click.option("--force", is_flag=True, help="Force termination without confirmation")
def developer_terminate(name: str, region: Optional[str], force: bool):
    """Terminate a provisioned development environment"""
    if not check_aws_credentials():
        click.echo("Not authenticated with AWS. Please run 'aws sso login' first.", err=True)
        sys.exit(1)
    
    if not region:
        region = get_aws_region()
    
    sc_client = boto3.client('servicecatalog', region_name=region)
    
    try:
        # First check if the product exists
        response = sc_client.describe_provisioned_product(Name=name)
        product_detail = response.get('ProvisionedProductDetail', {})
        product_id = product_detail.get('Id')
        
        if not product_id:
            click.echo(f"Could not find provisioned product with name: {name}")
            sys.exit(1)
        
        # Confirm termination
        if not force:
            confirm = click.confirm(f"Are you sure you want to terminate the environment '{name}'?")
            if not confirm:
                click.echo("Termination cancelled.")
                return
        
        # Terminate the product
        sc_client.terminate_provisioned_product(
            ProvisionedProductId=product_id
        )
        
        click.echo(click.style(f"Termination of '{name}' initiated.", fg="yellow"))
        click.echo("This process may take several minutes to complete.")
        click.echo(f"Check status with: onboarding developer status --name {name}")
    
    except ClientError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


if __name__ == "__main__":
    cli()
