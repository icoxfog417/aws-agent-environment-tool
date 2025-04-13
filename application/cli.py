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


def get_cloudformation_output(output_name: str, region: str) -> Optional[str]:
    """Get an exported CloudFormation output value
    
    Args:
        output_name: Name of the exported output to retrieve
        region: AWS region where the stack is deployed
        
    Returns:
        Optional[str]: The output value if found, or None if not found
    """
    cf_client = boto3.client('cloudformation', region_name=region)
    
    try:
        # Get exports from CloudFormation with pagination handling
        response = cf_client.list_exports()
        while True:
            exports = response.get('Exports', [])
            for export in exports:
                if export['Name'] == output_name:
                    return export['Value']
            
            # Break the loop if no more pages
            if 'NextToken' not in response:
                break
            response = cf_client.list_exports(NextToken=response['NextToken'])

        click.echo(f"Error: Could not find CloudFormation export '{output_name}'", err=True)
        return None
        
    except ClientError as e:
        click.echo(f"Error retrieving CloudFormation export: {e}", err=True)
        return None


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


def upload_templates_to_s3(directory: Path, bucket_name: str, region: str) -> None:
    """Upload CloudFormation templates to S3 bucket while preserving directory structure
    
    Args:
        bucket_name: Name of the S3 bucket to upload to
        region: AWS region where the bucket is located
        directory: Optional subdirectory under 'infrastructure/' to upload from
                  If None, all files in infrastructure/ will be uploaded
    """
    s3_client = boto3.client('s3', region_name=region)
    
    if not(directory.exists() and directory.is_dir()):
        click.echo(f"Error: Directory '{directory}' not found", err=True)
        return None
    elif directory.parent.name != "infrastructure":
        click.echo("Error: Directory must be under 'infrastructure/'", err=True)
        return None
    
    # Walk through the target directory recursively
    yaml_files = list(directory.glob("*.yaml"))
    
    if not yaml_files:
        click.echo(f"No YAML files found in {directory}")
        return

    # Upload each file while preserving relative path
    for file_path in yaml_files:
        # Calculate relative path from infrastructure directory parent
        relative_path = file_path.relative_to(directory.parent)
        s3_key = str(relative_path)
        
        click.echo(f"Uploading {file_path} to s3://{bucket_name}/{s3_key}")
        try:
            s3_client.upload_file(str(file_path), bucket_name, s3_key)
        except ClientError as e:
            click.echo(f"Error uploading file: {e}", err=True)
            sys.exit(1)
    
    click.echo(click.style(f"Successfully uploaded {len(yaml_files)} template(s)", fg="green"))


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
def admin_deploy(region: Optional[str], artifact_bucket_name: Optional[str]) -> None:
    """Deploy the base infrastructure for development environments"""
    click.echo(click.style("=== Administrator Setup Deployment ===", fg="blue"))

    # Check AWS credentials
    if not check_aws_credentials():
        click.echo("Not authenticated with AWS. Please run 'aws sso login' first.", err=True)
        return None
    
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

    # Deploy the base deployment stack
    base_stack_name = "AgentDevEnv-Infrastructure-Base"
    infra_dir = Path(__file__).parent.parent / "infrastructure"
    upload_templates_to_s3(infra_dir / "01-base", full_bucket_name, region)
    click.echo("Deploying Base CloudFormation stack...")

    deploy_cloudformation_stack(
        str(infra_dir / "01-base-deployment.yaml"),
        base_stack_name,
        region,
        parameters={
            'ArtifactBucketName': full_bucket_name
        }
    )

    # Deploy Launch Template and upload CloudFormation file for product
    click.echo("Deploying Launch Templates...")
    for template_file in infra_dir.glob("02-template/*.yaml"):
        environment_name = template_file.name.replace("-template.yaml", "")
        stack_name = f"AgentDevEnv-{environment_name}-LaunchTemplate"
        deploy_cloudformation_stack(
            str(template_file),
            stack_name,
            region
        )

        # Get the Launch Template ID and Version
        launch_template_id = get_cloudformation_output(f"AgentDevEnv-{environment_name}-LaunchTemplateId", region)
        launch_template_version = get_cloudformation_output(f"AgentDevEnv-{environment_name}-LaunchTemplateVersion", region)
        subnet_id = get_cloudformation_output("AgentDevEnv-PublicSubnet1Id", region)

        # Edit product file and store it to 03-product directory
        environments = []
        template_path = infra_dir / "03-product-template.yaml"
        with open(template_path, 'r') as file:
            template_content = file.read()
        template_content = template_content.replace("{{Environment}}", environment_name)
        template_content = template_content.replace("{{LaunchTemplateId}}", launch_template_id)
        template_content = template_content.replace("{{LaunchTemplateVersion}}", launch_template_version)
        template_content = template_content.replace("{{SubnetId}}", subnet_id)
        filled_path = infra_dir / "03-product" / f"{environment_name}-product.yaml"
        with open(filled_path, 'w') as file:
            file.write(template_content)
        
        environments.append(environment_name)

    # Upload all files in product directory to S3
    upload_templates_to_s3(infra_dir / "03-product", full_bucket_name, region)

    # Deploy products by executing 02-register-products.yaml
    click.echo("Deploying Products to Service Catalog...")
    for environment in environments:
        # Open the product-service-template.yaml file and replace the placeholder with the bucket name
        template_path = infra_dir / "04-product-service-template.yaml"
        with open(template_path, 'r') as file:
            product_service_content = file.read()
        product_service_content = product_service_content.replace("{{Environment}}", environment)
        filled_path = infra_dir / "04-product-service" / f"{environment}-product-service.yaml"
        with open(filled_path, 'w') as file:
            file.write(product_service_content)

        product_service_stack_name = f"AgentDevEnv-{environment}-ProductService"
        deploy_cloudformation_stack(
            str(filled_path),
            product_service_stack_name,
            region,
            parameters={
                'ArtifactBucketName': full_bucket_name
            }
        )

    click.echo(click.style("Administrator setup complete!", fg="green"))
    click.echo(f"Base stack: {base_stack_name}")
    click.echo(f"Registered products: {', '.join(environments)}")
    click.echo(f"Artifact S3 bucket: {full_bucket_name}")
    click.echo("")
    click.echo(click.style("You can now launch development environments using:", fg="blue"))
    click.echo("uv run python -m application.cli developer launch --key keyname [--region REGION] [--type standard|high|extra]")


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
    portfolio_id = get_cloudformation_output("AgentDevEnv-PortfolioId", region)    
    click.echo(f"Fetching available development environments from {portfolio_id}...")
        
    # List products in the portfolio
    search_products_response = sc_client.search_products_as_admin(PortfolioId=portfolio_id)

    products = []
    # Display products
    click.echo(click.style("\t".join(["Index", "ID", "Name", "Description"]), fg="blue"))
    for product_view_detail in search_products_response.get('ProductViewDetails', []):
        product_view = product_view_detail.get('ProductViewSummary', {})
        product = {
            'Id': product_view.get('ProductId'),
            'Name': product_view.get('Name'),
            'Description': product_view.get('ShortDescription', 'No description available')
        }
        products.append(product)
        click.echo(f"{len(products)})\t{product['Id']}\t{product['Name']}\t{product['Description']}")

    choice = click.prompt("Enter your choice", type=click.Choice([f"{index + 1}" for index in range(len(products))]))
    chosed_product = products[int(choice) - 1]
    product_id = chosed_product['Id']

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
    provisioned_product_name = f"{username}-{chosed_product['Name'].replace(" ", "-").strip()}-{timestamp}"

    click.echo(click.style("Launching development environment...", fg="blue"))
    click.echo(f"Product: {chosed_product['Name']}")
    click.echo(f"Instance Type: {instance_type}")
    click.echo(f"Provisioned Product Name: {provisioned_product_name}")
        
    # Launch the product with parameters
    command_id = f"Command-{provisioned_product_name}"
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
            },
            {
                'Key': 'CommandId',
                'Value': command_id
            }
        ]
    )
    
    # Get the provisioned product ID
    provisioned_product_id = provision_response.get('RecordDetail', {}).get('ProvisionedProductId')
    
    # Wait for provisioning to complete
    click.echo("Waiting for provisioning to complete. This may take several minutes...")
    while True:
        status_response = sc_client.describe_provisioned_product(Id=provisioned_product_id)
        status = status_response.get('ProvisionedProductDetail', {}).get('Status')
        
        if status == 'AVAILABLE':
            click.echo(click.style("Provisioning completed successfully!", fg="green"))
            break
        elif status in ['ERROR', 'TAINTED']:
            click.echo(click.style(f"Provisioning failed with status: {status}", fg="red"))
            break
        elif status == 'UNDER_CHANGE':
            click.echo("Provisioning in progress...")
            time.sleep(5)
        else:
            click.echo(f"Current status: {status}")
            time.sleep(5)

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
    command = get_cloudformation_output(command_id, region)
    click.echo("Connect by")
    click.echo(command)


if __name__ == "__main__":
    cli()
