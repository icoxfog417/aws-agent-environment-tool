#!/usr/bin/env python3
"""
Onboarding CLI - A tool for managing development environments
"""

import os
import sys
import json
import datetime
import time
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


def deploy_cloudformation_stack(template_path: str, stack_name: str, region: str) -> None:
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
    
    # Deploy the stack
    try:
        if stack_exists:
            cf_client.update_stack(
                StackName=stack_name,
                TemplateBody=template_body,
                Capabilities=['CAPABILITY_NAMED_IAM'],
                Tags=[
                    {'Key': 'ManagedBy', 'Value': 'CloudFormation'},
                    {'Key': 'Environment', 'Value': 'Development'}
                ]
            )
        else:
            cf_client.create_stack(
                StackName=stack_name,
                TemplateBody=template_body,
                Capabilities=['CAPABILITY_NAMED_IAM'],
                Tags=[
                    {'Key': 'ManagedBy', 'Value': 'CloudFormation'},
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
def admin_deploy(region: Optional[str]):
    """Deploy the base infrastructure for development environments"""
    click.echo(click.style("=== Administrator Setup Deployment ===", fg="blue"))
    
    # Check AWS credentials
    if not check_aws_credentials():
        click.echo("Not authenticated with AWS. Please run 'aws sso login' first.", err=True)
        sys.exit(1)
    
    # Get region if not provided
    if not region:
        region = get_aws_region()
    
    click.echo(f"Deploying administrator setup to region: {region}")
    
    # Get the infrastructure directory
    infra_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "infrastructure")
    
    # Deploy the main stack
    main_stack_name = "DevEnvironment-Admin-Setup"
    click.echo("Deploying main CloudFormation stack from initial directory...")
    deploy_cloudformation_stack(
        os.path.join(infra_dir, "initial", "00-admin-main.yaml"),
        main_stack_name,
        region
    )
    
    # Deploy the launch templates stack
    launch_template_stack_name = "DevEnvironment-Launch-Templates"
    click.echo("Deploying launch templates stack...")
    deploy_cloudformation_stack(
        os.path.join(infra_dir, "template", "05-admin-launch-template.yaml"),
        launch_template_stack_name,
        region
    )
    
    # Deploy the service catalog registration stack
    service_catalog_stack_name = "DevEnvironment-Service-Catalog-Registration"
    click.echo("Deploying service catalog registration stack...")
    deploy_cloudformation_stack(
        os.path.join(infra_dir, "template", "06-admin-register-launch-templates.yaml"),
        service_catalog_stack_name,
        region
    )
    
    click.echo(click.style("Administrator setup complete!", fg="green"))
    click.echo(f"Main stack: {main_stack_name}")
    click.echo(f"Launch templates stack: {launch_template_stack_name}")
    click.echo(f"Service catalog registration stack: {service_catalog_stack_name}")


@developer.command("launch")
@click.option("--region", help="AWS region to deploy to")
@click.option("--type", "env_type", type=click.Choice(["standard", "high", "extra"]), 
              help="Environment type (standard, high, or extra performance)")
def developer_launch(region: Optional[str], env_type: Optional[str]):
    """Launch a development environment from Service Catalog"""
    click.echo(click.style("=== Development Environment Launcher ===", fg="blue"))
    click.echo(click.style("This script will help you launch a development environment from Service Catalog", fg="yellow"))
    
    # Check AWS credentials
    if not check_aws_credentials():
        click.echo("Not authenticated with AWS. Please run 'aws sso login' first.", err=True)
        sys.exit(1)
    
    # Get region if not provided
    if not region:
        region = get_aws_region()
    
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
        
        # Map environment type to product name
        product_name_map = {
            "standard": "Standard Development Environment",
            "high": "High Performance Development Environment",
            "extra": "Extra Performance Development Environment"
        }
        
        product_name = product_name_map[env_type]
        
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
        username = os.getlogin()
        timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        product_name_safe = product_name.replace(" ", "-").lower()
        provisioned_product_name = f"{username}-{product_name_safe}-{timestamp}"
        
        click.echo(click.style("Launching development environment...", fg="blue"))
        click.echo(f"Product: {product_name}")
        click.echo(f"Provisioned Product Name: {provisioned_product_name}")
        
        # Launch the product
        provision_response = sc_client.provision_product(
            ProductId=product_id,
            ProvisioningArtifactId=artifact_id,
            ProvisionedProductName=provisioned_product_name
        )
        
        click.echo(click.style("Development environment launch initiated!", fg="green"))
        click.echo(f"Provisioned Product ID: {provision_response.get('RecordDetail', {}).get('ProvisionedProductId')}")
        click.echo("")
        click.echo(click.style("To check the status of your environment:", fg="yellow"))
        click.echo(f"Run: onboarding developer status --name {provisioned_product_name}")
        click.echo("")
        click.echo(click.style("Once provisioning is complete, you can find your instance ID in the outputs.", fg="yellow"))
        click.echo(f"Run: onboarding developer outputs --name {provisioned_product_name}")
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
            
            click.echo(f"{name:<40} {click.style(status:<15, fg=status_color)} {product_type:<30} {created}")
    
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
